"""
FastAPI 应用入口
- 挂载 /v1 /v2 /v3 路由
- 启动时初始化 DocStore、关键词索引、向量索引
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware  # ← 大写 M

from app.core.doc_store import doc_store
from app.core.keyword_index import keyword_index
from app.routers import v1, v2, v3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 50)
    logger.info("On-Call 助手启动中...")

    logger.info("Step 1/3: 加载 SOP 文档...")
    doc_store.load_all()
    logger.info(f"已加载 {len(doc_store.get_all_ids())} 个文档")

    logger.info("Step 2/3: 构建关键词索引 (BM25)...")
    keyword_index.build(doc_store)
    logger.info("关键词索引构建完成")

    logger.info("Step 3/3: 初始化语义向量索引...")
    try:
        from app.core.vector_index import vector_index
        vector_index.build(doc_store)
        logger.info(f"向量索引构建完成（模式: {vector_index.mode}）")
    except Exception as e:
        logger.warning(f"向量索引构建失败: {e}")

    logger.info("On-Call 助手启动成功 🚀")
    logger.info("=" * 50)

    yield
    logger.info("On-Call 助手关闭")


app = FastAPI(
    title="On-Call 助手",
    description="基于 SOP 文档的 On-Call 智能助手",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,        # ← 大写 M
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1.router, prefix="/v1")
app.include_router(v2.router, prefix="/v2")
app.include_router(v3.router, prefix="/v3")


@app.get("/")
async def root():
    return {
        "service": "On-Call 助手",
        "phases": {
            "v1": "/v1 - 关键词搜索引擎",
            "v2": "/v2 - 语义搜索",
            "v3": "/v3 - On-Call Agent 对话",
        },
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )