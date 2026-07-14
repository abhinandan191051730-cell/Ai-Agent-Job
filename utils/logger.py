import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler


def setup_logging(level: str = "INFO", log_file: str = None):
    root = logging.getLogger()
    if root.handlers:
        return
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    root.addHandler(ch)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            str(log_path), maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        fh.setFormatter(formatter)
        root.addHandler(fh)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
