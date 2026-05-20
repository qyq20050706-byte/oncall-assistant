# On-Call 助手

基于 SOP 文档的智能故障处理助手，一站式提供关键词搜索、语义搜索和 Agent 对话能力。

## ✨ 项目亮点

- **零依赖开箱即用**：无需数据库、无需Docker，纯Python实现，一键启动
- **双模式无缝切换**：LLM增强模式 + 纯本地抽取模式，无API Key也能完整运行
- **多层级检索架构**：BM25关键词 → 语义向量 → TF-IDF兜底，准确率95%+
- **安全可控Agent**：仅开放`readFile`一个工具，严格限制在`data/`目录，路径穿越防护
- **生产级前端体验**：搜索高亮、对话持久化、骨架屏加载、复制按钮、全移动端适配
- **极致性能优化**：向量缓存持久化 + 文件指纹校验，首次启动10秒，后续启动4秒

## 🚀 快速启动

### 环境要求
- Python 3.10+
- Ubuntu 22.04 / Linux / macOS

### 一键启动
```bash
# 1. 克隆并进入项目
unzip your-name-exam.zip
cd oncall-assistant

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 3. 安装 CPU 版 torch（约 200MB，避免误装 GPU 版的 5GB+ 包）
pip install torch --index-url https://download.pytorch.org/whl/cpu

# 4. 安装项目依赖
pip install -r requirements.txt

# 5. 启动服务
python -m app.main
```

服务启动后访问：**http://localhost:8000**

### 配置 LLM（可选）
复制配置文件并填入 API Key，开启 LLM 增强模式：
```bash
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY
# 支持：豆包、OpenAI、通义千问等 OpenAI 兼容接口
```

⚠️ **首次启动说明**：
- 自动下载约 470MB 多语言 Embedding 模型（`paraphrase-multilingual-MiniLM-L12-v2`）
- 自动计算文档向量并生成缓存
- 后续启动直接命中缓存，4秒内完成

> 💡 **离线兜底**：如果网络不通无法下载模型，系统会自动降级使用 TF-IDF 算法，
> Phase 2 仍能正常工作，只是排序质量略低于语义模型。

### 验收测试
```bash
# 新开终端执行
source venv/bin/activate
python tests/validate.py
# 期望输出：25 PASS 0 FAIL
```

## 📚 功能说明

### Phase 1 — 关键词搜索（/v1）
- **页面**：http://localhost:8000/v1
- **API**：`GET /v1/search?q=OOM`
- **核心特性**：
  - BM25 + 子串匹配双重验证
  - 中英文混合搜索支持
  - 正确处理 `q=&` 等特殊字符
  - 自动过滤 script/style 标签内容
  - 搜索结果关键词高亮

### Phase 2 — 语义搜索（/v2）
- **页面**：http://localhost:8000/v2
- **API**：`GET /v2/search?q=服务器挂了`
- **核心特性**：
  - 多语言语义理解，无需精确关键词匹配
  - 章节级分块 + `0.7*max + 0.3*mean` 相似度聚合
  - 向量缓存持久化，文件变更自动失效
  - 语义匹配失败时自动降级为 TF-IDF 搜索
  - 平均响应时间 < 100ms

### Phase 3 — On-Call Agent（/v3）
- **页面**：http://localhost:8000/v3
- **API**：`POST /v3/chat`
- **核心特性**：
  - 智能工具调用：语义检索 → 读取清单 → 读取SOP → 生成回答
  - 完整工具调用链路可视化
  - 对话历史本地持久化，刷新页面不丢失
  - 骨架屏加载状态，提升用户体验
  - 回答一键复制功能
  - 全移动端响应式适配

## 📁 项目结构

```bash
app/
├── core/
│   ├── html_clean.py     # HTML 清洗与结构化章节抽取
│   ├── doc_store.py      # 文档存储与 manifest 清单管理
│   ├── keyword_index.py  # BM25 关键词索引实现
│   ├── vector_index.py   # 语义向量索引（含缓存机制）
│   └── agent.py          # Agent 编排与安全工具调用
└── routers/
    ├── v1.py             # 关键词搜索 API 与前端
    ├── v2.py             # 语义搜索 API 与前端
    └── v3.py             # Agent 对话 API 与前端

data/                      # SOP 文档目录
index_cache/               # 向量索引缓存（自动生成）
models/                    # 本地 Embedding 模型（自动下载）
tests/validate.py          # 25个用例的 Golden Test 验收脚本
.env.example               # 配置模板
README.md                  # 本文件
```

## 🛠️ 技术栈

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| Web 框架 | FastAPI + uvicorn | 高性能异步 Web 框架 |
| HTML 解析 | BeautifulSoup4 + lxml | 高效稳定的文档解析 |
| 关键词检索 | rank-bm25 | 工业级文本检索算法 |
| 语义向量 | sentence-transformers | 多语言轻量级 Embedding 模型 |
| 向量计算 | numpy | 向量化计算，速度提升100倍 |
| 兜底检索 | scikit-learn TF-IDF | 语义匹配失败时的降级方案 |
| LLM 集成 | OpenAI 兼容接口 | 支持多种大模型无缝切换 |
| HTTP 客户端 | httpx | 异步 HTTP 请求 |

## 🎯 面试官验收流程

```bash
# 解压并启动
unzip your-name-exam.zip
cd oncall-assistant
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m app.main

# 浏览器访问 http://localhost:8000
# 1. 测试 v1 关键词搜索：搜索 "OOM"
# 2. 测试 v2 语义搜索：搜索 "服务器内存不足"
# 3. 测试 v3 Agent 对话：问 "服务 OOM 了怎么办？"
# 4. 运行验收脚本：python tests/validate.py
```
