"""Agent外部知识库存储与召回。"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from app.settings import settings

LOGGER = logging.getLogger(__name__)
_MEMORY_DOCUMENTS: dict[str, dict[str, Any]] = {}

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
    return bool(settings.database_url)


def initialize_knowledge_store() -> bool:
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


def search_persisted_knowledge(query: str, limit: int = 6) -> list[dict[str, Any]]:
    terms = _tokenize(query)
    hits = []
    for document in load_knowledge_documents():
        score = _score(terms, f"{document['title']} {document['content']}")
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
        )
        if term in value.lower()
    }
    return words | chinese_terms


def _score(terms: set[str], content: str) -> float:
    if not terms:
        return 0.0
    lowered = content.lower()
    matches = sum(1 for term in terms if term in lowered)
    return matches / max(len(terms), 1)
