import logging
import os
import time

from app.services.ci_ingestion import CIIngestion
from app.services.github_executor import GitHubExecutor
from app.services.project_discovery import discover_projects

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("rss-scheduler")


def run_forever() -> None:
    interval = max(300, int(os.getenv("DISCOVERY_INTERVAL_SECONDS", "900")))
    executor = GitHubExecutor()
    ci = CIIngestion()
    logger.info("RSS scheduler started; discovery interval=%ss", interval)
    while True:
        try:
            result = discover_projects()
            logger.info(
                "project discovery: added=%s total=%s",
                result.get("added", 0),
                len(result.get("projects", [])),
            )
            queued = executor.discover_and_queue()
            logger.info(
                "GitHub task queue: repositories=%s queued=%s",
                queued.get("repositories_seen", 0),
                queued.get("queued", 0),
            )
            ci_result = ci.sync()
            logger.info(
                "GitHub CI ingestion: checked=%s updated=%s",
                ci_result.get("checked", 0),
                ci_result.get("updated", 0),
            )
        except Exception:
            logger.exception("scheduled discovery/queue/CI cycle failed")
        time.sleep(interval)


if __name__ == "__main__":
    run_forever()
