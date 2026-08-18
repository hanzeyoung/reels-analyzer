"""DDL 마이그레이션 러너. `make migrate`에서 호출된다.

backend/db/migrations/ 안의 *.sql을 파일명 순으로 실행한다.
각 파일은 IF NOT EXISTS / CREATE OR REPLACE 등으로 멱등하게 작성되어 있어야 한다.
"""

import asyncio
import sys
from pathlib import Path

import psycopg

from app.config import get_settings

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "db" / "migrations"


async def run_migrations() -> None:
    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL이 설정되지 않았다", file=sys.stderr)
        raise SystemExit(1)

    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        print(f"마이그레이션 파일 없음: {MIGRATIONS_DIR}")
        return

    async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
        await conn.set_autocommit(True)
        for path in sql_files:
            print(f"적용 중: {path.name}")
            await conn.execute(path.read_text(encoding="utf-8"))
    print("마이그레이션 완료")


def main() -> None:
    asyncio.run(run_migrations())


if __name__ == "__main__":
    main()
