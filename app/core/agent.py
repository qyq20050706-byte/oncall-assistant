"""
Phase 3：On-Call Agent
真正的 Agent 设计：LLM 负责意图判断 + 多文档综合 + 回答生成
本地抽取作为 LLM 不可用时的保底
"""

import os
import json
import logging
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from app.core.html_clean import parse_html

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"

LLM_API_KEY  = os.getenv("LLM_API_KEY", "").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip()
LLM_MODEL    = os.getenv("LLM_MODEL", "").strip()
LLM_AVAILABLE = bool(LLM_API_KEY and LLM_BASE_URL and LLM_MODEL)


@dataclass
class ToolCall:
    tool:    str
    input:   str
    output:  str
    time_ms: float


@dataclass
class AgentResult:
    reply:      str
    tool_calls: list[ToolCall] = field(default_factory=list)
    sources:    list[str]      = field(default_factory=list)
    mode:       str            = "本地抽取"


# ──────────────────────────────────────────
# readFile 工具
# ──────────────────────────────────────────

def read_file(fname: str) -> str:
    fname = fname.strip()
    if not fname or "/" in fname or "\\" in fname:
        return "[错误] 只能使用文件名，不能包含路径"

    target = (DATA_DIR / fname).resolve()

    # 边界检查：解析后的路径必须仍在 DATA_DIR 之下
    try:
        target.relative_to(DATA_DIR.resolve())
    except ValueError:
        return "[错误] 文件路径越权"

    if not target.exists():
        return f"[错误] 文件 {fname} 不存在"
    if not target.is_file():
        return f"[错误] {fname} 不是文件"

    try:
        raw = target.read_text(encoding="utf-8")
        if fname.lower().endswith(".html"):
            _, clean_text = parse_html(raw)
            return clean_text
        return raw
    except Exception as e:
        return f"[错误] 读取失败: {e}"


# ──────────────────────────────────────────
# LLM 调用（通用）
# ──────────────────────────────────────────

def _call_llm_raw(messages: list[dict], max_tokens: int = 1500) -> Optional[str]:
    """底层 LLM 调用，失败返回 None"""
    if not LLM_AVAILABLE:
        return None
    import httpx
    try:
        url = LLM_BASE_URL.rstrip("/") + "/chat/completions"
        resp = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model":       LLM_MODEL,
                "messages":    messages,
                "temperature": 0.3,
                "max_tokens":  max_tokens,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"LLM 调用失败: {e}")
        return None


# ──────────────────────────────────────────
# Step 1：意图分析（简化，无外部调用）
# ──────────────────────────────────────────

def _analyze_intent(message: str) -> dict:
    """
    意图分析：只判断明显的闲聊/问候
    非运维问题通过语义检索相关度阈值来过滤（更可靠）
    """
    msg = message.strip()

    # 极短消息
    if len(msg) <= 2:
        return {
            "type": "chitchat",
            "chitchat_reply": "你好！我是 On-Call 运维助手，请描述你遇到的运维问题。"
        }

    # 明显问候词（精确匹配）
    greetings = [
        "你好", "您好", "hi", "hello", "hey", "哈喽", "嗨",
        "早上好", "下午好", "晚上好", "谢谢", "感谢", "再见",
        "好的", "ok", "okay", "测试", "test",
    ]
    msg_lower = msg.lower()
    if any(msg_lower == g or msg_lower == g + "！" or msg_lower == g + "~"
           for g in greetings):
        return {
            "type": "chitchat",
            "chitchat_reply": (
                "你好！我是 On-Call 运维助手。\n\n"
                "可以帮你处理：服务故障、数据库问题、安全事件、基础设施故障等。\n\n"
                "请描述你遇到的运维问题 👇"
            )
        }

    # 其余所有问题一律走语义检索+相关度阈值过滤
    need_multiple = any(kw in msg for kw in
                        ["流程", "规范", "p0", "P0", "p1", "P1", "升级", "综合", "全部", "所有"])
    return {
        "type": "oncall",
        "search_queries": [message],
        "need_multiple":  need_multiple,
    }

