"""
Phase 2：语义向量搜索
策略：
  主方案：paraphrase-multilingual-MiniLM-L12-v2 + cosine 相似度
  兜底：TF-IDF char n-gram（模型加载失败时自动切换）

性能优化：
  Embedding 计算结果持久化到 index_cache/，后续启动直接加载
  缓存失效条件：data/ 目录下文件有变化（mtime 检查）
"""

import json
import logging
import time
import numpy as np
from pathlib import Path
from app.core.doc_store import DocStore

logger = logging.getLogger(__name__)

MODELS_DIR   = Path(__file__).parent.parent.parent / "models"
CACHE_DIR    = Path(__file__).parent.parent.parent / "index_cache"
CACHE_FILE   = CACHE_DIR / "vector_cache.npz"
META_FILE    = CACHE_DIR / "vector_meta.json"
MODEL_NAME   = "paraphrase-multilingual-MiniLM-L12-v2"


class VectorIndex:
    def __init__(self):
        self._ready        = False
        self._model        = None
        self._use_fallback = False
        self._chunks: list[dict] = []

        # TF-IDF 兜底
        self._tfidf_vectorizer = None
        self._tfidf_matrix     = None
        self._tfidf_doc_ids:    list[str]        = []
        self._tfidf_doc_titles: dict[str, str]   = {}
        self._tfidf_doc_texts:  dict[str, str]   = {}

    # ──────────────────────────────────────────
    # 构建索引（含缓存加速）
    # ──────────────────────────────────────────

    def build(self, doc_store: DocStore):
        docs = doc_store.get_all_docs()
        if not docs:
            logger.warning("DocStore 为空，跳过向量索引构建")
            return

        try:
            self._load_model()

            # 尝试从缓存加载（加速启动）
            if self._load_cache(docs):
                self._ready        = True
                self._use_fallback = False
                logger.info(
                    f"向量索引从缓存加载完成，共 {len(self._chunks)} 个 chunk"
                )
            else:
                # 缓存不存在或已失效，重新计算
                self._build_embeddings(docs)
                self._save_cache()
                self._ready        = True
                self._use_fallback = False
                logger.info(
                    f"向量索引构建完成（Embedding 模式），共 {len(self._chunks)} 个 chunk"
                )

        except Exception as e:
            logger.warning(f"Embedding 模式失败，切换 TF-IDF 兜底: {e}")
            self._build_tfidf(docs)
            self._ready        = True
            self._use_fallback = True
            logger.info("TF-IDF 兜底索引构建完成")

    def _load_model(self):
        from sentence_transformers import SentenceTransformer
        logger.info(f"加载 Embedding 模型（本地缓存）: {MODEL_NAME}")
        self._model = SentenceTransformer(
            MODEL_NAME,
            cache_folder=str(MODELS_DIR),
            local_files_only=True,   # ← 关键：禁止任何网络请求，只用本地文件
        )
        logger.info("Embedding 模型加载完成")

    # ──────────────────────────────────────────
    # 缓存：保存 / 加载 / 有效性检查
    # ──────────────────────────────────────────

    def _get_data_fingerprint(self, docs: list[dict]) -> dict:
        """
        生成数据指纹：记录每个文档文件的修改时间
        用于判断缓存是否仍然有效
        """
        fingerprint = {}
        for doc in docs:
            path = Path(doc["path"])
            if path.exists():
                fingerprint[doc["id"]] = path.stat().st_mtime
        return fingerprint

    def _load_cache(self, docs: list[dict]) -> bool:
        """
        尝试从磁盘加载缓存
        返回 True 表示缓存有效且加载成功
        返回 False 表示需要重新计算
        """
        if not CACHE_FILE.exists() or not META_FILE.exists():
            logger.info("向量缓存不存在，将重新计算（首次启动）")
            return False

        try:
            meta = json.loads(META_FILE.read_text(encoding="utf-8"))

            # 检查数据指纹是否一致（文件是否有变化）
            current_fingerprint = self._get_data_fingerprint(docs)
            if meta.get("fingerprint") != current_fingerprint:
                logger.info("检测到文档变化，缓存失效，重新计算 Embedding")
                return False

            # 加载 numpy 向量
            cache_data  = np.load(str(CACHE_FILE), allow_pickle=False)
            embeddings  = cache_data["embeddings"]
            chunk_metas = meta["chunks"]

            if len(embeddings) != len(chunk_metas):
                logger.warning("缓存文件损坏（维度不匹配），重新计算")
                return False

            self._chunks = []
            for i, chunk_meta in enumerate(chunk_metas):
                self._chunks.append({
                    **chunk_meta,
                    "embedding": embeddings[i],
                })

            logger.info(f"缓存加载成功，共 {len(self._chunks)} 个 chunk")
            return True

        except Exception as e:
            logger.warning(f"缓存加载失败（{e}），重新计算")
            return False

    def _save_cache(self):
        """将 Embedding 计算结果保存到磁盘"""
        try:
            CACHE_DIR.mkdir(exist_ok=True)

            # 提取向量矩阵
            embeddings = np.array([c["embedding"] for c in self._chunks])

            # 提取元数据（不含 embedding，embedding 单独存 npz）
            chunk_metas = [
                {k: v for k, v in c.items() if k != "embedding"}
                for c in self._chunks
            ]

            # 保存向量
            np.savez_compressed(str(CACHE_FILE), embeddings=embeddings)

            # 保存元数据 + 指纹
            from app.core.doc_store import doc_store
            meta = {
                "chunks":      chunk_metas,
                "fingerprint": self._get_data_fingerprint(
                    doc_store.get_all_docs()
                ),
                "model":       MODEL_NAME,
                "count":       len(self._chunks),
            }
            META_FILE.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            logger.info(f"向量缓存已保存到 {CACHE_DIR}")

        except Exception as e:
            logger.warning(f"缓存保存失败（不影响功能）: {e}")

    def _invalidate_cache(self):
        """主动使缓存失效（新增文档时调用）"""
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
        if META_FILE.exists():
            META_FILE.unlink()
        logger.info("向量缓存已清除，下次重建时重新计算")

    # ──────────────────────────────────────────
    # Embedding 计算
    # ──────────────────────────────────────────

    def _build_embeddings(self, docs: list[dict]):
        self._chunks = []
        all_texts    = []
        chunk_meta   = []

        for doc in docs:
            sections = doc.get("sections", [])
            if not sections:
                sections = [{
                    "heading": doc["title"],
                    "content": doc["clean_text"]
                }]

            for section in sections:
                chunk_text = f"{section['heading']}\n{section['content']}"[:512]
                all_texts.append(chunk_text)
                chunk_meta.append({
                    "doc_id":  doc["id"],
                    "title":   doc["title"],
                    "heading": section["heading"],
                    "content": section["content"][:200],
                })

        logger.info(
            f"开始计算 {len(all_texts)} 个 chunk 的 Embedding"
            f"（batch_size=8，CPU 模式，首次约需 2-5 分钟）..."
        )
        t0 = time.time()

        embeddings = self._model.encode(
            all_texts,
            batch_size=8,
            show_progress_bar=True,
            normalize_embeddings=True,
        )

        elapsed = time.time() - t0
        logger.info(f"Embedding 计算完成，耗时 {elapsed:.1f}秒")

        for i, meta in enumerate(chunk_meta):
            self._chunks.append({
                **meta,
                "embedding": embeddings[i],
            })

    def _build_tfidf(self, docs: list[dict]):
        from sklearn.feature_extraction.text import TfidfVectorizer

        texts = []
        for doc in docs:
            self._tfidf_doc_ids.append(doc["id"])
            self._tfidf_doc_titles[doc["id"]] = doc["title"]
            self._tfidf_doc_texts[doc["id"]]  = doc["clean_text"]
            texts.append(doc["clean_text"])

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
        query_vec = self._model.encode(
            [query],
            normalize_embeddings=True
        )[0]

        chunk_embeddings = np.array([c["embedding"] for c in self._chunks])
        similarities     = np.dot(chunk_embeddings, query_vec)

        doc_chunk_scores:  dict[str, list[float]] = {}
        doc_titles:        dict[str, str]         = {}
        doc_best_snippet:  dict[str, str]         = {}
        doc_best_score:    dict[str, float]       = {}

        for i, chunk in enumerate(self._chunks):
            doc_id = chunk["doc_id"]
            score  = float(similarities[i])

            if doc_id not in doc_chunk_scores:
                doc_chunk_scores[doc_id] = []
                doc_titles[doc_id]       = chunk["title"]
                doc_best_score[doc_id]   = score
                doc_best_snippet[doc_id] = (
                    f"[{chunk['heading']}] {chunk['content']}"
                )

            doc_chunk_scores[doc_id].append(score)

            if score > doc_best_score[doc_id]:
                doc_best_score[doc_id]   = score
                doc_best_snippet[doc_id] = (
                    f"[{chunk['heading']}] {chunk['content']}"
                )

        # 0.7 * max + 0.3 * mean：防止 chunk 多的长文档天然占优
        results = []
        for doc_id, scores in doc_chunk_scores.items():
            max_score   = max(scores)
            mean_score  = sum(scores) / len(scores)
            final_score = 0.7 * max_score + 0.3 * mean_score

            results.append({
                "id":      doc_id,
                "title":   doc_titles[doc_id],
                "snippet": doc_best_snippet[doc_id],
                "score":   round(final_score, 4),
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _search_tfidf(self, query: str, top_k: int) -> list[dict]:
        from sklearn.metrics.pairwise import cosine_similarity

        query_vec = self._tfidf_vectorizer.transform([query])
        scores    = cosine_similarity(query_vec, self._tfidf_matrix)[0]

        results = []
        for idx, score in enumerate(scores):
            if score > 0:
                doc_id = self._tfidf_doc_ids[idx]
                text   = self._tfidf_doc_texts[doc_id]
                results.append({
                    "id":      doc_id,
                    "title":   self._tfidf_doc_titles[doc_id],
                    "snippet": text[:200].replace("\n", " ") + "...",
                    "score":   round(float(score), 4),
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    # ──────────────────────────────────────────
    # 动态添加文档
    # ──────────────────────────────────────────

    def add_document(self, doc: dict):
        if not self._ready:
            return

        if self._use_fallback:
            from app.core.doc_store import doc_store
            self._build_tfidf(doc_store.get_all_docs())
            return

        # 增量编码新文档
        sections = doc.get("sections", [])
        if not sections:
            sections = [{"heading": doc["title"], "content": doc["clean_text"]}]

        new_texts = []
        new_meta  = []
        for section in sections:
            chunk_text = f"{section['heading']}\n{section['content']}"[:512]
            new_texts.append(chunk_text)
            new_meta.append({
                "doc_id":  doc["id"],
                "title":   doc["title"],
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

        # 新文档加入后使旧缓存失效，下次重建时保存新缓存
        self._invalidate_cache()

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