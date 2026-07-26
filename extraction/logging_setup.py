"""Central logging setup.

`get_logger("api")` returns a logger that writes to BOTH the console and its own
rotating file `logs/api.log` — one file per component ("a log file for each
step"): api.log, db.log, storage.log (A3), tasks.log (A4), ...

Rotating handlers cap each file at ~2 MB with 5 backups so logs never grow
unbounded. `LOG_DIR` overrides the location (e.g. a mounted volume in Docker).
"""

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = os.environ.get(
    "LOG_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

_FMT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
_configured: set[str] = set()


def get_logger(name: str) -> logging.Logger:
    log = logging.getLogger(name)
    if name in _configured:               # idempotent — don't stack handlers
        return log

    log.setLevel(LOG_LEVEL)
    log.propagate = False                 # keep component logs out of the root logger
    os.makedirs(LOG_DIR, exist_ok=True)
    fmt = logging.Formatter(_FMT)

    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, f"{name}.log"),
        maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(fmt)
    log.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    log.addHandler(console)

    _configured.add(name)
    return log
