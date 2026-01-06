import logging
from pathlib import Path

from app.core.config import settings


def configure_logging(level: str) -> None:
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    handlers = {type(handler) for handler in root_logger.handlers}
    if logging.FileHandler not in handlers:
        root_logger.addHandler(file_handler)
    if logging.StreamHandler not in handlers:
        root_logger.addHandler(console_handler)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.setLevel(level)
        if logging.FileHandler not in {type(handler) for handler in logger.handlers}:
            logger.addHandler(file_handler)