def _out_of_scope_reply(message: str) -> str:
    """当问题与 SOP 完全无关时的固定回复"""
    return (
        f"抱歉，「{message[:20]}」超出了我的服务范围。\n\n"
        "我是专注于 IT 运维的 On-Call 助手，可以帮你处理：\n"
        "• 🔥 服务故障排查（OOM、超时、崩溃）\n"
        "• 🗄️ 数据库问题（主从延迟、连接池、慢查询）\n"
        "• 🛡️ 安全事件响应（入侵检测、数据泄露）\n"
        "• ☁️ 基础设施问题（K8s、CDN、DNS）\n"
        "• 📱 移动端/AI 服务故障\n\n"
        "请描述你遇到的运维问题，我来帮你查找对应 SOP。"
    )


# ──────────────────────────────────────────
# Step 2：本地抽取式回答（保底）
# ──────────────────────────────────────────

def _extract_answer(message: str, doc_contents: list[dict]) -> str:
    if not doc_contents:
        return "未找到相关 SOP 文档，请换一种描述方式。"

    parts = []
    for doc in doc_contents:
        parts.append(f"## 📄 {doc.get('title', '')}\n")
        sections = doc.get("sections", [])

        if not sections:
            parts.append(doc.get("clean_text", "")[:500] + "...\n")
            continue

        # 优先取"场景/故障/处理"类章节
        priority = [s for s in sections
                    if any(kw in s.get("heading", "")
                           for kw in ["场景", "故障", "处理", "排查", "响应", "升级"])]
        others   = [s for s in sections if s not in priority]
        selected = (priority[:3] + others[:1]) or sections[:3]

        for sec in selected:
            h = sec.get("heading", "")
            c = sec.get("content", "")[:400]
            if len(sec.get("content", "")) > 400:
                c += "..."
            if h:
                parts.append(f"### {h}\n{c}\n")

    return "\n".join(parts)


# ──────────────────────────────────────────
# Step 3：LLM 综合回答
# ──────────────────────────────────────────

def _llm_answer(message: str, doc_contents: list[dict],
                history: list[dict] | None = None) -> Optional[str]:
    if not LLM_AVAILABLE or not doc_contents:
        return None

    sop_text = "\n\n---\n\n".join(
        f"【{d['title']}】\n{d['clean_text'][:2000]}"
        for d in doc_contents
    )

    messages = [{
        "role": "system",
        "content": (
            "你是专业的 On-Call 运维助手。"
            "请基于提供的 SOP 文档内容，给出清晰、结构化的处理步骤。"
            "要求：1.只基于SOP内容回答，不编造 2.分步骤说明 3.中文回答 4.提及升级流程"
        ),
    }]

    # 注入对话历史（最多最近 6 轮，控制上下文长度）
    if history:
        for turn in history[-6:]:
            role = turn.get("role")
            content = turn.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    messages.append({
        "role": "user",
        "content": f"问题：{message}\n\nSOP文档：\n{sop_text}",
    })

    return _call_llm_raw(messages, max_tokens=2000)


# ──────────────────────────────────────────
# Agent 主入口
# ──────────────────────────────────────────

