"""
文档存储与管理模块
职责：
1. 扫描 data/ 目录，加载所有 sop-*.html
2. 维护内存中的文档元数据（id / title / path / clean_text / sections）
3. 支持动态添加文档（POST /v1/documents）
4. 生成并维护 data/manifest.json（供 Phase 3 Agent 使用）
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional
from app.core.html_clean import parse_html, extract_sections
from app.core.html_clean import parse_and_extract

logger = logging.getLogger(__name__)

# 项目根目录下的 data/ 目录
DATA_DIR = Path(__file__).parent.parent.parent / "data"


class DocStore:
    def __init__(self):
        # 核心存储：{doc_id: doc_meta}
        self._docs: dict[str, dict] = {}

    def load_all(self):
        """
        启动时扫描 data/ 目录，加载所有 sop-*.html 文件
        """
        DATA_DIR.mkdir(exist_ok=True)
        
        loaded = 0
        errors = 0
        
        for html_file in sorted(DATA_DIR.glob("sop-*.html")):
            doc_id = html_file.stem  # "sop-001"
            try:
                html_content = html_file.read_text(encoding="utf-8")
                self._add_doc(doc_id, html_content, html_file)
                loaded += 1
            except Exception as e:
                logger.error(f"加载文件 {html_file.name} 失败: {e}")
                errors += 1

        logger.info(f"DocStore 初始化完成：成功加载 {loaded} 个文档，失败 {errors} 个")
        
        # 生成 manifest.json（供 Phase 3 Agent 使用）
        self._update_manifest()

    from app.core.html_clean import parse_and_extract

    def _add_doc(self, doc_id, html, file_path=None):
        title, clean_text, sections = parse_and_extract(html)
        self._docs[doc_id] = {
            "id": doc_id,
            "title": title,
            "path": str(file_path) if file_path else str(DATA_DIR / f"{doc_id}.html"),
            "clean_text": clean_text,
            "sections": sections,
        }

    def add_document(self, doc_id: str, html: str) -> dict:
        """
        动态添加文档（对应 POST /v1/documents）
        同时写入 data/ 目录持久化
        """
        file_path = DATA_DIR / f"{doc_id}.html"
        file_path.write_text(html, encoding="utf-8")
        self._add_doc(doc_id, html, file_path)
        self._update_manifest()
        
        logger.info(f"新增文档: {doc_id} - {self._docs[doc_id]['title']}")
        return {"id": doc_id, "title": self._docs[doc_id]["title"]}

    def get_doc(self, doc_id: str) -> Optional[dict]:
        return self._docs.get(doc_id)

    def get_all_docs(self) -> list[dict]:
        return list(self._docs.values())

    def get_all_ids(self) -> list[str]:
        return list(self._docs.keys())

    def _update_manifest(self):
        """
        生成/更新 data/manifest.json
        这是 Phase 3 Agent 获知"有哪些文件可读"的唯一方式
        Agent 调用 readFile("manifest.json") 即可获取文件列表
        """
        manifest = {
            "description": "On-Call SOP 文档目录，通过 readFile(filename) 读取对应文档",
            "documents": [
                {
                    "filename": f"{doc['id']}.html",
                    "title": doc["title"],
                    "id": doc["id"]
                }
                for doc in self._docs.values()
            ]
        }
        manifest_path = DATA_DIR / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )


# 全局单例
doc_store = DocStore()