# app/routers/v3.py
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Phase3 - Agent 对话"])

@router.get("/", response_class=HTMLResponse)
async def chat_page():
    return HTMLResponse("<h1>Phase 3 Agent 对话 - 开发中</h1>")