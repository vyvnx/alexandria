"""Backend logging.

One handler on the ``alexandria`` namespace; every backend logger is created
under it via :func:`get_logger`. Independent of uvicorn's own logging so our
lines show up regardless of how the app is launched.

Only the webscrape logs for now (see ``ingest/loaders.py``). To add logging
elsewhere, just ``get_logger("<area>")`` and emit — no extra wiring needed.
"""
import logging
import os

_NAMESPACE = "alexandria"
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"


def configure_logging(level: str | int | None = None) -> None:
    """Attach a stream handler to the ``alexandria`` logger. Idempotent.

    Level comes from the ``level`` arg, else ``ALEX_LOG_LEVEL`` (e.g. DEBUG to
    see byte sizes and a text preview of each scrape), else INFO.
    """
    level = level or os.getenv("ALEX_LOG_LEVEL", "INFO")
    logger = logging.getLogger(_NAMESPACE)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_FORMAT, datefmt="%H:%M:%S"))
        logger.addHandler(handler)
        logger.propagate = False  # don't double-print through root / uvicorn
    logger.setLevel(level)


def get_logger(area: str) -> logging.Logger:
    """Return a backend logger named ``alexandria.<area>`` (e.g. "scrape")."""
    return logging.getLogger(f"{_NAMESPACE}.{area}")
