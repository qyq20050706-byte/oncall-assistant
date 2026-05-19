"""
Phase 2：语义向量搜索（占位）
Phase 2 阶段会完整实现
"""

from app.core.doc_store import DocStore


class VectorIndex:
    def __init__(self):
        self._ready = False

    def build(self, doc_store: DocStore):
        """Phase 2 完整实现"""
        self._ready = False

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """Phase 2 完整实现"""
        return []


# 全局单例
vector_index = VectorIndex()