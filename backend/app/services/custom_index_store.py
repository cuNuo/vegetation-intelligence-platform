# backend/app/services/custom_index_store.py
# 文件说明：自定义指数 PostgreSQL 持久化。
# 主要职责：建表、upsert 保存并加载恢复指数定义。
# 对外入口：save_custom_index、load_custom_indices。
# 依赖边界：故障状态交由上层决定内存回退。

"""PostgreSQL自定义指数存储。"""

from __future__ import annotations

import logging
from typing import Any

from app.settings import settings

LOGGER = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS vegetation_custom_indices (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    expression TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    expected_range JSONB,
    categories JSONB NOT NULL DEFAULT '[]'::jsonb,
    recommendation_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    limitations JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def is_enabled() -> bool:
    """执行 is_enabled 对应的领域操作并返回结构化结果。"""
    return bool(settings.database_url)


def initialize_custom_index_store() -> bool:
    """执行 initialize_custom_index_store 对应的领域操作并返回结构化结果。"""
    if not settings.database_url:
        return False
    try:
        import psycopg

        with psycopg.connect(settings.database_url) as connection:
            connection.execute(CREATE_TABLE_SQL)
        return True
    except Exception as error:  # noqa: BLE001 - 数据库不可用时降级内存
        LOGGER.warning("自定义指数数据库初始化失败: %s", error)
        return False


def save_custom_index(spec: dict[str, Any]) -> bool:
    """执行 save_custom_index 对应的领域操作并返回结构化结果。"""
    if not initialize_custom_index_store():
        return False
    import psycopg
    from psycopg.types.json import Jsonb

    sql = """
    INSERT INTO vegetation_custom_indices (
        id, name, expression, description, expected_range,
        categories, recommendation_tags, limitations
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (id) DO UPDATE SET
        name = EXCLUDED.name,
        expression = EXCLUDED.expression,
        description = EXCLUDED.description,
        expected_range = EXCLUDED.expected_range,
        categories = EXCLUDED.categories,
        recommendation_tags = EXCLUDED.recommendation_tags,
        limitations = EXCLUDED.limitations,
        updated_at = now()
    """
    with psycopg.connect(settings.database_url) as connection:
        connection.execute(
            sql,
            (
                spec["id"],
                spec["name"],
                spec["expression"],
                spec.get("description", ""),
                Jsonb(spec.get("expectedRange")),
                Jsonb(spec.get("categories", [])),
                Jsonb(spec.get("recommendationTags", [])),
                Jsonb(spec.get("limitations", [])),
            ),
        )
    return True


def load_custom_indices() -> list[dict[str, Any]]:
    """执行 load_custom_indices 对应的领域操作并返回结构化结果。"""
    if not initialize_custom_index_store():
        return []
    import psycopg

    sql = """
    SELECT id, name, expression, description, expected_range,
           categories, recommendation_tags, limitations
    FROM vegetation_custom_indices
    ORDER BY updated_at DESC
    """
    with psycopg.connect(settings.database_url) as connection:
        rows = connection.execute(sql).fetchall()
    return [
        {
            "id": row[0],
            "name": row[1],
            "expression": row[2],
            "description": row[3],
            "expectedRange": row[4],
            "categories": row[5],
            "recommendationTags": row[6],
            "limitations": row[7],
        }
        for row in rows
    ]
