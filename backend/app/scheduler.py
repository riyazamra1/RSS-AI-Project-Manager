import logging
import os
import time

from app.services.project_discovery import discover_projects
from app.services.github_executor import GitHubExecutor

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("rss-scheduler")


def run_forever() -> None:
    interval = max(300, int(os.getenv("DISCOVERY_INTERVAL_SECONDS", "900")))
    github_enabled = os.getenv("GITHUB_DISCOVERY_ENABLED", "false").lower() in {"1","true","yes"}
    logger.info("RSS AI Project Manager scheduler started; interval=%ss; github_discovery=%s", interval, github_enabled)
    while True:
        try:
            if github_enabled:
                result = discover_projects()
                logger.info("project discovery: added=%s total=%s", result.get("added", 0), len(result.get("projects", [])))
                queued = GitHubExecutor().discover_and_queue()
                logger.info("GitHub discovery: repositories=%s queued=%s", queued.get("repositories_seen", 0), queued.get("queued", 0))
            else:
                logger.info("GitHub discovery disabled; execution remains RSS Core/RAY-only")
        except Exception:
            logger.exception("scheduled discovery cycle failed")
        time.sleep(interval)


if __name__ == "__main__":
    run_forever()
