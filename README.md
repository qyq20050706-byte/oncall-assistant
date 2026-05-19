**以下是一个可直接复制粘贴的 **`**README.md**`** 文件，已整合所有安全规范和细节调整，确保完整且符合提交标准：**

```markdown
# On-Call 助手

基于 SOP 文档的 On-Call 智能助手，支持关键词搜索、语义搜索和 Agent 对话三个阶段。

## 快速启动

### 环境要求
- Python 3.10+
- Ubuntu 22.04 / Linux（推荐）

### 安装依赖
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 配置（可选）

复制配置文件并填入 LLM API Key（**不填也能运行**，系统会自动切换为本地抽取模式）：

```bash
cp .env.example .env
# 编辑 .env，填入你的 LLM_API_KEY（⚠️ 重要：.env 文件已加入 .gitignore，不会提交到仓库）
```

### 启动服务

```bash
# 在项目根目录执行
source venv/bin/activate
python -m app.main
```

服务启动后访问：http://localhost:8000

⚠️ **首次启动**：  
- 会自动下载约 118MB 的 Embedding 模型（`paraphrase-multilingual-MiniLM-L12-v2`），请确保网络通畅  
- 之后计算向量并缓存，约 10 秒  
⚡ **后续启动**：缓存命中，约 4 秒完成

### 验收测试

```bash
# 保持服务运行，新开终端执行
source venv/bin/activate
python tests/validate.py
# 期望：25 PASS 0 FAIL
```

## 功能说明

### Phase 1 — 关键词搜索（/v1）

- 页面：http://localhost:8000/v1
- API：`GET /v1/search?q=OOM`
- 添加文档：`POST /v1/documents`

**特性：**

- BM25 + substring 双重验证
- 支持中英文混合搜索
- 正确处理 `q=&` 等特殊字符
- script/style 标签内容不参与检索

### Phase 2 — 语义搜索（/v2）

- 页面：http://localhost:8000/v2
- API：`GET /v2/search?q=服务器挂了`

**特性：**

- `paraphrase-multilingual-MiniLM-L12-v2` 多语言 Embedding
- 查询词无需精确出现在文档中
- 章节级分块 + `0.7*max + 0.3*mean` 聚合
- 向量缓存持久化，文件指纹校验自动失效
- TF-IDF char n-gram 自动兜底

### Phase 3 — On-Call Agent（/v3）

- 页面：http://localhost:8000/v3
- API：`POST /v3/chat`

**特性：**

- 只使用 `readFile(fname)` 一个工具
- 只能读取 `data/` 目录，路径穿越防护
- 对话过程展示完整工具调用链路
- 语义检索定位 → `readFile manifest` → `readFile SOP` → 生成回答
- LLM 增强（豆包 API）+ 本地抽取双模式

## 项目结构

```bash
app/core/html_clean.py     # HTML 清洗与章节抽取
app/core/doc_store.py      # 文档存储与 manifest 管理
app/core/keyword_index.py  # BM25 关键词索引
app/core/vector_index.py   # 语义向量索引（含缓存）
app/core/agent.py          # Agent 编排与 readFile 工具
app/routers/v1.py          # Phase 1 API
app/routers/v2.py          # Phase 2 API
app/routers/v3.py          # Phase 3 API
data/                      # SOP 文档目录
models/                    # 本地 Embedding 模型
index_cache/               # 向量缓存（自动生成）
tests/validate.py          # Golden Test 验收脚本
screenshot/                # 功能截图目录
prompt/                    # 对话截图目录
.env.example               # 配置模板（已忽略提交）
README.md                  # 本项目说明
```

## 技术栈

| 组件 | 技术 |
| ------ |------ |
| Web 框架 | FastAPI + uvicorn |
| HTML 解析 | BeautifulSoup4 + lxml |
| 关键词检索 | rank-bm25 |
| 语义向量 | sentence-transformers（multilingual-MiniLM） |
| 向量计算 | numpy（cosine 相似度） |
| TF-IDF 兜底 | scikit-learn |
| LLM | 豆包 API（OpenAI 兼容接口） |
| HTTP 客户端 | httpx |

## 面试官验收一键流程

```bash
# 面试官收到 zip 后只需执行：
unzip your-name-exam.zip
cd oncall-assistant
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m app.main
# 访问 http://localhost:8000 进行验收
```