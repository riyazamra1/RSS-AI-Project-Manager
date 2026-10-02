from pathlib import Path

import psycopg

from app.core.config import settings


def main() -> None:
    database_url = settings.database_url
    migration_dir = Path("/app/database")
    files = sorted(migration_dir.glob("*.sql"))

    if not files:
        raise RuntimeError("No database migrations found")

    with psycopg.connect(database_url) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        for path in files:
            filename = path.name
            already_applied = conn.execute(
                "SELECT 1 FROM schema_migrations WHERE filename = %s",
                (filename,),
            ).fetchone()
            if already_applied:
                continue

            sql = path.read_text(encoding="utf-8")
            with conn.transaction():
                conn.execute(sql)
                conn.execute(
                    "INSERT INTO schema_migrations (filename) VALUES (%s)",
                    (filename,),
                )

    print(f"Database migrations checked: {len(files)}")


if __name__ == "__main__":
    main()
