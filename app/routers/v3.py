"""
Phase 3：On-Call Agent 对话
路由前缀：/v3

API:
  POST /v3/chat    发送消息（支持多轮对话历史），返回回答 + 工具调用记录
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
    history: list[dict] = []   # [{"role": "user/assistant", "content": "..."}]


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

    logger.info(f"Agent 收到问题: {req.message[:50]}（历史轮次: {len(req.history)}）")

    result = agent_runner.run(req.message, history=req.history)

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
    return r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>On-Call 助手 — Agent 对话</title>
    <style>
        *{box-sizing:border-box;margin:0;padding:0}
        html, body{
            font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;
            background:#f0f4ff;
            color:#1a1a2e;
        }
        body{
            display:flex; flex-direction:column;
            min-height:100vh;
        }
        .topbar{
            background:white; border-bottom:1px solid #e8eaf6;
            padding:0 32px; height:60px; display:flex; align-items:center;
            justify-content:space-between; box-shadow:0 1px 8px rgba(0,0,0,0.06);
            flex-shrink:0;
            position:sticky; top:0; z-index:100;
        }
        .topbar-logo{font-size:18px;font-weight:700;color:#059669;display:flex;align-items:center;gap:8px}
        .topbar-nav{display:flex;gap:6px;align-items:center}
        .nav-btn{padding:6px 14px;border-radius:20px;font-size:13px;text-decoration:none;color:#555;transition:all .2s}
        .nav-btn:hover{background:#e8f5e9;color:#059669}
        .nav-btn.active{background:#059669;color:white}
        .clear-btn{
            padding:6px 14px;border-radius:20px;font-size:13px;
            background:#fef2f2;color:#dc2626;border:1px solid #fecaca;
            cursor:pointer;transition:all .2s;margin-left:8px;
        }
        .clear-btn:hover{background:#dc2626;color:white;border-color:#dc2626}
        .chat-container{
            flex:1;
            padding:24px 20px 16px;
            display:flex; flex-direction:column; gap:20px;
            max-width:860px; width:100%; margin:0 auto;
        }
        .msg-row{display:flex;gap:12px;align-items:flex-start}
        .msg-row.user{flex-direction:row-reverse}
        .avatar{
            width:36px;height:36px;border-radius:50%;
            display:flex;align-items:center;justify-content:center;
            font-size:18px;flex-shrink:0;
        }
        .avatar.bot{background:linear-gradient(135deg,#059669,#10b981)}
        .avatar.user{background:linear-gradient(135deg,#1a73e8,#4285f4)}
        .msg-content{
            max-width:78%;
            display:flex;flex-direction:column;gap:8px;
            position:relative;
            padding-right:40px; /* 给复制按钮预留空间 */
        }
        .bubble{
            padding:14px 18px;border-radius:16px;
            font-size:15px;line-height:1.75;
        }
        .user .bubble{
            background:linear-gradient(135deg,#1a73e8,#4285f4);
            color:white;border-top-right-radius:4px;
        }
        .bot .bubble{
            background:white;color:#1a1a2e;
            border-top-left-radius:4px;
            box-shadow:0 2px 10px rgba(0,0,0,0.07);
        }
        .bot .bubble h1,.bot .bubble h2{
            font-size:16px;font-weight:700;color:#059669;
            margin:14px 0 6px;padding-bottom:4px;
            border-bottom:1px solid #d1fae5;
        }
        .bot .bubble h3{font-size:15px;font-weight:700;color:#1a73e8;margin:10px 0 4px}
        .bot .bubble p{margin:6px 0}
        .bot .bubble ul,.bot .bubble ol{padding-left:20px;margin:6px 0}
        .bot .bubble li{margin:3px 0}
        .bot .bubble strong{color:#059669}
        .bot .bubble code{
            background:#f0fdf4;color:#059669;
            padding:1px 6px;border-radius:4px;font-size:13px;
        }
        .bot .bubble pre{
            background:#1e293b;color:#e2e8f0;
            padding:12px 16px;border-radius:8px;
            overflow-x:auto;margin:8px 0;
            font-size:13px;line-height:1.5;
        }
        .bot .bubble pre code{
            background:transparent;color:inherit;
            padding:0;
        }
        .mode-badge{
            display:inline-flex;align-items:center;gap:6px;
            font-size:12px;padding:3px 12px;
            background:#f0fdf4;color:#059669;
            border-radius:12px;font-weight:600;width:fit-content;
        }
        .tool-calls-panel{
            background:#fafafa;border:1px solid #e8eaf6;
            border-radius:12px;overflow:hidden;font-size:13px;
        }
        .tc-header{
            display:flex;align-items:center;justify-content:space-between;
            padding:10px 14px;cursor:pointer;user-select:none;
            background:#f8faff;color:#1a73e8;font-weight:600;
            transition:background .2s;
        }
        .tc-header:hover{background:#e8f0fe}
        .tc-body{display:none;padding:0 14px 12px}
        .tc-body.open{display:block}
        .tc-item{border-top:1px solid #f0f0f0;padding:10px 0}
        .tc-item:first-child{border-top:none}
        .tc-fn{
            font-family:monospace;color:#7c3aed;font-weight:700;font-size:12px;
            margin-bottom:4px;display:flex;justify-content:space-between;
        }
        .tc-arg{
            background:#f3f4f6;border-radius:6px;
            padding:4px 10px;font-family:monospace;
            color:#374151;font-size:12px;margin-bottom:4px;
        }
        .tc-out{
            color:#555;font-size:12px;max-height:70px;
            overflow:hidden;border-left:3px solid #d1d5db;
            padding-left:8px;line-height:1.5;
        }
        .sources-row{display:flex;gap:6px;flex-wrap:wrap}
        .copy-btn {
            position: absolute; top: 0; right: 0;
            background: white; border: 1px solid #e5e7eb;
            border-radius: 8px; padding: 4px 10px;
            font-size: 12px; color: #6b7280; cursor: pointer;
            opacity: 0; transition: all .2s;
            box-shadow: 0 2px 6px rgba(0,0,0,0.05);
            z-index:10;
        }
        .bot .msg-content:hover .copy-btn { opacity: 1; }
        .copy-btn:hover { background: #059669; color: white; border-color: #059669; }
        .copy-btn.copied { background: #10b981; color: white; border-color: #10b981; }
        .source-chip{
            font-size:12px;padding:3px 10px;
            background:#f0fdf4;color:#059669;
            border:1px solid #d1fae5;border-radius:10px;font-weight:600;
        }
        .history-badge{
            font-size:11px;padding:2px 8px;
            background:#fef3c7;color:#92400e;
            border-radius:8px;font-weight:600;
        }
        .input-area{
            background:white;border-top:1px solid #e8eaf6;
            padding:16px 20px;flex-shrink:0;
            position:sticky; bottom:0; z-index:100;
        }
        .quick-bar{
            max-width:860px;margin:0 auto 10px;
            display:flex;flex-wrap:wrap;gap:8px;
        }
        .qbtn{
            padding:6px 14px;background:#f0f4ff;
            border:1px solid #c7d7fd;border-radius:20px;
            font-size:13px;cursor:pointer;color:#1a73e8;
            transition:all .2s;
        }
        .qbtn:hover{background:#1a73e8;color:white;border-color:#1a73e8}
        .input-row{
            max-width:860px;margin:0 auto;
            display:flex;gap:10px;
        }
        textarea{
            flex:1;padding:13px 16px;
            border:2px solid #e8eaf6;border-radius:12px;
            font-size:15px;font-family:inherit;resize:none;
            outline:none;line-height:1.5;transition:border-color .2s;
            min-height:50px;max-height:120px;background:#fafafa;
        }
        textarea:focus{border-color:#059669;background:white}
        .send-btn{
            padding:13px 28px;
            background:linear-gradient(135deg,#059669,#10b981);
            color:white;border:none;border-radius:12px;
            font-size:15px;cursor:pointer;font-weight:600;
            transition:all .2s;align-self:flex-end;
        }
        .send-btn:hover{opacity:.9;transform:translateY(-1px)}
        .send-btn:disabled{background:#ccc;cursor:not-allowed;transform:none}
        
        /* 骨架屏样式 */
        .skeleton {
            background: linear-gradient(90deg, #f0f0f0 25%, #e8e8e8 50%, #f0f0f0 75%);
            background-size: 200% 100%;
            animation: shimmer 1.4s infinite;
            border-radius: 6px;
            height: 14px; margin: 8px 0;
        }
        .skeleton.short { width: 40%; }
        .skeleton.medium { width: 70%; }
        .skeleton.long { width: 90%; }
        .skeleton.title { height: 18px; width: 30%; margin-bottom: 14px; }
        @keyframes shimmer {
            0% { background-position: 200% 0; }
            100% { background-position: -200% 0; }
        }
        .skeleton-status {
            display:flex; align-items:center; gap:8px;
            color:#059669; font-size:13px; font-weight:600;
            margin-bottom:14px;
        }
        .skeleton-status::before {
            content: ""; width: 6px; height: 6px; border-radius: 50%;
            background: #059669; animation: pulse 1s infinite;
        }
        @keyframes pulse {
            0%,100% { opacity: 1; transform: scale(1); }
            50% { opacity: .4; transform: scale(1.4); }
        }

        /* 移动端响应式 */
        @media (max-width: 768px) {
            .topbar { padding: 0 12px; height: 52px; }
            .topbar-logo { font-size: 15px; }
            .topbar-nav { gap: 2px; }
            .nav-btn { padding: 5px 8px; font-size: 11px; }
            .clear-btn { padding: 5px 8px; font-size: 11px; margin-left: 4px; }
            
            .chat-container { padding: 14px 12px; gap: 14px; }
            .msg-content { max-width: 86%; padding-right: 35px; }
            .bubble { padding: 11px 14px; font-size: 14px; }
            .input-area { padding: 10px 12px; }
            .qbtn { font-size: 12px; padding: 5px 10px; }
            .send-btn { padding: 11px 18px; font-size: 14px; }
            .avatar { width: 30px; height: 30px; font-size: 15px; }
            .copy-btn { right: 0; top: -4px; }
        }
    </style>
</head>
<body>
    <div class="topbar">
        <div class="topbar-logo">🤖 On-Call 助手</div>
        <nav class="topbar-nav">
            <a href="/v1/" class="nav-btn">🔍 关键词搜索</a>
            <a href="/v2/" class="nav-btn">🧠 语义搜索</a>
            <a href="/v3/" class="nav-btn active">🤖 Agent 对话</a>
            <button class="clear-btn" onclick="clearHistory()" title="清空对话历史">🗑️ 清空</button>
        </nav>
    </div>

    <div class="chat-container" id="chatContainer">
        <div class="msg-row bot">
            <div class="avatar bot">🤖</div>
            <div class="msg-content">
                <div class="bubble">
                    <strong>👋 你好！我是 On-Call 智能助手</strong><br><br>
                    我会自动查阅相关 SOP 文档，给出精准的故障处理步骤。<br>
                    支持多轮对话，可以追问、要求更详细的步骤、或切换不同的故障场景。<br><br>
                    💡 你可以点击下方快捷问题，或直接描述你遇到的故障。
                </div>
            </div>
        </div>
    </div>

    <div class="input-area">
        <div class="quick-bar">
            <button class="qbtn" onclick="fill(this)">服务 OOM 了怎么办？</button>
            <button class="qbtn" onclick="fill(this)">数据库主从延迟超过30秒怎么处理？</button>
            <button class="qbtn" onclick="fill(this)">P0 故障响应流程</button>
            <button class="qbtn" onclick="fill(this)">怀疑有人入侵了系统</button>
            <button class="qbtn" onclick="fill(this)">推荐结果质量下降了</button>
        </div>
        <div class="input-row">
            <textarea id="msgInput" rows="1"
                placeholder="描述故障或问题，按 Enter 发送，Shift+Enter 换行..."
                onkeydown="handleKey(event)" oninput="resize(this)"></textarea>
            <button class="send-btn" id="sendBtn" onclick="send()">发送</button>
        </div>
    </div>

    <script>
        const MAX_HISTORY = 12;
        const STORAGE_KEY = 'oncall_chat_history_v1';
        const UI_STORAGE_KEY = 'oncall_chat_ui_v1';

        let conversationHistory = [];
        let uiMessages = [];

        // localStorage 工具函数
        function saveToStorage() {
            try {
                localStorage.setItem(STORAGE_KEY, JSON.stringify(conversationHistory));
            } catch(e) {
                console.warn('localStorage 写入失败:', e);
            }
        }

        function loadFromStorage() {
            try {
                const raw = localStorage.getItem(STORAGE_KEY);
                if (raw) {
                    const arr = JSON.parse(raw);
                    if (Array.isArray(arr)) return arr;
                }
            } catch(e) {
                console.warn('localStorage 读取失败:', e);
            }
            return [];
        }

        function saveUIState(uiMessages) {
            try {
                localStorage.setItem(UI_STORAGE_KEY, JSON.stringify(uiMessages));
            } catch(e) {
                console.warn('UI 状态保存失败:', e);
            }
        }

        function loadUIState() {
            try {
                const raw = localStorage.getItem(UI_STORAGE_KEY);
                if (raw) {
                    const arr = JSON.parse(raw);
                    if (Array.isArray(arr)) return arr;
                }
            } catch(e) {
                console.warn('UI 状态读取失败:', e);
            }
            return [];
        }

        function pushHistory(role, content) {
            conversationHistory.push({role, content});
            if (conversationHistory.length > MAX_HISTORY) {
                conversationHistory = conversationHistory.slice(-MAX_HISTORY);
            }
            saveToStorage();
        }

        function clearHistory() {
            if (!confirm('确定要清空对话历史吗？')) return;
            conversationHistory = [];
            uiMessages = [];
            localStorage.removeItem(STORAGE_KEY);
            localStorage.removeItem(UI_STORAGE_KEY);
            const c = document.getElementById('chatContainer');
            c.innerHTML = `
                <div class="msg-row bot">
                    <div class="avatar bot">🤖</div>
                    <div class="msg-content">
                        <div class="bubble">
                            <strong>👋 对话已重置</strong><br><br>
                            可以开始新的话题啦。
                        </div>
                    </div>
                </div>`;
        }

        function fill(el){
            document.getElementById('msgInput').value=el.textContent.trim();
            document.getElementById('msgInput').focus();
        }
        function handleKey(e){
            if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}
        }
        function resize(t){
            t.style.height='auto';
            t.style.height=Math.min(t.scrollHeight,120)+'px';
        }
        function esc(s){
            if(!s)return'';
            return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
        }
        function renderMarkdown(text) {
            if (!text) return '';
            // 先处理多行代码块
            text = text.replace(/```([\s\S]*?)```/g, function(match, code) {
                return '<pre><code>' + esc(code.trim()) + '</code></pre>';
            });
            // 再处理其他markdown
            return text
                .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
                .replace(/^## (.+)$/gm,'<h2>$1</h2>')
                .replace(/^### (.+)$/gm,'<h3>$1</h3>')
                .replace(/^#### (.+)$/gm,'<h4>$1</h4>')
                .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
                .replace(/`([^`]+)`/g,'<code>$1</code>')
                .replace(/^• (.+)$/gm,'<li>$1</li>')
                .replace(/^[\*\-] (.+)$/gm,'<li>$1</li>')
                .replace(/^(\d+)\. (.+)$/gm,'<li>$2</li>')
                .replace(/(<li>.*<\/li>\n?)+/g, s=>`<ul>${s}</ul>`)
                .replace(/\n{2,}/g,'</p><p>')
                .replace(/\n/g,'<br>')
                .replace(/^(?!<[h|u|o|l|p|pre])/,'<p>')
                .replace(/(?<![>])$/,'</p>');
        }
        function scrollBottom(){
            window.scrollTo(0, document.body.scrollHeight);
        }
        function addUser(msg) {
            const c = document.getElementById('chatContainer');
            c.insertAdjacentHTML('beforeend', `
            <div class="msg-row user">
                <div class="avatar user">👤</div>
                <div class="msg-content">
                    <div class="bubble">${esc(msg)}</div>
                </div>
            </div>`);
            scrollBottom();
            pushHistory('user', msg);

            uiMessages.push({type: 'user', content: msg});
            saveUIState(uiMessages);
        }
        
        // 骨架屏加载状态
        function addLoading(){
            const c = document.getElementById('chatContainer');
            c.insertAdjacentHTML('beforeend', `
            <div class="msg-row bot" id="loadingRow">
                <div class="avatar bot">🤖</div>
                <div class="msg-content">
                    <div class="bubble">
                        <div class="skeleton-status">正在查阅 SOP 文档...</div>
                        <div class="skeleton title"></div>
                        <div class="skeleton long"></div>
                        <div class="skeleton long"></div>
                        <div class="skeleton medium"></div>
                        <div class="skeleton short"></div>
                    </div>
                </div>
            </div>`);
            scrollBottom();
        }
        
        function removeLoading(){
            const el=document.getElementById('loadingRow');
            if(el)el.remove();
        }
        
        // 复制回答函数
        async function copyReply(btn, text) {
            try {
                await navigator.clipboard.writeText(text);
                const original = btn.innerHTML;
                btn.classList.add('copied');
                btn.innerHTML = '✓ 已复制';
                setTimeout(() => {
                    btn.classList.remove('copied');
                    btn.innerHTML = original;
                }, 1500);
            } catch(e) {
                // 降级方案
                const ta = document.createElement('textarea');
                ta.value = text;
                document.body.appendChild(ta);
                ta.select();
                try { document.execCommand('copy'); } catch(_) {}
                document.body.removeChild(ta);
                btn.innerHTML = '✓ 已复制';
                setTimeout(() => btn.innerHTML = '📋 复制', 1500);
            }
        }
        
        function addBot(data){
            const c=document.getElementById('chatContainer');

            let tcHtml='';
            if(data.tool_calls&&data.tool_calls.length>0){
                const items=data.tool_calls.map(tc=>`
                    <div class="tc-item">
                        <div class="tc-fn">
                            <span>🔧 ${esc(tc.tool)}("${esc(tc.input)}")</span>
                            <span>${tc.time_ms}ms</span>
                        </div>
                        <div class="tc-out">${esc(tc.output)}</div>
                    </div>`).join('');
                tcHtml=`<div class="tool-calls-panel">
                    <div class="tc-header" onclick="toggleTc(this)">
                        <span>🔍 工具调用（${data.tool_calls.length} 次）</span>
                        <span>▼</span>
                    </div>
                    <div class="tc-body">${items}</div>
                </div>`;
            }

            let srcHtml='';
            if(data.sources&&data.sources.length>0){
                srcHtml='<div class="sources-row">'+
                    data.sources.map(s=>`<span class="source-chip">📄 ${esc(s)}</span>`).join('')+
                '</div>';
            }

            let historyBadge = '';
            if (conversationHistory.length >= 2) {
                const turns = Math.floor(conversationHistory.length / 2);
                historyBadge = `<span class="history-badge">💬 第 ${turns + 1} 轮</span>`;
            }

            c.insertAdjacentHTML('beforeend',`
            <div class="msg-row bot">
                <div class="avatar bot">🤖</div>
                <div class="msg-content">
                    <button class="copy-btn" onclick="copyReply(this, ${JSON.stringify(data.reply || '').replace(/"/g, '&quot;')})">📋 复制</button>
                    <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
                        <div class="mode-badge">⚡ ${esc(data.mode||'本地抽取')}</div>
                        ${historyBadge}
                    </div>
                    <div class="bubble">${renderMarkdown(data.reply||'')}</div>
                    ${tcHtml}
                    ${srcHtml}
                </div>
            </div>`);
            scrollBottom();

            if (data.reply) {
                pushHistory('assistant', data.reply);
            }
            
            uiMessages.push({
                type: 'bot',
                data: {
                    reply: data.reply,
                    tool_calls: data.tool_calls || [],
                    sources: data.sources || [],
                    mode: data.mode || '本地抽取',
                }
            });
            saveUIState(uiMessages);
        }
        function toggleTc(header){
            const body=header.nextElementSibling;
            const arrow=header.querySelector('span:last-child');
            body.classList.toggle('open');
            arrow.textContent=body.classList.contains('open')?'▲':'▼';
        }
        async function send(){
            const input=document.getElementById('msgInput');
            const btn=document.getElementById('sendBtn');
            const msg=input.value.trim();
            if(!msg)return;
            addUser(msg);
            input.value='';input.style.height='auto';
            btn.disabled=true;
            addLoading();
            try{
                const historyToSend = conversationHistory.slice(0, -1);
                const resp=await fetch('/v3/chat',{
                    method:'POST',
                    headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({
                        message: msg,
                        history: historyToSend
                    })
                });
                removeLoading();
                if(!resp.ok){
                    addBot({reply:`请求失败：HTTP ${resp.status}`,tool_calls:[],sources:[],mode:'错误'});
                    return;
                }
                const data=await resp.json();
                addBot(data);
            }catch(e){
                removeLoading();
                addBot({reply:`网络错误：${e.message}`,tool_calls:[],sources:[],mode:'错误'});
            }finally{
                btn.disabled=false;input.focus();
            }
        }
        
        // 页面加载时恢复历史对话
        function restoreHistory() {
            conversationHistory = loadFromStorage();
            uiMessages = loadUIState();

            if (uiMessages.length === 0) return;

            const c = document.getElementById('chatContainer');
            c.innerHTML = `
                <div class="msg-row bot">
                    <div class="avatar bot">🤖</div>
                    <div class="msg-content">
                        <div class="bubble" style="background:#fef3c7;border:1px dashed #fbbf24">
                            <strong>📂 已恢复 ${uiMessages.length} 条历史消息</strong>
                            <span style="float:right;cursor:pointer;color:#92400e;font-size:13px"
                                onclick="clearHistory()">🗑️ 清空重来</span>
                        </div>
                    </div>
                </div>`;

            uiMessages.forEach(item => {
                if (item.type === 'user') {
                    c.insertAdjacentHTML('beforeend', `
                    <div class="msg-row user">
                        <div class="avatar user">👤</div>
                        <div class="msg-content">
                            <div class="bubble">${esc(item.content)}</div>
                        </div>
                    </div>`);
                } else if (item.type === 'bot') {
                    const data = item.data;
                    let tcHtml = '';
                    if (data.tool_calls && data.tool_calls.length > 0) {
                        const items = data.tool_calls.map(tc => `
                            <div class="tc-item">
                                <div class="tc-fn">
                                    <span>🔧 ${esc(tc.tool)}("${esc(tc.input)}")</span>
                                    <span>${tc.time_ms}ms</span>
                                </div>
                                <div class="tc-out">${esc(tc.output)}</div>
                            </div>`).join('');
                        tcHtml = `<div class="tool-calls-panel">
                            <div class="tc-header" onclick="toggleTc(this)">
                                <span>🔍 工具调用（${data.tool_calls.length} 次）</span>
                                <span>▼</span>
                            </div>
                            <div class="tc-body">${items}</div>
                        </div>`;
                    }
                    let srcHtml = '';
                    if (data.sources && data.sources.length > 0) {
                        srcHtml = '<div class="sources-row">' +
                            data.sources.map(s => `<span class="source-chip">📄 ${esc(s)}</span>`).join('') +
                        '</div>';
                    }
                    c.insertAdjacentHTML('beforeend', `
                    <div class="msg-row bot">
                        <div class="avatar bot">🤖</div>
                        <div class="msg-content">
                            <button class="copy-btn" onclick="copyReply(this, ${JSON.stringify(data.reply || '').replace(/"/g, '&quot;')})">📋 复制</button>
                            <div class="mode-badge">⚡ ${esc(data.mode||'本地抽取')}</div>
                            <div class="bubble">${renderMarkdown(data.reply||'')}</div>
                            ${tcHtml}
                            ${srcHtml}
                        </div>
                    </div>`);
                }
            });
            scrollBottom();
        }

        restoreHistory();
    </script>
</body>
</html>"""