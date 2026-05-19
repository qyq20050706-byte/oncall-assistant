"""
Phase 1：关键词搜索引擎
路由前缀：/v1

API:
  POST /v1/documents      添加文档
  GET  /v1/search?q=xxx   关键词搜索
  GET  /v1                搜索页面
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.core.doc_store import doc_store
from app.core.keyword_index import keyword_index

router = APIRouter(tags=["Phase1 - 关键词搜索"])


# ──────────────────────────────────────────
# 数据模型
# ──────────────────────────────────────────

class DocumentInput(BaseModel):
    id: str
    html: str


# ──────────────────────────────────────────
# API 路由
# ──────────────────────────────────────────

@router.post("/documents", status_code=201)
async def add_document(doc: DocumentInput):
    """
    添加文档到索引
    """
    if not doc.id or not doc.html:
        raise HTTPException(status_code=400, detail="id 和 html 不能为空")

    # 存入 DocStore 并写入磁盘
    result = doc_store.add_document(doc.id, doc.html)

    # 更新关键词索引
    stored_doc = doc_store.get_doc(doc.id)
    if stored_doc:
        keyword_index.add_document(
            doc.id,
            stored_doc["clean_text"],
            stored_doc["title"]
        )

    return result


@router.get("/search")
async def search(request: Request):
    """
    关键词搜索
    
    特殊处理：q=& 的 URL 解析陷阱
    FastAPI 默认将 ?q=& 解析为 q=""（因为 & 是参数分隔符）
    必须读取原始 query string 来正确处理
    """
    # 读取原始 query string（绕过框架的参数解析）
    raw_query_string = str(request.url.query)  # 例如 "q=&" 或 "q=OOM"
    
    query = _parse_query_param(raw_query_string)
    
    results = keyword_index.search(query)
    
    return {
        "query": query,
        "results": results,
        "total": len(results)
    }


@router.get("/", response_class=HTMLResponse)
async def search_page():
    """
    Phase 1 搜索页面
    """
    return HTMLResponse(content=_get_search_page_html("v1", "关键词搜索"))


# ──────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────

def _parse_query_param(raw_query_string: str) -> str:
    """
    从原始 query string 中提取 q 参数值
    
    正确处理以下情况：
    - "q=OOM"        → "OOM"
    - "q=&"          → "&"     ← 标准解析会错误返回空
    - "q=%26"        → "&"     ← URL 编码的 &
    - "q=CDN&page=1" → "CDN"   ← & 作为参数分隔符
    - "q="           → ""
    - ""             → ""
    
    核心思路：找到 q= 之后的内容，用正则判断 & 后面是否跟着 key=value
    如果是，则 & 是参数分隔符；否则 & 是查询值的一部分。
    """
    import re
    from urllib.parse import unquote_plus

    if not raw_query_string:
        return ""

    # Step 1: 定位 q= 的起始位置
    if raw_query_string.startswith("q="):
        pos = 0
    elif "&q=" in raw_query_string:
        pos = raw_query_string.index("&q=") + 1
    else:
        return ""

    # Step 2: 取 q= 之后的所有内容
    after_q_eq = raw_query_string[pos + 2:]  # 跳过 "q="

    # Step 3: 找到下一个"真正的参数分隔符"
    # 真正的分隔符 = & 后面紧跟 param_name=
    match = re.search(r'&([a-zA-Z_]\w*)=', after_q_eq)
    if match:
        q_value = after_q_eq[:match.start()]
    else:
        q_value = after_q_eq

    # Step 4: URL decode（%26 → &，%20 → 空格 等）
    q_value = unquote_plus(q_value)

    return q_value


def _get_search_page_html(version: str, description: str) -> str:
    """
    生成简洁的搜索页面 HTML
    共用于 v1 和 v2（通过参数区分）
    """
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>On-Call 助手 - {description}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
            background: #f5f7fa;
            color: #333;
            padding: 20px;
        }}
        .container {{ max-width: 800px; margin: 40px auto; }}
        h1 {{ color: #1a73e8; margin-bottom: 8px; font-size: 24px; }}
        .subtitle {{ color: #666; font-size: 14px; margin-bottom: 24px; }}
        .search-box {{
            display: flex;
            gap: 8px;
            margin-bottom: 24px;
        }}
        input {{
            flex: 1;
            padding: 12px 16px;
            border: 2px solid #ddd;
            border-radius: 8px;
            font-size: 16px;
            outline: none;
            transition: border-color 0.2s;
        }}
        input:focus {{ border-color: #1a73e8; }}
        button {{
            padding: 12px 24px;
            background: #1a73e8;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            cursor: pointer;
            transition: background 0.2s;
        }}
        button:hover {{ background: #1557b0; }}
        .results {{ margin-top: 16px; }}
        .result-item {{
            background: white;
            border-radius: 8px;
            padding: 16px 20px;
            margin-bottom: 12px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.08);
            border-left: 4px solid #1a73e8;
        }}
        .result-title {{ font-size: 18px; font-weight: 600; color: #1a73e8; margin-bottom: 6px; }}
        .result-id {{ font-size: 12px; color: #999; margin-bottom: 8px; }}
        .result-snippet {{ font-size: 14px; color: #555; line-height: 1.6; }}
        .result-score {{ font-size: 12px; color: #aaa; margin-top: 8px; }}
        .empty {{ text-align: center; color: #999; padding: 40px; font-size: 16px; }}
        .loading {{ text-align: center; color: #1a73e8; padding: 20px; }}
        .query-info {{ 
            font-size: 14px; color: #666; margin-bottom: 16px; 
            padding: 8px 12px; background: #e8f0fe; border-radius: 4px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚨 On-Call 助手 <span style="font-size:16px;color:#666;">/{version}</span></h1>
        <p class="subtitle">{description} — 基于 SOP 文档的智能检索</p>
        
        <div class="search-box">
            <input 
                type="text" 
                id="queryInput" 
                placeholder="输入关键词，例如：OOM、主从延迟、DDoS攻击..."
                onkeydown="if(event.key==='Enter') doSearch()"
            />
            <button onclick="doSearch()">搜索</button>
        </div>
        
        <div id="results"></div>
    </div>

    <script>
        // 从 URL 参数中恢复搜索词
        const urlParams = new URLSearchParams(window.location.search);
        const initialQ = urlParams.get('q');
        if (initialQ !== null) {{
            document.getElementById('queryInput').value = initialQ;
            doSearch();
        }}

        async function doSearch() {{
            const query = document.getElementById('queryInput').value;
            const resultsDiv = document.getElementById('results');
            
            resultsDiv.innerHTML = '<div class="loading">搜索中...</div>';
            
            try {{
                // 使用 encodeURIComponent 正确编码查询词（& → %26）
                const response = await fetch(`/{version}/search?q=${{encodeURIComponent(query)}}`);
                const data = await response.json();
                
                renderResults(data);
            }} catch (e) {{
                resultsDiv.innerHTML = `<div class="empty">搜索出错：${{e.message}}</div>`;
            }}
        }}

        function renderResults(data) {{
            const resultsDiv = document.getElementById('results');
            
            if (!data.results || data.results.length === 0) {{
                resultsDiv.innerHTML = `
                    <div class="query-info">查询词：<strong>"${{escapeHtml(data.query)}}"</strong> — 未找到匹配文档</div>
                    <div class="empty">没有找到相关的 SOP 文档</div>
                `;
                return;
            }}
            
            let html = `<div class="query-info">
                查询词：<strong>"${{escapeHtml(data.query)}}"</strong> — 
                找到 <strong>${{data.total}}</strong> 个相关文档
            </div>`;
            
            data.results.forEach(r => {{
                html += `
                    <div class="result-item">
                        <div class="result-title">${{escapeHtml(r.title)}}</div>
                        <div class="result-id">文档 ID：${{escapeHtml(r.id)}}</div>
                        <div class="result-snippet">${{escapeHtml(r.snippet)}}</div>
                        <div class="result-score">相关度：${{r.score}}</div>
                    </div>
                `;
            }});
            
            resultsDiv.innerHTML = html;
        }}

        function escapeHtml(str) {{
            if (!str) return '';
            return str
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;');
        }}
    </script>
</body>
</html>"""