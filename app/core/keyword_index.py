"""
Phase 1：关键词搜索引擎
策略：BM25（精准） + substring fallback（保证边界 case）
特殊处理：q=& 的 URL 解析陷阱
"""

import re
from typing import Optional
from rank_bm25 import BM25Okapi
from app.core.doc_store import DocStore

def tokenize(text: str) -> list[str]:
    """
    中英混合 tokenizer:
      - 中文单字 token（基础召回）
      - 中文相邻字 bigram token（提升排序准确度，"故障"=故+障+故障）
      - 英文/数字小写单词
      - 特殊字符（如 &）单独保留
    """
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    english_words = re.findall(r'[a-zA-Z0-9]+', text.lower())
    special_chars = re.findall(r'[&<>@#$%^*]', text)

    # 中文 bigram：把相邻两个汉字拼成 token
    bigrams = []
    chinese_seq = re.findall(r'[\u4e00-\u9fff]+', text)
    for seq in chinese_seq:
        for i in range(len(seq) - 1):
            bigrams.append(seq[i:i+2])

    return chinese_chars + bigrams + english_words + special_chars


class KeywordIndex:
    def __init__(self):
        self._doc_ids: list[str] = []
        self._doc_texts: list[str] = []
        self._doc_titles: dict[str, str] = {}
        self._bm25: Optional[BM25Okapi] = None

    def build(self, doc_store: DocStore):
        """
        从 DocStore 构建 BM25 索引
        """
        docs = doc_store.get_all_docs()
        if not docs:
            return

        self._doc_ids = [d["id"] for d in docs]
        self._doc_texts = [d["clean_text"] for d in docs]
        self._doc_titles = {d["id"]: d["title"] for d in docs}

        # 构建 BM25
        tokenized_corpus = [tokenize(text) for text in self._doc_texts]
        self._bm25 = BM25Okapi(tokenized_corpus)

    def add_document(self, doc_id: str, clean_text: str, title: str):
        """
        动态添加文档后重建索引
        """
        if doc_id in self._doc_ids:
            # 更新已有文档
            idx = self._doc_ids.index(doc_id)
            self._doc_texts[idx] = clean_text
        else:
            self._doc_ids.append(doc_id)
            self._doc_texts.append(clean_text)
        
        self._doc_titles[doc_id] = title
        
        # 重建 BM25（数据量小，重建成本低）
        tokenized_corpus = [tokenize(text) for text in self._doc_texts]
        self._bm25 = BM25Okapi(tokenized_corpus)

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """
        关键词检索
        返回：[{id, title, snippet, score}, ...]
        
        策略：
        1. 空 query → 返回空列表
        2. BM25 检索 → 过滤掉 score=0 的结果（未命中）
        3. 对于 & 等特殊字符，额外做 substring 校验确保结果可靠
        """
        if not query or not query.strip():
            return []

        if self._bm25 is None:
            return []

        query_tokens = tokenize(query)
        
        if not query_tokens:
            return []

        # BM25 打分
        scores = self._bm25.get_scores(query_tokens)

        results = []
        for idx, score in enumerate(scores):
            doc_id = self._doc_ids[idx]
            doc_text = self._doc_texts[idx]
            
            # BM25 score > 0 表示有命中
            # 对于特殊字符查询（如 &），额外验证 substring 存在
            if score > 0 and self._verify_match(query, doc_text):
                snippet = self._extract_snippet(query, doc_text)
                results.append({
                    "id": doc_id,
                    "title": self._doc_titles[doc_id],
                    "snippet": snippet,
                    "score": round(float(score), 4),
                })

        # 按 score 降序排列
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _verify_match(self, query: str, text: str) -> bool:
        """
        验证 query 确实在 text 中出现（大小写不敏感）
        这是防止 BM25 误判的保障层，同时确保 & 这类特殊字符的精确匹配
        """
        return query.lower() in text.lower()

    def _extract_snippet(self, query: str, text: str, context_chars: int = 100) -> str:
        """
        提取包含 query 的上下文片段
        """
        text_lower = text.lower()
        query_lower = query.lower()
        
        pos = text_lower.find(query_lower)
        if pos == -1:
            # fallback：返回文本前 200 字符
            return text[:200].replace("\n", " ").strip() + "..."

        start = max(0, pos - context_chars)
        end = min(len(text), pos + len(query) + context_chars)
        
        snippet = text[start:end].replace("\n", " ").strip()
        
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."

        return snippet


# 全局单例
keyword_index = KeywordIndex()