class AgentRunner:

    def run(self, message: str, history: list[dict] | None = None) -> AgentResult:
        tool_calls: list[ToolCall] = []
        sources:    list[str]      = []

        # ── Step 1：意图分析（先判断，避免不必要的工具调用）
        intent = _analyze_intent(message)
        logger.info(f"意图分析结果: {intent}")

        # 闲聊直接返回，不调用任何工具
        if intent.get("type") == "chitchat":
            return AgentResult(
                reply      = intent.get("chitchat_reply", "你好！我是 On-Call 助手。"),
                tool_calls = tool_calls,
                sources    = [],
                mode       = "意图识别",
            )

        # ── Step 2：只有运维问题才读取 manifest（工具调用展示）
        t0 = time.time()
        manifest_content = read_file("manifest.json")
        tool_calls.append(ToolCall(
            tool    = "readFile",
            input   = "manifest.json",
            output  = manifest_content[:300] + ("..." if len(manifest_content) > 300 else ""),
            time_ms = round((time.time() - t0) * 1000, 2),
        ))

        # ── Step 3：语义检索定位候选 SOP
        from app.core.vector_index import vector_index

        search_queries = intent.get("search_queries", [message])
        need_multiple  = intent.get("need_multiple", False)
        top_k          = 5 if need_multiple else 3

        # 多查询合并去重
        all_candidates: list[dict] = []
        seen_ids: set[str] = set()

        for q in search_queries[:2]:
            results = vector_index.search(q, top_k=top_k)
            for r in results:
                if r["id"] not in seen_ids:
                    all_candidates.append(r)
                    seen_ids.add(r["id"])

        candidate_ids = [c["id"] for c in all_candidates]
        logger.info(f"语义检索候选（合并）: {candidate_ids}")

        # ── 相关度门槛：最高分低于阈值，说明问题与 SOP 无关
        from app.core.vector_index import vector_index
        if vector_index.mode == "TF-IDF 兜底":
            RELEVANCE_THRESHOLD = 0.02
        else:
            RELEVANCE_THRESHOLD = 0.25

        top_score = all_candidates[0]["score"] if all_candidates else 0.0
        logger.info(
            f"相关度判定: top1={top_score:.4f}, 阈值={RELEVANCE_THRESHOLD} "
            f"(模式: {vector_index.mode}), 候选={[(c['id'], round(c['score'], 4)) for c in all_candidates[:3]]}"
        )

        if top_score < RELEVANCE_THRESHOLD:
            if LLM_AVAILABLE:
                polite_reply = _call_llm_raw([
                    {"role": "system", "content": "你是On-Call运维助手，只处理IT运维相关问题。用1-2句话礼貌回应非运维问题，并引导用户提运维问题。"},
                    {"role": "user",   "content": message}
                ], max_tokens=150)
                reply = polite_reply or _out_of_scope_reply(message)
            else:
                reply = _out_of_scope_reply(message)

            return AgentResult(
                reply      = reply,
                tool_calls = tool_calls,
                sources    = [],
                mode       = "范围外问题",
            )

        # ── Step 4：readFile 读取候选 SOP（优化：复用 DocStore 元数据）
        doc_contents  = []
        read_count    = 3 if need_multiple else 2

        # 校验 manifest 有效性
        try:
            manifest    = json.loads(manifest_content)
            valid_files = {d["filename"] for d in manifest.get("documents", [])}
        except Exception:
            valid_files = set()

        for doc_id in candidate_ids[:read_count]:
            fname = f"{doc_id}.html"
            if valid_files and fname not in valid_files:
                continue

            t0          = time.time()
            raw_content = read_file(fname)
            elapsed     = round((time.time() - t0) * 1000, 2)

            tool_calls.append(ToolCall(
                tool    = "readFile",
                input   = fname,
                output  = raw_content[:400] + ("..." if len(raw_content) > 400 else ""),
                time_ms = elapsed,
            ))

            if raw_content.startswith("[错误]"):
                continue

            sources.append(doc_id)

            # 从全局 DocStore 直接获取 title 和 sections，避免重复读磁盘和解析
            from app.core.doc_store import doc_store
            doc_meta = doc_store.get_doc(doc_id)
            if doc_meta:
                title = doc_meta["title"]
                sections = doc_meta["sections"]
            else:
                title = doc_id
                sections = []

            doc_contents.append({
                "id":         doc_id,
                "title":      title,
                "clean_text": raw_content,
                "sections":   sections,
            })

        # ── Step 5：生成回答（LLM 优先，本地抽取保底）
        reply = None
        mode  = "本地抽取"

        if LLM_AVAILABLE and doc_contents:
            reply = _llm_answer(message, doc_contents, history=history)
            if reply:
                mode = f"LLM 增强（{LLM_MODEL}）"

        if not reply:
            reply = _extract_answer(message, doc_contents)

        if not sources:
            reply = "未找到相关 SOP 文档，请尝试换一种描述方式。"

        return AgentResult(
            reply      = reply,
            tool_calls = tool_calls,
            sources    = sources,
            mode       = mode,
        )
