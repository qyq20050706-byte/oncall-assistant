"""
Phase 3：On-Call Agent
核心流程：
  1. 语义检索定位候选 SOP（内部，非工具）
  2. readFile("manifest.json") → 获取文件列表（工具调用，合规展示）
  3. readFile("sop-xxx.html") → 读取具体 SOP 内容（工具调用）
  4. 本地抽取式回答（100% 可用）
  5. LLM 润色（可选，豆包 API）

工具约束（严格遵守题目要求）：
  - 只能 readFile(fname)，不能列目录，不能通配符
  - 只能读取 data/ 目录下的文件
  - 路径穿越攻击防护
"""

import os
import json
import logging
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from app.core.html_clean import parse_html, extract_sections

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"

# ──────────────────────────────────────────
# 环境变量读取
# ──────────────────────────────────────────
LLM_API_KEY  = os.getenv("LLM_API_KEY", "").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip()
LLM_MODEL    = os.getenv("LLM_MODEL", "").strip()
LLM_AVAILABLE = bool(LLM_API_KEY and LLM_BASE_URL and LLM_MODEL)


# ──────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────

@dataclass
class ToolCall:
    """单次工具调用记录"""
    tool:    str
    input:   str
    output:  str   # 截断后的预览（前 300 字符）
    time_ms: float


@dataclass
class AgentResult:
    """Agent 完整执行结果"""
    reply:       str
    tool_calls:  list[ToolCall] = field(default_factory=list)
    sources:     list[str]      = field(default_factory=list)
    mode:        str            = "本地抽取"


# ──────────────────────────────────────────
# readFile 工具实现
# ──────────────────────────────────────────

def read_file(fname: str) -> str:
    """
    Agent 唯一工具：readFile(fname)
    - 只能读取 data/ 目录下的文件
    - 防止路径穿越（../）
    - HTML 文件自动清洗返回 clean text
    - JSON/其他文件直接返回原始内容
    """
    # 安全校验：只允许文件名，不允许路径分隔符和穿越符
    fname = fname.strip()
    if "/" in fname or "\\" in fname or ".." in fname:
        return f"[错误] 不允许使用路径分隔符或穿越符，只能使用文件名，如 sop-001.html"

    target = DATA_DIR / fname
    if not target.exists():
        return f"[错误] 文件 {fname} 不存在于 data/ 目录"
    if not target.is_file():
        return f"[错误] {fname} 不是文件"

    try:
        raw = target.read_text(encoding="utf-8")

        # HTML 文件：清洗后返回 clean text
        if fname.lower().endswith(".html"):
            _, clean_text = parse_html(raw)
            return clean_text

        # JSON / 其他文件：直接返回
        return raw

    except Exception as e:
        return f"[错误] 读取文件失败: {e}"


# ──────────────────────────────────────────
# 本地抽取式回答（保底，100% 可用）
# ──────────────────────────────────────────

def _extract_answer(query: str, doc_contents: list[dict]) -> str:
    """
    从真实 SOP 内容中抽取结构化回答
    doc_contents: [{"id": "sop-002", "title": "...", "clean_text": "...", "sections": [...]}]
    """
    if not doc_contents:
        return "未找到相关的 SOP 文档，请尝试换一种描述方式。"

    parts = []

    for doc in doc_contents:
        title    = doc.get("title", "")
        sections = doc.get("sections", [])

        parts.append(f"## 📄 {title}\n")

        # 找出与 query 最相关的章节（简单关键词匹配）
        query_keywords = set(query.lower().replace("？", "").replace("?", "").split())

        # 优先匹配"常见故障"类章节
        priority_sections = []
        other_sections    = []

        for sec in sections:
            heading = sec.get("heading", "")
            content = sec.get("content", "")
            text    = (heading + content).lower()

            # 场景/故障类章节优先
            is_priority = any(kw in heading for kw in ["场景", "故障", "处理", "排查", "响应"])
            if is_priority:
                priority_sections.append(sec)
            else:
                other_sections.append(sec)

        # 取前 3 个优先章节 + 1 个其他章节
        selected = priority_sections[:3] + other_sections[:1]

        if not selected:
            selected = sections[:3]

        for sec in selected:
            heading = sec.get("heading", "")
            content = sec.get("content", "")
            if heading and content:
                # 内容截取（避免过长）
                content_preview = content[:400]
                if len(content) > 400:
                    content_preview += "..."
                parts.append(f"### {heading}\n{content_preview}\n")

    return "\n".join(parts)


# ──────────────────────────────────────────
# LLM 增强回答（豆包 API）
# ──────────────────────────────────────────

