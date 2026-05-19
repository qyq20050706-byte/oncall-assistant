# app/routers/v2.py
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Phase2 - 语义搜索"])

@router.get("/", response_class=HTMLResponse)
async def search_page():
    return HTMLResponse("<h1>Phase 2 语义搜索 - 开发中</h1>")

@router.get("/search")
async def search(q: str = ""):
    return {"query": q, "results": [], "message": "Phase 2 开发中"}