"""Persistence helpers for the permanent RSS project registry."""
from __future__ import annotations

from collections.abc import Iterable

from app.db import get_connection


def upsert_projects(projects: Iterable[dict]) -> int:
    count = 0
    with get_connection() as connection:
        with connection.cursor() as cursor:
            for project in projects:
                cursor.execute(
                    """
                    INSERT INTO projects (id, name, repository, enabled, priority)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        repository = EXCLUDED.repository,
                        enabled = EXCLUDED.enabled,
                        priority = EXCLUDED.priority,
                        updated_at = NOW()
                    """,
                    (
                        project["id"],
                        project["name"],
                        project.get("repository"),
                        project.get("enabled", True),
                        int(project.get("priority", 100)),
                    ),
                )
                count += 1
        connection.commit()
    return count


def list_projects() -> list[dict]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, name, repository, enabled, priority, created_at, updated_at
                FROM projects
                ORDER BY priority ASC, id ASC
                """
            )
            columns = [item.name for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
