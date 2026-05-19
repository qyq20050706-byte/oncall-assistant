"""
Phase 2：语义搜索
路由前缀：/v2

API:
  GET /v2/search?q=xxx   语义搜索（不需要关键词精确匹配）
  GET /v2                搜索页面
"""
import time
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.core.vector_index import vector_index
from app.routers.v1 import _parse_query_param, _get_search_page_html

router = APIRouter(tags=["Phase2 - 语义搜索"])


@router.get("/search")
async def search(request: Request):
    raw_query_string = str(request.url.query)
    query = _parse_query_param(raw_query_string)

    start_time = time.time()
    results = vector_index.search(query)
    took_ms = round((time.time() - start_time) * 1000, 2)

    return {
        "query": query,
        "results": results,
        "total": len(results),
        "mode": vector_index.mode,
        "took_ms": took_ms,
    }


@router.get("/", response_class=HTMLResponse)
async def search_page():
    """Phase 2 语义搜索页面（复用 v1 模板，路径指向 /v2）"""
    return HTMLResponse(content=_get_search_page_html("v2", "语义搜索"))