"""
Structured logger: per-pipeline rotating log files + rich console output.
"""
from __future__ import annotations
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


_LOGGERS: dict[str, logging.Logger] = {}

RESET   = "\033[0m"
BOLD    = "\033[1m"
RED     = "\033[91m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
BLUE    = "\033[94m"
CYAN    = "\033[96m"
GREY    = "\033[90m"


class ColorFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG:    GREY,
        logging.INFO:     CYAN,
        logging.WARNING:  YELLOW,
        logging.ERROR:    RED,
        logging.CRITICAL: RED + BOLD,
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, RESET)
        ts = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        level = f"{color}{record.levelname:<8}{RESET}"
        name = f"{BLUE}[{record.name}]{RESET}"
        msg = record.getMessage()
        return f"{GREY}{ts}{RESET} {level} {name} {msg}"


class PlainFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        return f"{ts} {record.levelname:<8} [{record.name}] {record.getMessage()}"


def get_logger(name: str, log_dir: str = "logs", log_level: str = "INFO") -> logging.Logger:
    """
    Get (or create) a named logger with both console and file handlers.
    Loggers are cached — calling this multiple times with the same name is safe.
    """
    if name in _LOGGERS:
        return _LOGGERS[name]

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    logger.propagate = False

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(ColorFormatter())
    logger.addHandler(console)

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_file = Path(log_dir) / f"{name.replace(' ', '_')}.log"
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(PlainFormatter())
    logger.addHandler(file_handler)

    _LOGGERS[name] = logger
    return logger


def get_run_logger(pipeline_name: str, log_dir: str = "logs", log_level: str = "INFO") -> logging.Logger:
    """Create a run-scoped logger with a timestamped file for this specific run."""
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = pipeline_name.replace(" ", "_")
    run_name = f"{safe_name}_{run_ts}"

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_file = Path(log_dir) / f"{run_name}.log"

    logger = logging.getLogger(run_name)
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    logger.propagate = False

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(ColorFormatter())
    logger.addHandler(console)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(PlainFormatter())
    logger.addHandler(file_handler)

    return logger
