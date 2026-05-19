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
    # 从原始 query string 中提取 q 参数值
    # 正确处理 q=& 等特殊字符
    import re
    from urllib.parse import unquote_plus

    if not raw_query_string:
        return ""

    if raw_query_string.startswith("q="):
        pos = 0
    elif "&q=" in raw_query_string:
        pos = raw_query_string.index("&q=") + 1
    else:
        return ""

    after_q_eq = raw_query_string[pos + 2:]

    match = re.search(r'&([a-zA-Z_]\w*)=', after_q_eq)
    if match:
        q_value = after_q_eq[:match.start()]
    else:
        q_value = after_q_eq

    return unquote_plus(q_value)


@router.get("/documents/{doc_id}", response_class=HTMLResponse)
async def view_document(doc_id: str, request: Request):
    """
    文档详情页
    根据 ?from=v1/v2/v3 自适应主题色和返回链接
    根据 ?q=xxx 恢复搜索词
    """
    doc = doc_store.get_doc(doc_id)
    if not doc:
        return HTMLResponse("<h1>文档不存在</h1>", status_code=404)

    from_version = request.query_params.get("from", "v1")
    query = request.query_params.get("q", "")

    if query:
        back_url = f"/{from_version}/?q={query}"
    else:
        back_url = f"/{from_version}/"

    # 主题配置：v1 蓝色 / v2 紫色 / v3 绿色
    themes = {
        "v1": {
            "color": "#1a73e8",
            "color_dark": "#1557b0",
            "light": "#e8f0fe",
            "gradient_from": "#f0f4ff",
            "gradient_to": "#e8eaf6",
            "icon": "🔍",
            "name": "关键词搜索",
        },
        "v2": {
            "color": "#7c3aed",
            "color_dark": "#5b21b6",
            "light": "#f3e8ff",
            "gradient_from": "#faf5ff",
            "gradient_to": "#ede9fe",
            "icon": "🧠",
            "name": "语义搜索",
        },
        "v3": {
            "color": "#059669",
            "color_dark": "#047857",
            "light": "#d1fae5",
            "gradient_from": "#f0fdf4",
            "gradient_to": "#dcfce7",
            "icon": "🤖",
            "name": "Agent 对话",
        },
    }
    theme = themes.get(from_version, themes["v1"])

    title = doc["title"]
    sections = doc.get("sections", [])

    sections_html = ""
    for sec in sections:
        heading = sec.get("heading", "")
        content = sec.get("content", "").replace("\n", "<br>")
        if heading:
            tag = "h2" if not heading.startswith("场景") else "h3"
            sections_html += f"<{tag}>{heading}</{tag}><p>{content}</p>"

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} — On-Call 助手</title>
    <style>
        :root {{
            --primary: {theme['color']};
            --primary-dark: {theme['color_dark']};
            --primary-light: {theme['light']};
            --gradient-from: {theme['gradient_from']};
            --gradient-to: {theme['gradient_to']};
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
            background:linear-gradient(135deg,var(--gradient-from) 0%,var(--gradient-to) 100%);
            min-height:100vh; color:#1a1a2e; line-height:1.6;
        }}
        .topbar {{
            background:rgba(255,255,255,0.85); backdrop-filter:blur(12px);
            border-bottom:1px solid rgba(0,0,0,0.06);
            padding:0 32px; height:60px; display:flex; align-items:center;
            justify-content:space-between;
            box-shadow:0 1px 8px rgba(0,0,0,0.04);
            position:sticky; top:0; z-index:100;
        }}
        .topbar-logo {{
            font-size:18px; font-weight:700; color:var(--primary);
            display:flex; align-items:center; gap:8px;
        }}
        .topbar-nav {{ display:flex; gap:6px; }}
        .nav-btn {{
            padding:6px 14px; border-radius:20px; font-size:13px;
            text-decoration:none; color:#555; transition:all .2s;
        }}
        .nav-btn:hover {{ background:var(--primary); color:white; }}
        .nav-btn.active {{ background:var(--primary); color:white; }}

        .container {{ max-width:880px; margin:40px auto; padding:0 20px 80px; }}

        .breadcrumb {{
            display:flex; align-items:center; gap:8px;
            margin-bottom:20px; font-size:13px; color:#888;
        }}
        .breadcrumb a {{
            color:var(--primary); text-decoration:none; font-weight:500;
        }}
        .breadcrumb a:hover {{ text-decoration:underline; }}

        .back-btn {{
            display:inline-flex; align-items:center; gap:6px;
            margin-bottom:24px; padding:10px 20px;
            background:white; color:var(--primary);
            border:1px solid var(--primary-light); border-radius:24px;
            text-decoration:none; font-size:14px; font-weight:600;
            transition:all .2s; box-shadow:0 2px 8px rgba(0,0,0,0.04);
        }}
        .back-btn:hover {{
            background:var(--primary); color:white;
            border-color:var(--primary); transform:translateX(-2px);
            box-shadow:0 4px 16px rgba(0,0,0,0.10);
        }}

        .card {{
            background:white; border-radius:20px;
            padding:40px 48px;
            box-shadow:0 4px 24px rgba(0,0,0,0.06),
                       0 1px 3px rgba(0,0,0,0.04);
            animation:fadeIn .4s ease-out;
        }}
        @keyframes fadeIn {{
            from {{ opacity:0; transform:translateY(8px); }}
            to {{ opacity:1; transform:translateY(0); }}
        }}

        .doc-meta {{
            display:flex; gap:8px; align-items:center; margin-bottom:14px;
            flex-wrap:wrap;
        }}
        .doc-badge {{
            display:inline-block; padding:4px 14px;
            background:var(--primary-light); color:var(--primary-dark);
            border-radius:14px; font-size:12px; font-weight:700;
            letter-spacing:.3px;
        }}
        .doc-source {{
            font-size:12px; color:#888;
            display:inline-flex; align-items:center; gap:4px;
        }}

        h1 {{
            color:#1a1a2e; font-size:28px; font-weight:800;
            margin-bottom:8px; line-height:1.3;
        }}
        h1::after {{
            content:""; display:block;
            width:60px; height:4px; border-radius:2px;
            background:linear-gradient(90deg,var(--primary),var(--primary-light));
            margin-top:14px;
        }}
        h2 {{
            color:#1a1a2e; font-size:19px; font-weight:700;
            margin-top:32px; padding-left:14px;
            border-left:4px solid var(--primary);
            line-height:1.4;
        }}
        h3 {{
            color:var(--primary-dark); font-size:16px; font-weight:700;
            margin-top:22px; padding-left:12px;
            border-left:3px solid var(--primary-light);
        }}
        p {{
            color:#374151; margin:12px 0 18px;
            line-height:1.85; font-size:15px;
        }}

        .toc {{
            background:#fafafa; border-radius:12px;
            padding:18px 22px; margin-bottom:24px;
            border:1px solid #f0f0f0;
        }}
        .toc-title {{
            font-size:13px; color:#888; font-weight:700;
            margin-bottom:10px; letter-spacing:.5px;
        }}
        .toc ul {{ list-style:none; padding:0; }}
        .toc li {{ margin:6px 0; }}
        .toc a {{
            color:#4b5563; text-decoration:none; font-size:14px;
            padding:4px 0; display:inline-block;
            transition:color .2s;
        }}
        .toc a:hover {{ color:var(--primary); }}
        .toc a::before {{
            content:"•"; color:var(--primary);
            margin-right:8px; font-weight:700;
        }}
    </style>
