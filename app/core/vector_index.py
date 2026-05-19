"""
Phase 2：语义向量搜索
策略：
  主方案：paraphrase-multilingual-MiniLM-L12-v2 + cosine 相似度
  兜底：TF-IDF char n-gram（模型加载失败时自动切换）

分块策略：按 h2/h3 章节分块（复用 extract_sections）
聚合策略：0.7 * max_chunk_score + 0.3 * mean_chunk_score
  → 防止 chunk 数量多的长文档天然占优
"""

import logging
import numpy as np
from pathlib import Path
from app.core.doc_store import DocStore

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent.parent.parent / "models"
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


class VectorIndex:
    def __init__(self):
        self._ready = False
        self._model = None
        self._use_fallback = False

        # Embedding 模式存储
        # 每个 chunk: {doc_id, title, heading, content(snippet), embedding}
        self._chunks: list[dict] = []

        # TF-IDF 兜底存储
        self._tfidf_vectorizer = None
        self._tfidf_matrix = None
        self._tfidf_doc_ids: list[str] = []
        self._tfidf_doc_titles: dict[str, str] = {}
        self._tfidf_doc_texts: dict[str, str] = {}

    # ──────────────────────────────────────────
    # 构建索引
    # ──────────────────────────────────────────

    def build(self, doc_store: DocStore):
        """
        构建向量索引
        优先 Embedding，失败则自动退化到 TF-IDF
        """
        docs = doc_store.get_all_docs()
        if not docs:
            logger.warning("DocStore 为空，跳过向量索引构建")
            return

        try:
            self._load_model()
            self._build_embeddings(docs)
            self._ready = True
            self._use_fallback = False
            logger.info(
                f"向量索引构建完成（Embedding 模式）"
                f"，共 {len(self._chunks)} 个 chunk"
            )
        except Exception as e:
            logger.warning(f"Embedding 模型加载失败，切换 TF-IDF 兜底: {e}")
            self._build_tfidf(docs)
            self._ready = True
            self._use_fallback = True
            logger.info("TF-IDF 兜底索引构建完成")

    def _load_model(self):
        from sentence_transformers import SentenceTransformer
        logger.info(f"加载 Embedding 模型（本地缓存）: {MODEL_NAME}")
        self._model = SentenceTransformer(
            MODEL_NAME,
            cache_folder=str(MODELS_DIR)
        )
        logger.info("Embedding 模型加载成功")

    def _build_embeddings(self, docs: list[dict]):
        """为所有文档的章节块生成向量"""
        self._chunks = []
        all_texts = []
        chunk_meta = []

        for doc in docs:
            sections = doc.get("sections", [])

            # 若无章节结构，整体作为单一 chunk
            if not sections:
                sections = [{
                    "heading": doc["title"],
                    "content": doc["clean_text"]
                }]

            for section in sections:
                # heading + content 拼接，限制长度不超过模型 max_seq_length
                chunk_text = f"{section['heading']}\n{section['content']}"
                chunk_text = chunk_text[:512]

                all_texts.append(chunk_text)
                chunk_meta.append({
                    "doc_id": doc["id"],
                    "title": doc["title"],
                    "heading": section["heading"],
                    "content": section["content"][:200],  # 仅用于 snippet
                })

        logger.info(f"开始编码 {len(all_texts)} 个 chunk...")

        # 批量 encode + L2 归一化（归一化后 dot product = cosine，速度更快）
        embeddings = self._model.encode(
            all_texts,
            batch_size=8,          # ← 从 32 改为 8，降低内存峰值
            show_progress_bar=True, # ← 改为 True，便于观察进度
            normalize_embeddings=True,
            )

        for i, meta in enumerate(chunk_meta):
            self._chunks.append({
                **meta,
                "embedding": embeddings[i],
            })

    def _build_tfidf(self, docs: list[dict]):
        """TF-IDF 兜底索引（字符 n-gram，无需分词，天然支持中文）"""
        from sklearn.feature_extraction.text import TfidfVectorizer

        texts = []
        for doc in docs:
            self._tfidf_doc_ids.append(doc["id"])
            self._tfidf_doc_titles[doc["id"]] = doc["title"]
            self._tfidf_doc_texts[doc["id"]] = doc["clean_text"]
            texts.append(doc["clean_text"])

        # char_wb: 字符级 n-gram，对中文效果好
        self._tfidf_vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 4),
            max_features=50000,
        )
        self._tfidf_matrix = self._tfidf_vectorizer.fit_transform(texts)

    # ──────────────────────────────────────────
    # 搜索
    # ──────────────────────────────────────────

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        if not query or not query.strip():
            return []
        if not self._ready:
            return []
        if self._use_fallback:
            return self._search_tfidf(query, top_k)
        return self._search_embedding(query, top_k)

    def _search_embedding(self, query: str, top_k: int) -> list[dict]:
        """Embedding 语义搜索 + 章节聚合"""

        # 1. 编码查询向量（归一化）
        query_vec = self._model.encode(
            [query],
            normalize_embeddings=True
        )[0]

        # 2. 批量 cosine 相似度（归一化后 = dot product）
        chunk_embeddings = np.array([c["embedding"] for c in self._chunks])
        similarities = np.dot(chunk_embeddings, query_vec)  # shape: (N,)

        # 3. 按 doc 聚合
        doc_chunk_scores: dict[str, list[float]] = {}
        doc_titles: dict[str, str] = {}
        doc_best_snippet: dict[str, str] = {}
        doc_best_score: dict[str, float] = {}

        for i, chunk in enumerate(self._chunks):
            doc_id = chunk["doc_id"]
            score = float(similarities[i])

            if doc_id not in doc_chunk_scores:
                doc_chunk_scores[doc_id] = []
                doc_titles[doc_id] = chunk["title"]
                doc_best_score[doc_id] = score
                doc_best_snippet[doc_id] = (
                    f"[{chunk['heading']}] {chunk['content']}"
                )

            doc_chunk_scores[doc_id].append(score)

            # 保留分数最高 chunk 的 snippet
            if score > doc_best_score[doc_id]:
                doc_best_score[doc_id] = score
                doc_best_snippet[doc_id] = (
                    f"[{chunk['heading']}] {chunk['content']}"
                )

        # 4. 最终得分：0.7 * max + 0.3 * mean
        #    防止 chunk 数量多的长文档天然占优
        results = []
        for doc_id, scores in doc_chunk_scores.items():
            max_score = max(scores)
            mean_score = sum(scores) / len(scores)
            final_score = 0.7 * max_score + 0.3 * mean_score

            results.append({
                "id": doc_id,
                "title": doc_titles[doc_id],
                "snippet": doc_best_snippet[doc_id],
                "score": round(final_score, 4),
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _search_tfidf(self, query: str, top_k: int) -> list[dict]:
        """TF-IDF 兜底搜索"""
        from sklearn.metrics.pairwise import cosine_similarity

        query_vec = self._tfidf_vectorizer.transform([query])
        scores = cosine_similarity(query_vec, self._tfidf_matrix)[0]

        results = []
        for idx, score in enumerate(scores):
            if score > 0:
                doc_id = self._tfidf_doc_ids[idx]
                text = self._tfidf_doc_texts[doc_id]
                results.append({
                    "id": doc_id,
                    "title": self._tfidf_doc_titles[doc_id],
                    "snippet": text[:200].replace("\n", " ") + "...",
                    "score": round(float(score), 4),
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    # ──────────────────────────────────────────
    # 动态添加文档（POST /v1/documents 触发）
    # ──────────────────────────────────────────

    def add_document(self, doc: dict):
        """
        动态添加单个文档到向量索引
        仅 Embedding 模式有效；TF-IDF 模式下需全量重建（数据量小，可接受）
        """
        if not self._ready:
            return

        if self._use_fallback:
            # TF-IDF 全量重建
            from app.core.doc_store import doc_store
            self._build_tfidf(doc_store.get_all_docs())
            return

        # Embedding 模式：只增量编码新文档的 chunks
        sections = doc.get("sections", [])
        if not sections:
            sections = [{"heading": doc["title"], "content": doc["clean_text"]}]

        new_texts = []
        new_meta = []
        for section in sections:
            chunk_text = f"{section['heading']}\n{section['content']}"[:512]
            new_texts.append(chunk_text)
            new_meta.append({
                "doc_id": doc["id"],
                "title": doc["title"],
                "heading": section["heading"],
                "content": section["content"][:200],
            })

        new_embeddings = self._model.encode(
            new_texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        for i, meta in enumerate(new_meta):
            self._chunks.append({**meta, "embedding": new_embeddings[i]})

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def mode(self) -> str:
        if not self._ready:
            return "未初始化"
        return "TF-IDF 兜底" if self._use_fallback else "Embedding 语义"


# 全局单例
vector_index = VectorIndex()