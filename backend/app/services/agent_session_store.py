"""Agent会话事件存储。"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.settings import settings

LOGGER = logging.getLogger(__name__)
_MEMORY_SESSIONS: dict[str, dict[str, Any]] = {}
_MEMORY_EVENTS: dict[str, list[dict[str, Any]]] = {}

CREATE_SESSION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS vegetation_agent_sessions (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

CREATE_EVENT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS vegetation_agent_events (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES vegetation_agent_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    event_type TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def is_enabled() -> bool:
    return bool(settings.database_url)


def initialize_agent_session_store() -> bool:
    if not settings.database_url:
        return False
    try:
        import psycopg

        with psycopg.connect(settings.database_url) as connection:
            connection.execute(CREATE_SESSION_TABLE_SQL)
            connection.execute(CREATE_EVENT_TABLE_SQL)
        return True
    except Exception as error:  # noqa: BLE001 - 数据库不可用时降级内存
        LOGGER.warning("Agent会话数据库初始化失败: %s", error)
        return False


def create_session(title: str) -> str:
    session_id = str(uuid.uuid4())
    _MEMORY_SESSIONS[session_id] = {"id": session_id, "title": title[:160]}
    _MEMORY_EVENTS.setdefault(session_id, [])
    if not initialize_agent_session_store():
        return session_id
    import psycopg

    with psycopg.connect(settings.database_url) as connection:
        connection.execute(
            """
            INSERT INTO vegetation_agent_sessions (id, title)
            VALUES (%s, %s)
            """,
            (session_id, title[:160]),
        )
    return session_id


def append_event(
    session_id: str,
    role: str,
    event_type: str,
    content: str,
    payload: dict[str, Any] | None = None,
) -> bool:
    if not initialize_agent_session_store():
        _MEMORY_EVENTS.setdefault(session_id, []).append(
            {
                "id": str(uuid.uuid4()),
                "role": role,
                "eventType": event_type,
                "content": content,
                "payload": payload or {},
                "createdAt": "",
            }
        )
        return False
    import psycopg
    from psycopg.types.json import Jsonb

    with psycopg.connect(settings.database_url) as connection:
        connection.execute(
            """
            INSERT INTO vegetation_agent_events (
                id, session_id, role, event_type, content, payload
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                str(uuid.uuid4()),
                session_id,
                role,
                event_type,
                content,
                Jsonb(payload or {}),
            ),
        )
        connection.execute(
            "UPDATE vegetation_agent_sessions SET updated_at = now() WHERE id = %s",
            (session_id,),
        )
    return True


def list_events(session_id: str) -> list[dict[str, Any]]:
    if not initialize_agent_session_store():
        return list(_MEMORY_EVENTS.get(session_id, []))
    import psycopg

    with psycopg.connect(settings.database_url) as connection:
        rows = connection.execute(
            """
            SELECT id, role, event_type, content, payload, created_at
            FROM vegetation_agent_events
            WHERE session_id = %s
            ORDER BY created_at ASC
            """,
            (session_id,),
        ).fetchall()
    return [
        {
            "id": str(row[0]),
            "role": row[1],
            "eventType": row[2],
            "content": row[3],
            "payload": row[4],
            "createdAt": row[5].isoformat(),
        }
        for row in rows
    ]
