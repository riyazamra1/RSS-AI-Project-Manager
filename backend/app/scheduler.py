import os
import time
import logging

from app.services.project_discovery import discover_projects

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("rss-scheduler")


def run_forever() -> None:
    interval = max(300, int(os.getenv("DISCOVERY_INTERVAL_SECONDS", "900")))
    logger.info("RSS scheduler started; discovery interval=%ss", interval)
    while True:
        try:
            result = discover_projects()
            logger.info("project discovery: added=%s total=%s", result.get("added", 0), len(result.get("projects", [])))
        except Exception:
            logger.exception("scheduled discovery failed")
        time.sleep(interval)


if __name__ == "__main__":
    run_forever()
