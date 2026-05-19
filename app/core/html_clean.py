"""
HTML 清洗模块
核心职责：
1. 移除 script / style / noscript 标签及其内容
2. HTML entities 解码（&#38; → &，&amp; → & 等）
3. 容错解析（支持 sop-004 这类不规范 HTML）
4. 提取 title 和 clean text
"""

from bs4 import BeautifulSoup
from typing import Tuple


def parse_html(html: str) -> Tuple[str, str]:
    """
    解析 HTML，返回 (title, clean_text)
    
    - title: <title> 标签内容，decode 后；若无则取 h1
    - clean_text: 去除 script/style/noscript 后的可见正文，HTML entities 已 decode
    """
    # lxml 容错能力强，能处理 sop-004 这类不规范 HTML
    # 若 lxml 未安装则 fallback 到 html.parser
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    # ① 提取 title（BeautifulSoup 自动 decode entities）
    title = ""
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)
    
    if not title:
        h1_tag = soup.find("h1")
        if h1_tag:
            title = h1_tag.get_text(strip=True)
    
    if not title:
        title = "未知文档"

    # ② 移除所有 script / style / noscript 标签及其内容
    # decompose() 直接从树中删除节点，确保内容不会残留
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()

    # ③ 提取可见文本（BeautifulSoup 自动处理 HTML entities decode）
    # separator="\n" 保留段落结构，便于后续 snippet 提取
    clean_text = soup.get_text(separator="\n", strip=True)

    # ④ 清理多余空行（超过 2 个连续换行压缩为 2 个）
    import re
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)
    clean_text = clean_text.strip()

    return title, clean_text


def extract_sections(html: str) -> list[dict]:
    """
    提取文档的章节结构，用于 Phase 2 分块 embedding 和 Phase 3 Agent 摘要
    返回: [{"heading": "场景一：OOM", "content": "..."}, ...]
    """
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    # 移除 script / style / noscript
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()

    sections = []
    current_heading = "概述"
    current_content_parts = []

    # 遍历所有标签，按 h2/h3 分节
    for element in soup.find_all(["h1", "h2", "h3", "p"]):
        tag_name = element.name
        text = element.get_text(strip=True)
        
        if not text:
            continue

        if tag_name in ("h1", "h2", "h3"):
            # 保存上一节
            if current_content_parts:
                sections.append({
                    "heading": current_heading,
                    "content": "\n".join(current_content_parts)
                })
                current_content_parts = []
            current_heading = text
        else:
            # p 标签
            current_content_parts.append(text)

    # 保存最后一节
    if current_content_parts:
        sections.append({
            "heading": current_heading,
            "content": "\n".join(current_content_parts)
        })

    return sections