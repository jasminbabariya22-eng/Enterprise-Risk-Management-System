import logging
import os
from logging.handlers import TimedRotatingFileHandler

LOG_DIR = "logs/excel_import"
os.makedirs(LOG_DIR, exist_ok=True)

log_file = os.path.join(LOG_DIR, "excel_import.log")

excel_logger = logging.getLogger("excel_import_logger")
excel_logger.setLevel(logging.INFO)

# Prevent duplicate logs
if not excel_logger.handlers:

    handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )

    handler.suffix = "%Y-%m-%d.log"

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    handler.setFormatter(formatter)
    excel_logger.addHandler(handler)

    # Optional: don't propagate to root logger
    excel_logger.propagate = False