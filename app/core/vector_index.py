"""
Phase 2：语义向量搜索

策略：
  主方案：paraphrase-multilingual-MiniLM-L12-v2 + cosine
  兜底：TF-IDF char n-gram

性能优化：
  - Embedding 计算结果持久化到 index_cache/
  - 缓存指纹用 mtime + size，自动失效
  - chunk 矩阵在 build 时缓存为单个 ndarray，避免每次 search 重建
  - 缓存写入用 .tmp + rename，原子操作
"""

import os
import json
import logging
import time
import numpy as np
from pathlib import Path
from app.core.doc_store import DocStore

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent.parent.parent / "models"
CACHE_DIR  = Path(__file__).parent.parent.parent / "index_cache"
CACHE_FILE = CACHE_DIR / "vector_cache.npz"
META_FILE  = CACHE_DIR / "vector_meta.json"
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


class VectorIndex:
    def __init__(self):
        self._ready        = False
        self._model        = None
        self._use_fallback = False
        self._chunks: list[dict] = []
        self._chunk_matrix: np.ndarray | None = None  # ← 新增：预计算矩阵

        # TF-IDF 兜底
        self._tfidf_vectorizer = None
        self._tfidf_matrix     = None
        self._tfidf_doc_ids:    list[str]      = []
        self._tfidf_doc_titles: dict[str, str] = {}
        self._tfidf_doc_texts:  dict[str, str] = {}

    # ──────────────────────────────────────────
    # 构建索引
    # ──────────────────────────────────────────

    def build(self, doc_store: DocStore):
        docs = doc_store.get_all_docs()
        if not docs:
            logger.warning("DocStore 为空，跳过向量索引构建")
            return

        try:
            self._load_model()

            if self._load_cache(docs):
                self._rebuild_matrix()
                self._ready, self._use_fallback = True, False
                logger.info(f"向量索引从缓存加载完成，共 {len(self._chunks)} 个 chunk")
            else:
                self._build_embeddings(docs)
                self._rebuild_matrix()
                self._save_cache()
                self._ready, self._use_fallback = True, False
                logger.info(f"向量索引构建完成（Embedding 模式），共 {len(self._chunks)} 个 chunk")

        except Exception as e:
            logger.warning(f"Embedding 模式失败，切换 TF-IDF 兜底: {e}")
            self._build_tfidf(docs)
            self._ready, self._use_fallback = True, True
            logger.info("TF-IDF 兜底索引构建完成")

    def _load_model(self):
        from sentence_transformers import SentenceTransformer
        import inspect

        logger.info(f"加载 Embedding 模型: {MODEL_NAME}")

        # 检测当前 SentenceTransformer 是否支持 local_files_only 参数
        # 新版（5.x+）已移除该参数
        sig = inspect.signature(SentenceTransformer.__init__)
        supports_local_only = "local_files_only" in sig.parameters

        # 优先离线加载
        try:
            os.environ["HF_HUB_OFFLINE"] = "1"
            kwargs = {"cache_folder": str(MODELS_DIR)}
            if supports_local_only:
                kwargs["local_files_only"] = True
            self._model = SentenceTransformer(MODEL_NAME, **kwargs)
            logger.info("Embedding 模型加载完成（本地缓存）")
            return
        except Exception as e:
            logger.info(f"本地未找到模型缓存，尝试在线下载: {e}")

        # 离线失败，转在线下载
        os.environ.pop("HF_HUB_OFFLINE", None)
        try:
            self._model = SentenceTransformer(MODEL_NAME, cache_folder=str(MODELS_DIR))
            logger.info("Embedding 模型加载完成（在线下载）")
        except Exception as e:
            logger.warning(f"在线下载也失败（{e}），将使用 TF-IDF 兜底")
            raise

    def _rebuild_matrix(self):
        """从 self._chunks 重建 ndarray 矩阵（search 直接复用）"""
        if self._chunks:
            self._chunk_matrix = np.array([c["embedding"] for c in self._chunks])
        else:
            self._chunk_matrix = None

    # ──────────────────────────────────────────
    # 缓存
    # ──────────────────────────────────────────

    def _get_data_fingerprint(self, docs: list[dict]) -> dict:
        fingerprint = {}
        for doc in docs:
            path = Path(doc["path"])
            if path.exists():
                st = path.stat()
                fingerprint[doc["id"]] = {"mtime": st.st_mtime, "size": st.st_size}
        return fingerprint

    def _load_cache(self, docs: list[dict]) -> bool:
        if not CACHE_FILE.exists() or not META_FILE.exists():
            logger.info("向量缓存不存在，将重新计算（首次启动）")
            return False
        try:
            meta = json.loads(META_FILE.read_text(encoding="utf-8"))
            if meta.get("model") != MODEL_NAME:
                logger.info("缓存的模型与当前不一致，重新计算")
                return False
            current_fp = self._get_data_fingerprint(docs)
            if meta.get("fingerprint") != current_fp:
                logger.info("检测到文档变化，缓存失效，重新计算 Embedding")
                return False

            cache_data  = np.load(str(CACHE_FILE), allow_pickle=False)
            embeddings  = cache_data["embeddings"]
            chunk_metas = meta["chunks"]

            if len(embeddings) != len(chunk_metas):
                logger.warning("缓存文件维度不匹配，重新计算")
                return False

            self._chunks = [
                {**chunk_metas[i], "embedding": embeddings[i]}
                for i in range(len(chunk_metas))
            ]
            logger.info(f"缓存加载成功，共 {len(self._chunks)} 个 chunk")
            return True
        except Exception as e:
            logger.warning(f"缓存加载失败（{e}），重新计算")
            return False

    def _save_cache(self):
        try:
            CACHE_DIR.mkdir(exist_ok=True)
            embeddings = np.array([c["embedding"] for c in self._chunks])
            chunk_metas = [
                {k: v for k, v in c.items() if k != "embedding"}
                for c in self._chunks
            ]
            from app.core.doc_store import doc_store
            meta = {
                "chunks":      chunk_metas,
                "fingerprint": self._get_data_fingerprint(doc_store.get_all_docs()),
                "model":       MODEL_NAME,
                "count":       len(self._chunks),
            }

            # 原子写入：tmp → rename
            tmp_npz  = CACHE_FILE.with_name(CACHE_FILE.stem + ".tmp.npz")
            tmp_meta = META_FILE.with_name(META_FILE.stem + ".tmp.json")
            np.savez_compressed(str(tmp_npz), embeddings=embeddings)
            tmp_meta.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_npz.replace(CACHE_FILE)
            tmp_meta.replace(META_FILE)

            logger.info(f"向量缓存已保存到 {CACHE_DIR}")
        except Exception as e:
            logger.warning(f"缓存保存失败（不影响功能）: {e}")

    # ──────────────────────────────────────────
    # Embedding 计算
    # ──────────────────────────────────────────

    def _build_embeddings(self, docs: list[dict]):
        self._chunks = []
        all_texts, chunk_meta = [], []

        for doc in docs:
            sections = doc.get("sections", []) or [
                {"heading": doc["title"], "content": doc["clean_text"]}
            ]
            for section in sections:
                chunk_text = f"{section['heading']}\n{section['content']}"[:512]
                all_texts.append(chunk_text)
                chunk_meta.append({
                    "doc_id":  doc["id"],
                    "title":   doc["title"],
                    "heading": section["heading"],
                    "content": section["content"][:200],
                })

        logger.info(f"开始计算 {len(all_texts)} 个 chunk 的 Embedding...")
        t0 = time.time()
        embeddings = self._model.encode(
            all_texts,
            batch_size=8,
            show_progress_bar=True,
            normalize_embeddings=True,
        )
        logger.info(f"Embedding 计算完成，耗时 {time.time() - t0:.1f}秒")

        self._chunks = [
            {**chunk_meta[i], "embedding": embeddings[i]}
            for i in range(len(chunk_meta))
        ]

    def _build_tfidf(self, docs: list[dict]):
        from sklearn.feature_extraction.text import TfidfVectorizer

        # ← 关键修复：每次重建都清空，保证幂等
        self._tfidf_doc_ids    = []
        self._tfidf_doc_titles = {}
        self._tfidf_doc_texts  = {}

        texts = []
        for doc in docs:
            self._tfidf_doc_ids.append(doc["id"])
            self._tfidf_doc_titles[doc["id"]] = doc["title"]
            self._tfidf_doc_texts[doc["id"]]  = doc["clean_text"]
            texts.append(doc["clean_text"])

        self._tfidf_vectorizer = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(2, 4), max_features=50000,
        )
        self._tfidf_matrix = self._tfidf_vectorizer.fit_transform(texts)

    # ──────────────────────────────────────────
    # 搜索
    # ──────────────────────────────────────────

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        if not query or not query.strip() or not self._ready:
            return []
        if self._use_fallback:
            return self._search_tfidf(query, top_k)
        return self._search_embedding(query, top_k)

    def _search_embedding(self, query: str, top_k: int) -> list[dict]:
        if self._chunk_matrix is None:
            return []
        query_vec = self._model.encode([query], normalize_embeddings=True)[0]
        similarities = self._chunk_matrix @ query_vec  # ← 复用预计算矩阵

        doc_scores:   dict[str, list[float]] = {}
        doc_titles:   dict[str, str]         = {}
        doc_snippets: dict[str, str]         = {}
        doc_best:     dict[str, float]       = {}

        for i, chunk in enumerate(self._chunks):
            doc_id = chunk["doc_id"]
            score  = float(similarities[i])
            doc_scores.setdefault(doc_id, []).append(score)
            doc_titles[doc_id] = chunk["title"]

            if score > doc_best.get(doc_id, -1):
                doc_best[doc_id] = score
                doc_snippets[doc_id] = f"[{chunk['heading']}] {chunk['content']}"

        results = []
        for doc_id, scores in doc_scores.items():
            final_score = 0.7 * max(scores) + 0.3 * (sum(scores) / len(scores))
            results.append({
                "id":      doc_id,
                "title":   doc_titles[doc_id],
                "snippet": doc_snippets[doc_id],
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

        sections = doc.get("sections", []) or [
            {"heading": doc["title"], "content": doc["clean_text"]}
        ]
        new_texts, new_meta = [], []
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
            new_texts, normalize_embeddings=True, show_progress_bar=False,
        )
        for i, meta in enumerate(new_meta):
            self._chunks.append({**meta, "embedding": new_embeddings[i]})

        self._rebuild_matrix()  # ← 增量更新预计算矩阵
        self._save_cache()      # ← 直接保存新状态，下次启动秒加载

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def mode(self) -> str:
        if not self._ready:
            return "未初始化"
        return "TF-IDF 兜底" if self._use_fallback else "Embedding 语义"


vector_index = VectorIndex()