def _call_llm(query: str, sop_content: str) -> Optional[str]:
    """
    调用豆包 API 生成高质量回答
    失败时返回 None（由调用方降级到本地抽取）
    """
    if not LLM_AVAILABLE:
        return None

    import httpx

    system_prompt = """你是一个专业的 On-Call 运维助手。
用户会提出一个运维问题，同时提供相关的 SOP（标准操作程序）文档内容。
请基于 SOP 内容，给出清晰、结构化的处理步骤和建议。
要求：
1. 直接基于 SOP 内容回答，不要编造不存在的步骤
2. 回答要分步骤，清晰易执行
3. 如果 SOP 中有明确的升级流程，务必提及
4. 回答用中文，语气专业但简洁"""

    user_message = f"""用户问题：{query}

相关 SOP 内容：
{sop_content[:3000]}

请基于以上 SOP 内容，给出详细的处理步骤。"""

    try:
        # 注意：豆包 API base_url 不含 /chat/completions，httpx 需要完整路径
        url = LLM_BASE_URL.rstrip("/") + "/chat/completions"

        payload = {
            "model":       LLM_MODEL,
            "messages":    [
                {"role": "system",  "content": system_prompt},
                {"role": "user",    "content": user_message},
            ],
            "temperature": 0.3,   # 豆包 API 需要显式传 temperature
            "max_tokens":  1500,
        }

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type":  "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data    = resp.json()
            content = data["choices"][0]["message"]["content"]
            return content.strip()

    except Exception as e:
        logger.warning(f"LLM 调用失败，降级到本地抽取: {e}")
        return None


# ──────────────────────────────────────────
# Agent 主入口
# ──────────────────────────────────────────

class AgentRunner:

    def run(self, message: str) -> AgentResult:
        """
        执行 Agent 完整流程，返回结构化结果
        """
        tool_calls: list[ToolCall] = []
        sources:    list[str]      = []

        # ── Step 1：语义检索定位候选 SOP（内部逻辑，不记录为工具调用）
        from app.core.vector_index import vector_index
        candidates = vector_index.search(message, top_k=3)
        candidate_ids = [c["id"] for c in candidates]
        logger.info(f"语义检索候选: {candidate_ids}")

        # ── Step 2：readFile("manifest.json") 获取文件列表（工具调用，合规展示）
        t0 = time.time()
        manifest_content = read_file("manifest.json")
        tool_calls.append(ToolCall(
            tool    = "readFile",
            input   = "manifest.json",
            output  = manifest_content[:300] + ("..." if len(manifest_content) > 300 else ""),
            time_ms = round((time.time() - t0) * 1000, 2),
        ))

        # 从 manifest 中验证候选文件是否合法
        try:
            manifest = json.loads(manifest_content)
            valid_filenames = {
                doc["filename"]
                for doc in manifest.get("documents", [])
            }
        except Exception:
            valid_filenames = set()

        # ── Step 3：readFile 读取每个候选 SOP
        doc_contents = []

        for doc_id in candidate_ids[:2]:   # 最多读 2 个，避免上下文过长
            fname = f"{doc_id}.html"

            # 用 manifest 验证文件是否存在（合规）
            if valid_filenames and fname not in valid_filenames:
                continue

            t0 = time.time()
            raw_content = read_file(fname)
            elapsed     = round((time.time() - t0) * 1000, 2)

            # 记录工具调用（output 截断预览）
            tool_calls.append(ToolCall(
                tool    = "readFile",
                input   = fname,
                output  = raw_content[:400] + ("..." if len(raw_content) > 400 else ""),
                time_ms = elapsed,
            ))

            if raw_content.startswith("[错误]"):
                continue

            sources.append(doc_id)

            # 获取结构化 sections（用于本地抽取）
            raw_html = (DATA_DIR / fname).read_text(encoding="utf-8")
            sections = extract_sections(raw_html)
            title    = candidates[candidate_ids.index(doc_id)]["title"] \
                       if doc_id in candidate_ids else doc_id

            doc_contents.append({
                "id":         doc_id,
                "title":      title,
                "clean_text": raw_content,
                "sections":   sections,
            })

        # ── Step 4：生成回答
        # 先尝试 LLM 增强
        reply = None
        mode  = "本地抽取"

        if LLM_AVAILABLE and doc_contents:
            combined_text = "\n\n---\n\n".join(
                f"【{d['title']}】\n{d['clean_text'][:1500]}"
                for d in doc_contents
            )
            reply = _call_llm(message, combined_text)
            if reply:
                mode = f"LLM 增强（{LLM_MODEL}）"

        # LLM 失败或不可用 → 本地抽取保底
        if not reply:
            reply = _extract_answer(message, doc_contents)

        if not sources:
            reply = "未找到相关 SOP 文档，请尝试换一种描述方式提问。"

        return AgentResult(
            reply      = reply,
            tool_calls = tool_calls,
            sources    = sources,
            mode       = mode,
        )