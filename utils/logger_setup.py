"""utils/logger_setup.py — Rotating file + console logging."""
import logging, os
from logging.handlers import RotatingFileHandler
from datetime import datetime

def setup_logging(log_dir="logs", level="INFO"):
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"bot_{datetime.now().strftime('%Y%m%d')}.log")
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)-28s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    ch = logging.StreamHandler()
    ch.setFormatter(fmt); root.addHandler(ch)
    fh = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt); root.addHandler(fh)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