</head>
<body>
    <div class="topbar">
        <div class="topbar-logo">🚨 On-Call 助手</div>
        <nav class="topbar-nav">
            <a href="/v1/" class="nav-btn {'active' if from_version == 'v1' else ''}">🔍 关键词搜索</a>
            <a href="/v2/" class="nav-btn {'active' if from_version == 'v2' else ''}">🧠 语义搜索</a>
            <a href="/v3/" class="nav-btn {'active' if from_version == 'v3' else ''}">🤖 Agent 对话</a>
        </nav>
    </div>

    <div class="container">
        <div class="breadcrumb">
            <a href="{back_url}">{theme['icon']} {theme['name']}</a>
            <span>›</span>
            <span>{doc_id}</span>
        </div>

        <a class="back-btn" href="{back_url}">← 返回搜索结果</a>

        <div class="card">
            <div class="doc-meta">
                <span class="doc-badge">{doc_id}</span>
                <span class="doc-source">📍 来自 {theme['name']}</span>
            </div>
            <h1>{title}</h1>
            {sections_html}
        </div>
    </div>
</body>
</html>""")

def _get_search_page_html(version: str, description: str) -> str:
    icon = "🔍" if version == "v1" else "🧠"
    color = "#1a73e8" if version == "v1" else "#7c3aed"
    badge = "关键词匹配" if version == "v1" else "AI 语义理解"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>On-Call 助手 — {description}</title>
    <style>
        *{{box-sizing:border-box;margin:0;padding:0}}
        body{{
            font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;
            background:linear-gradient(135deg,#f0f4ff 0%,#faf5ff 100%);
            min-height:100vh; color:#1a1a2e;
        }}
        .topbar{{
            background:white; border-bottom:1px solid #e8eaf6;
            padding:0 32px; height:60px; display:flex; align-items:center;
            justify-content:space-between; box-shadow:0 1px 8px rgba(0,0,0,0.06);
            position:sticky; top:0; z-index:100;
        }}
        .topbar-logo{{font-size:18px;font-weight:700;color:{color};display:flex;align-items:center;gap:8px}}
        .topbar-nav{{display:flex;gap:6px}}
        .nav-btn{{
            padding:6px 14px; border-radius:20px; font-size:13px;
            text-decoration:none; color:#555; transition:all .2s;
        }}
        .nav-btn:hover,.nav-btn.active{{background:{color};color:white}}
        .hero{{
            text-align:center; padding:60px 20px 40px;
        }}
        .hero h1{{font-size:36px;font-weight:800;color:#1a1a2e;margin-bottom:12px}}
        .hero h1 span{{color:{color}}}
        .hero p{{font-size:16px;color:#666;margin-bottom:32px}}
        .badge{{
            display:inline-block; padding:4px 14px;
            background:{color}18; color:{color};
            border-radius:20px; font-size:13px; font-weight:600;
            margin-bottom:24px;
        }}
        .search-wrap{{max-width:700px;margin:0 auto}}
        .search-box{{
            display:flex; gap:10px;
            background:white; border-radius:16px; padding:8px;
            box-shadow:0 4px 24px rgba(0,0,0,0.10);
            border:2px solid transparent; transition:border-color .2s;
        }}
        .search-box:focus-within{{border-color:{color}}}
        .search-box input{{
            flex:1; border:none; outline:none; font-size:16px;
            padding:10px 14px; background:transparent; color:#1a1a2e;
        }}
        .search-box button{{
            padding:10px 28px; background:{color}; color:white;
            border:none; border-radius:10px; font-size:15px;
            cursor:pointer; font-weight:600; transition:all .2s;
            white-space:nowrap;
        }}
        .search-box button:hover{{opacity:.88;transform:translateY(-1px)}}
        .quick-tags{{margin-top:16px;display:flex;flex-wrap:wrap;gap:8px;justify-content:center}}
        .tag{{
            padding:6px 14px; background:white; border:1px solid #e0e0e0;
            border-radius:20px; font-size:13px; cursor:pointer; color:#555;
            transition:all .2s;
        }}
        .tag:hover{{background:{color};color:white;border-color:{color}}}
        .results-section{{max-width:700px;margin:32px auto;padding:0 20px 60px}}
        .result-meta{{
            font-size:13px; color:#888; margin-bottom:16px;
            display:flex; align-items:center; gap:8px;
        }}
        .result-count{{
            background:{color}; color:white; padding:2px 10px;
            border-radius:10px; font-weight:600;
        }}
        .result-card{{
            background:white; border-radius:14px; padding:20px 24px;
            margin-bottom:14px; box-shadow:0 2px 10px rgba(0,0,0,0.06);
            border:1px solid #f0f0f0; transition:all .2s;
            cursor:pointer; text-decoration:none; display:block; color:inherit;
        }}
        .result-card:hover{{
            box-shadow:0 6px 24px rgba(0,0,0,0.12);
            transform:translateY(-2px); border-color:{color}40;
        }}
        .card-header{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px}}
        .card-title{{font-size:17px;font-weight:700;color:#1a1a2e}}
        .card-id{{
            font-size:12px; background:#f1f3f4; color:#666;
            padding:3px 10px; border-radius:10px; white-space:nowrap;
        }}
        .card-snippet{{font-size:14px;color:#555;line-height:1.7;margin-bottom:10px}}
        mark.hl {{
            background: linear-gradient(180deg, transparent 60%, #fef08a 60%);
            color: inherit;
            padding: 0 1px;
            font-weight: 600;
            border-radius: 2px;
        }}
        .card-footer{{display:flex;justify-content:space-between;align-items:center}}
        .card-score{{
            font-size:12px; color:{color}; font-weight:600;
            background:{color}12; padding:2px 10px; border-radius:8px;
        }}
        .card-link{{font-size:13px;color:{color};font-weight:600}}
        .empty{{
            text-align:center; padding:60px 20px; color:#aaa;
        }}
        .empty .icon{{font-size:48px;margin-bottom:12px}}
        .loading{{text-align:center;padding:40px;color:{color}}}
        .spinner{{
            width:32px;height:32px;border:3px solid #e0e0e0;
            border-top-color:{color};border-radius:50%;
            animation:spin .8s linear infinite;margin:0 auto 12px;
        }}
        @keyframes spin{{to{{transform:rotate(360deg)}}}}
    </style>
</head>
<body>
    <div class="topbar">
        <div class="topbar-logo">{icon} On-Call 助手</div>
        <nav class="topbar-nav">
            <a href="/v1/" class="nav-btn {'active' if version=='v1' else ''}">🔍 关键词搜索</a>
            <a href="/v2/" class="nav-btn {'active' if version=='v2' else ''}">🧠 语义搜索</a>
            <a href="/v3/" class="nav-btn">🤖 Agent 对话</a>
        </nav>
    </div>

    <div class="hero">
        <div class="badge">{icon} {badge}</div>
        <h1>On-Call <span>{description}</span></h1>
        <p>快速检索 SOP 文档，精准定位故障处理方案</p>
        <div class="search-wrap">
            <div class="search-box">
                <input type="text" id="queryInput"
                    placeholder="{'输入关键词，如：OOM、CDN、主从延迟...' if version=='v1' else '描述问题，如：服务器挂了、黑客攻击...'}"
                    onkeydown="if(event.key==='Enter')doSearch()"/>
                <button onclick="doSearch()">搜索</button>
            </div>
            <div class="quick-tags">
                {'<span class="tag" onclick="fillAndSearch(this)">OOM</span><span class="tag" onclick="fillAndSearch(this)">故障</span><span class="tag" onclick="fillAndSearch(this)">CDN</span><span class="tag" onclick="fillAndSearch(this)">数据库</span><span class="tag" onclick="fillAndSearch(this)">K8s</span>' if version=='v1' else '<span class="tag" onclick="fillAndSearch(this)">服务器挂了</span><span class="tag" onclick="fillAndSearch(this)">黑客攻击</span><span class="tag" onclick="fillAndSearch(this)">机器学习模型出问题</span><span class="tag" onclick="fillAndSearch(this)">数据库故障</span>'}
            </div>
        </div>
    </div>

    <div class="results-section" id="resultsSection"></div>

    <script>
        const VERSION = "{version}";
        const COLOR = "{color}";

        const urlParams = new URLSearchParams(window.location.search);
        const initialQ = urlParams.get('q');
        if (initialQ !== null) {{
            document.getElementById('queryInput').value = initialQ;
            doSearch();
        }}

        function fillAndSearch(el) {{
            document.getElementById('queryInput').value = el.textContent.trim();
            doSearch();
        }}

        async function doSearch() {{
            const query = document.getElementById('queryInput').value;
            const section = document.getElementById('resultsSection');
            section.innerHTML = '<div class="loading"><div class="spinner"></div>搜索中...</div>';

            // ← 关键：把搜索词写入 URL，浏览器返回时能恢复
            const newUrl = `/${{VERSION}}/?q=${{encodeURIComponent(query)}}`;
            window.history.pushState({{query}}, '', newUrl);

            try {{
                const resp = await fetch(`/${{VERSION}}/search?q=${{encodeURIComponent(query)}}`);
                const data = await resp.json();
                renderResults(data);
            }} catch(e) {{
                section.innerHTML = `<div class="empty"><div class="icon">⚠️</div>搜索出错：${{e.message}}</div>`;
            }}
        }}

        function renderResults(data) {{
            const section = document.getElementById('resultsSection');
            if (!data.results || data.results.length === 0) {{
                section.innerHTML = `<div class="empty"><div class="icon">🔎</div><div>未找到与 "<strong>${{escapeHtml(data.query)}}</strong>" 相关的文档</div></div>`;
                return;
            }}
            let html = `<div class="result-meta">找到 <span class="result-count">${{data.total}}</span> 个相关文档`;
            if (data.took_ms !== undefined) html += `&nbsp;·&nbsp;耗时 ${{data.took_ms}}ms`;
            if (data.mode) html += `&nbsp;·&nbsp;${{escapeHtml(data.mode)}}`;
            html += '</div>';

            const currentQ = document.getElementById('queryInput').value;

            data.results.forEach(r => {{
                // ← 关键修复1：链接带 from 和 q 参数，返回时恢复搜索状态
                const detailUrl = `/v1/documents/${{r.id}}?from=${{VERSION}}&q=${{encodeURIComponent(currentQ)}}`;
                html += `
                <a class="result-card" href="${{detailUrl}}">
                    <div class="card-header">
                        <div class="card-title">${{highlight(r.title, currentQ)}}</div>
                        <div class="card-id">${{r.id}}</div>
                    </div>
                    <div class="card-snippet">${{highlight(r.snippet, currentQ)}}</div>
                    <div class="card-footer">
                        <span class="card-score">相关度 ${{r.score}}</span>
                        <span class="card-link">查看详情 →</span>
                    </div>
                </a>`;
            }});
            section.innerHTML = html;
        }}

        function escapeHtml(s) {{
            if (!s) return '';
            return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
        }}
        
       function highlight(text, query) {{
            if (!text) return '';
            if (!query || !query.trim()) return escapeHtml(text);
            
            // 先转义 HTML 防 XSS
            const escaped = escapeHtml(text);
            
            // 转义正则特殊字符
            const escapedQuery = query.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&');
            
            // 中文不需要 \b 词边界（会失效），直接全局匹配
            try {{
                const re = new RegExp(`(${{escapedQuery}})`, 'gi');
                return escaped.replace(re, '<mark class="hl">$1</mark>');
            }} catch(e) {{
                // 万一正则构造失败（query 全是特殊字符），降级返回普通文本
                return escaped;
            }}
        }}
        
        // ← 关键：监听浏览器前进/后退，恢复搜索状态
        window.addEventListener('popstate', function(e) {{
            const params = new URLSearchParams(window.location.search);
            const q = params.get('q');
            if (q !== null) {{
                document.getElementById('queryInput').value = q;
                doSearch();
            }} else {{
                document.getElementById('resultsSection').innerHTML = '';
                document.getElementById('queryInput').value = '';
            }}
        }});
    </script>
</body>
</html>"""