"""
Phase 3：On-Call Agent 对话
路由前缀：/v3

API:
  POST /v3/chat    发送消息，返回回答 + 工具调用记录
  GET  /v3/        对话前端页面
"""

import logging
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.core.agent import AgentRunner

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Phase3 - Agent 对话"])

agent_runner = AgentRunner()


# ──────────────────────────────────────────
# 数据模型
# ──────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str


# ──────────────────────────────────────────
# API 路由
# ──────────────────────────────────────────

@router.post("/chat")
async def chat(req: ChatRequest):
    """
    Agent 对话接口
    返回：reply + tool_calls + sources + mode
    """
    if not req.message or not req.message.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "message 不能为空"}
        )

    logger.info(f"Agent 收到问题: {req.message[:50]}")

    result = agent_runner.run(req.message)

    return {
        "reply": result.reply,
        "tool_calls": [
            {
                "tool":    tc.tool,
                "input":   tc.input,
                "output":  tc.output,
                "time_ms": tc.time_ms,
            }
            for tc in result.tool_calls
        ],
        "sources": result.sources,
        "mode":    result.mode,
    }


# ──────────────────────────────────────────
# 前端页面
# ──────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def chat_page():
    return HTMLResponse(content=_get_chat_page_html())


def _get_chat_page_html() -> str:
    return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>On-Call 助手 - Agent 对话</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
            background: #f0f2f5;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            background: #1a73e8;
            color: white;
            padding: 16px 24px;
            display: flex;
            align-items: center;
            gap: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        }
        .header h1 { font-size: 20px; }
        .header .subtitle { font-size: 13px; opacity: 0.85; }
        .chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            max-width: 900px;
            width: 100%;
            margin: 0 auto;
        }
        .message { margin-bottom: 20px; }
        .message.user { text-align: right; }
        .bubble {
            display: inline-block;
            max-width: 75%;
            padding: 12px 16px;
            border-radius: 12px;
            line-height: 1.6;
            font-size: 15px;
            text-align: left;
        }
        .user .bubble {
            background: #1a73e8;
            color: white;
            border-bottom-right-radius: 4px;
        }
        .assistant .bubble {
            background: white;
            color: #333;
            border-bottom-left-radius: 4px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.1);
            white-space: pre-wrap;
        }
        .tool-calls {
            margin-top: 10px;
            max-width: 75%;
        }
        .tool-calls summary {
            cursor: pointer;
            color: #1a73e8;
            font-size: 13px;
            padding: 6px 10px;
            background: #e8f0fe;
            border-radius: 6px;
            user-select: none;
        }
        .tool-calls summary:hover { background: #d2e3fc; }
        .tool-call-item {
            background: #f8f9fa;
            border: 1px solid #e0e0e0;
            border-radius: 6px;
            padding: 10px 14px;
            margin-top: 6px;
            font-size: 13px;
        }
        .tool-call-item .tc-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 6px;
        }
        .tc-tool {
            font-weight: 600;
            color: #1a73e8;
            font-family: monospace;
        }
        .tc-time { color: #999; font-size: 12px; }
        .tc-input {
            font-family: monospace;
            background: #e8f0fe;
            padding: 3px 8px;
            border-radius: 4px;
            color: #333;
            margin-bottom: 4px;
        }
        .tc-output {
            color: #555;
            font-size: 12px;
            max-height: 80px;
            overflow: hidden;
            text-overflow: ellipsis;
            border-left: 3px solid #dadce0;
            padding-left: 8px;
        }
        .sources {
            margin-top: 6px;
            font-size: 12px;
            color: #888;
        }
        .mode-badge {
            display: inline-block;
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 10px;
            background: #e8f0fe;
            color: #1a73e8;
            margin-bottom: 8px;
        }
        .input-area {
            background: white;
            border-top: 1px solid #e0e0e0;
            padding: 16px 20px;
        }
        .input-row {
            max-width: 900px;
            margin: 0 auto;
            display: flex;
            gap: 10px;
        }
        textarea {
            flex: 1;
            padding: 12px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 15px;
            font-family: inherit;
            resize: none;
            outline: none;
            line-height: 1.5;
            transition: border-color 0.2s;
            min-height: 50px;
            max-height: 120px;
        }
        textarea:focus { border-color: #1a73e8; }
        button {
            padding: 12px 24px;
            background: #1a73e8;
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 15px;
            cursor: pointer;
            transition: background 0.2s;
            align-self: flex-end;
        }
        button:hover { background: #1557b0; }
        button:disabled { background: #ccc; cursor: not-allowed; }
        .quick-questions {
            max-width: 900px;
            margin: 0 auto 10px;
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        .quick-btn {
            padding: 6px 12px;
            background: white;
            border: 1px solid #dadce0;
            border-radius: 16px;
            font-size: 13px;
            cursor: pointer;
            color: #444;
            transition: all 0.2s;
        }
        .quick-btn:hover {
            background: #e8f0fe;
            border-color: #1a73e8;
            color: #1a73e8;
        }
        .loading-dots span {
            animation: blink 1.4s infinite;
            font-size: 24px;
            color: #1a73e8;
        }
        .loading-dots span:nth-child(2) { animation-delay: 0.2s; }
        .loading-dots span:nth-child(3) { animation-delay: 0.4s; }
        @keyframes blink {
            0%, 80%, 100% { opacity: 0; }
            40% { opacity: 1; }
        }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>🚨 On-Call 助手</h1>
            <div class="subtitle">AI Agent / 基于 SOP 文档的智能问答 / Phase 3</div>
        </div>
    </div>

    <div class="chat-container" id="chatContainer">
        <div class="message assistant">
            <div class="bubble">👋 你好！我是 On-Call 助手。<br><br>
你可以向我提问任何运维相关的问题，我会自动查找相关 SOP 文档并给出处理步骤。<br><br>
💡 <strong>提示：</strong>描述越具体，回答越精准。
            </div>
        </div>
    </div>

    <div class="input-area">
        <div class="quick-questions">
            <button class="quick-btn" onclick="fillQuestion(this)">服务 OOM 了怎么办？</button>
            <button class="quick-btn" onclick="fillQuestion(this)">数据库主从延迟超过30秒怎么处理？</button>
            <button class="quick-btn" onclick="fillQuestion(this)">P0 故障的响应流程是什么？</button>
            <button class="quick-btn" onclick="fillQuestion(this)">怀疑有人入侵了系统</button>
            <button class="quick-btn" onclick="fillQuestion(this)">推荐结果质量下降了</button>
        </div>
        <div class="input-row">
            <textarea
                id="messageInput"
                placeholder="描述你的 On-Call 问题，按 Enter 发送，Shift+Enter 换行..."
                rows="1"
                onkeydown="handleKeydown(event)"
                oninput="autoResize(this)"
            ></textarea>
            <button id="sendBtn" onclick="sendMessage()">发送</button>
        </div>
    </div>

    <script>
        function fillQuestion(btn) {
            document.getElementById("messageInput").value = btn.textContent.trim();
            document.getElementById("messageInput").focus();
        }

        function handleKeydown(e) {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        }

        function autoResize(textarea) {
            textarea.style.height = "auto";
            textarea.style.height = Math.min(textarea.scrollHeight, 120) + "px";
        }

        function escapeHtml(str) {
            if (!str) return "";
            return str.replace(/&/g,"&amp;").replace(/</g,"&lt;")
                      .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
        }

        function scrollToBottom() {
            const c = document.getElementById("chatContainer");
            c.scrollTop = c.scrollHeight;
        }

        function addMessage(role, content) {
            const container = document.getElementById("chatContainer");
            const div = document.createElement("div");
            div.className = `message ${role}`;
            div.innerHTML = `<div class="bubble">${escapeHtml(content)}</div>`;
            container.appendChild(div);
            scrollToBottom();
            return div;
        }

        function addLoadingMessage() {
            const container = document.getElementById("chatContainer");
            const div = document.createElement("div");
            div.className = "message assistant";
            div.id = "loadingMsg";
            div.innerHTML = `<div class="bubble"><span class="loading-dots"><span>●</span><span>●</span><span>●</span></span></div>`;
            container.appendChild(div);
            scrollToBottom();
        }

        function removeLoadingMessage() {
            const el = document.getElementById("loadingMsg");
            if (el) el.remove();
        }

        function renderAssistantMessage(data) {
            const container = document.getElementById("chatContainer");
            const div = document.createElement("div");
            div.className = "message assistant";

            // 工具调用面板
            let toolCallsHtml = "";
            if (data.tool_calls && data.tool_calls.length > 0) {
                const items = data.tool_calls.map(tc => `
                    <div class="tool-call-item">
                        <div class="tc-header">
                            <span class="tc-tool">🔧 ${escapeHtml(tc.tool)}</span>
                            <span class="tc-time">${tc.time_ms}ms</span>
                        </div>
                        <div class="tc-input">📄 ${escapeHtml(tc.input)}</div>
                        <div class="tc-output">${escapeHtml(tc.output)}</div>
                    </div>
                `).join("");

                toolCallsHtml = `
                    <div class="tool-calls">
                        <details>
                            <summary>🔍 工具调用过程（共 ${data.tool_calls.length} 次）</summary>
                            ${items}
                        </details>
                    </div>
                `;
            }

            // 来源文件
            const sourcesHtml = data.sources && data.sources.length > 0
                ? `<div class="sources">📚 参考文档：${data.sources.join(", ")}</div>`
                : "";

            // 模式标签
            const modeHtml = `<div class="mode-badge">⚡ ${escapeHtml(data.mode)}</div>`;

            div.innerHTML = `
                ${modeHtml}
                <div class="bubble">${escapeHtml(data.reply)}</div>
                ${toolCallsHtml}
                ${sourcesHtml}
            `;

            container.appendChild(div);
            scrollToBottom();
        }

        async function sendMessage() {
            const input   = document.getElementById("messageInput");
            const sendBtn = document.getElementById("sendBtn");
            const message = input.value.trim();

            if (!message) return;

            // 显示用户消息
            addMessage("user", message);
            input.value = "";
            input.style.height = "auto";

            // 禁用发送按钮，显示 loading
            sendBtn.disabled = true;
            addLoadingMessage();

            try {
                const response = await fetch("/v3/chat", {
                    method:  "POST",
                    headers: { "Content-Type": "application/json" },
                    body:    JSON.stringify({ message }),
                });

                removeLoadingMessage();

                if (!response.ok) {
                    addMessage("assistant", `请求失败：HTTP ${response.status}`);
                    return;
                }

                const data = await response.json();
                renderAssistantMessage(data);

            } catch (e) {
                removeLoadingMessage();
                addMessage("assistant", `网络错误：${e.message}`);
            } finally {
                sendBtn.disabled = false;
                input.focus();
            }
        }
    </script>
</body>
</html>'''