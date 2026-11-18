"""Consistent, readable logging for the whole backend."""
import logging
import sys

from app.core.config import settings


def setup_logging() -> None:
    logging.basicConfig(
        level=settings.LOG_LEVEL.upper(),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
        force=True,
    )
    # Quieten noisy libraries
    for name in ("matplotlib", "PIL", "urllib3", "httpx", "numba", "shap"):
        logging.getLogger(name).setLevel(logging.WARNING)
