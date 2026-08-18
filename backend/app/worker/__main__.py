import asyncio
import logging

from app.config import get_settings
from app.db.connection import close_pool, init_pool
from app.worker.loop import run_forever


async def _main() -> None:
    await init_pool()
    try:
        settings = get_settings()
        await run_forever(stale_minutes=settings.stale_minutes)
    finally:
        await close_pool()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())


if __name__ == "__main__":
    main()
