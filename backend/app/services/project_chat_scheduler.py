import asyncio
import logging

from ..core.config import settings
from .auto_chat import AutomaticProjectChat

logger = logging.getLogger(__name__)


class ProjectChatScheduler:
    """In-process scheduler for automatic project chat.

    Multiple API replicas are safe because run_due claims schedules with
    PostgreSQL row locking (SKIP LOCKED). The scheduler only wakes the
    service; database state remains the source of truth.
    """

    def __init__(self) -> None:
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if not settings.auto_chat_scheduler_enabled:
            logger.info("Automatic project chat scheduler disabled")
            return
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="rss-auto-project-chat")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except asyncio.TimeoutError:
                self._task.cancel()
            self._task = None

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                result = await asyncio.to_thread(AutomaticProjectChat().run_due, settings.auto_chat_batch_size)
                if result["processed"]:
                    logger.info("Automatic project chat processed %s schedule(s)", result["processed"])
            except Exception:
                logger.exception("Automatic project chat scheduler cycle failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=settings.auto_chat_poll_seconds)
            except asyncio.TimeoutError:
                pass
