# backend/app/services/agent_knowledge_store.py
# 文件说明：Agent 外部知识内存/PostgreSQL 存储。
# 主要职责：保存、加载、清理和词项评分召回知识文档。
# 对外入口：save_knowledge_document、search_persisted_knowledge。
# 依赖边界：查询文本不作为指令执行。

"""Agent外部知识库存储与召回。"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from app.settings import settings

LOGGER = logging.getLogger(__name__)
_MEMORY_DOCUMENTS: dict[str, dict[str, Any]] = {}
SPECIFIC_DIAGNOSIS_TERMS = (
    "根腐病",
    "白粉病",
    "锈病",
    "稻瘟病",
    "赤霉病",
    "枯萎病",
    "晚疫病",
    "炭疽病",
)

CREATE_KNOWLEDGE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS vegetation_agent_knowledge_documents (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'user-upload',
    session_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def is_enabled() -> bool:
    """执行 is_enabled 对应的领域操作并返回结构化结果。"""
    return bool(settings.database_url)


def initialize_knowledge_store() -> bool:
    """执行 initialize_knowledge_store 对应的领域操作并返回结构化结果。"""
    if not settings.database_url:
        return False
    try:
        import psycopg

        with psycopg.connect(settings.database_url) as connection:
            connection.execute(CREATE_KNOWLEDGE_TABLE_SQL)
        return True
    except Exception as error:  # noqa: BLE001 - 数据库不可用时降级内存
        LOGGER.warning("Agent知识库数据库初始化失败: %s", error)
        return False


def save_knowledge_document(spec: dict[str, Any]) -> dict[str, Any]:
    """执行 save_knowledge_document 对应的领域操作并返回结构化结果。"""
    content = str(spec.get("content") or "").strip()
    if not content:
        raise ValueError("知识文档内容不能为空")
    document = {
        "id": str(uuid.uuid4()),
        "title": str(spec.get("title") or "外部指数知识").strip()[:200],
        "content": content[:12000],
        "source": str(spec.get("source") or "user-upload").strip()[:500],
        "sessionId": spec.get("sessionId"),
    }
    _MEMORY_DOCUMENTS[document["id"]] = document
    if not initialize_knowledge_store():
        document["storage"] = "memory"
        return document

    import psycopg

    with psycopg.connect(settings.database_url) as connection:
        connection.execute(
            """
            INSERT INTO vegetation_agent_knowledge_documents (
                id, title, content, source, session_id
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                document["id"],
                document["title"],
                document["content"],
                document["source"],
                document["sessionId"],
            ),
        )
    document["storage"] = "postgresql"
    return document


def load_knowledge_documents(limit: int = 80) -> list[dict[str, Any]]:
    """执行 load_knowledge_documents 对应的领域操作并返回结构化结果。"""
    if not initialize_knowledge_store():
        return list(_MEMORY_DOCUMENTS.values())[-limit:]
    import psycopg

    with psycopg.connect(settings.database_url) as connection:
        rows = connection.execute(
            """
            SELECT id, title, content, source, session_id
            FROM vegetation_agent_knowledge_documents
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "id": str(row[0]),
            "title": row[1],
            "content": row[2],
            "source": row[3],
            "sessionId": str(row[4]) if row[4] else None,
        }
        for row in rows
    ]


def delete_knowledge_documents_by_source(source: str) -> int:
    """按来源删除测试或已撤回知识，避免测试数据污染真实召回。"""
    memory_ids = [
        document_id
        for document_id, document in _MEMORY_DOCUMENTS.items()
        if document.get("source") == source
    ]
    for document_id in memory_ids:
        _MEMORY_DOCUMENTS.pop(document_id, None)
    deleted = len(memory_ids)
    if not initialize_knowledge_store():
        return deleted

    import psycopg

    with psycopg.connect(settings.database_url) as connection:
        result = connection.execute(
            "DELETE FROM vegetation_agent_knowledge_documents WHERE source = %s",
            (source,),
        )
        deleted = max(deleted, result.rowcount)
    return deleted


def search_persisted_knowledge(query: str, limit: int = 6) -> list[dict[str, Any]]:
    """执行 search_persisted_knowledge 对应的领域操作并返回结构化结果。"""
    terms = _tokenize(query)
    hits = []
    for document in load_knowledge_documents():
        content = f"{document['title']} {document['content']}"
        if any(term in content and term not in query for term in SPECIFIC_DIAGNOSIS_TERMS):
            continue
        score = _score(terms, content)
        if score > 0:
            hits.append(
                {
                    "title": document["title"],
                    "content": document["content"][:500],
                    "source": f"knowledge-base:{document['source']}",
                    "score": round(score + 0.08, 3),
                }
            )
    hits.sort(key=lambda item: item["score"], reverse=True)
    return hits[:limit]


def _tokenize(value: str) -> set[str]:
    """完成模块内部的 tokenize 辅助处理。"""
    words = set(re.findall(r"[a-zA-Z0-9_]+", value.lower()))
    chinese_terms = {
        term
        for term in (
            "长势",
            "健康",
            "叶绿素",
            "水分",
            "干旱",
            "裸土",
            "稀疏",
            "变化",
            "火灾",
            "红边",
            "黄化",
            "氮素",
            "设施农业",
            "无人机",
            "rgb",
            "病虫害",
            "灌溉",
            "积水",
            "涝害",
            "盐碱",
            "倒伏",
            "冠层",
        )
        if term in value.lower()
    }
    return words | chinese_terms


def _score(terms: set[str], content: str) -> float:
    """完成模块内部的 score 辅助处理。"""
    if not terms:
        return 0.0
    lowered = content.lower()
    matches = sum(1 for term in terms if term in lowered)
    return matches / max(len(terms), 1)
