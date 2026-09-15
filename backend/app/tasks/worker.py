import asyncio
import logging

from app.core.config import get_settings
from app.database.session import SessionLocal, engine
from app.tasks.runner import run_due_tasks_once, sync_task_definitions


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def serve() -> None:
    settings = get_settings()
    while True:
        try:
            async with SessionLocal() as db:
                await sync_task_definitions(db)
            break
        except Exception:
            logger.exception("Task scheduler is waiting for the database and migrations")
            await asyncio.sleep(settings.task_poll_seconds)
    logger.info("BTB task scheduler started (poll every %s seconds)", settings.task_poll_seconds)
    try:
        while True:
            try:
                while await run_due_tasks_once(
                    SessionLocal,
                    lease_seconds=settings.task_lease_seconds,
                    retry_minutes=settings.task_retry_minutes,
                ):
                    pass
            except Exception:
                logger.exception("Task scheduler polling failed")
            await asyncio.sleep(settings.task_poll_seconds)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(serve())
