import os
import time
import logging

from app.services.task_runner import TaskRunner

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("rss-worker")


def run_forever() -> None:
    interval = max(5, int(os.getenv("WORKER_INTERVAL_SECONDS", "60")))
    runner = TaskRunner()
    logger.info("RSS AI Project Manager worker started; interval=%ss", interval)
    while True:
        try:
            result = runner.run_next()
            if result.get("status") != "idle":
                logger.info("task result: %s", result.get("status"))
        except Exception:
            logger.exception("worker cycle failed")
        time.sleep(interval)


if __name__ == "__main__":
    run_forever()
