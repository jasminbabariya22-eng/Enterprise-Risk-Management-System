import logging
import os
from logging.handlers import TimedRotatingFileHandler

LOG_DIR = "logs"                               # Directory to store log files
os.makedirs(LOG_DIR, exist_ok=True)             # Ensure log directory exists

log_file = os.path.join(LOG_DIR, "ers_app.log")

logger = logging.getLogger("ers_logger")
logger.setLevel(logging.INFO)

handler = TimedRotatingFileHandler(                 # Rotate logs at midnight and keep 30 days of logs
    log_file,
    when="midnight",      # rotate daily
    interval=1,
    backupCount=30,       # keep last 30 days logs
    encoding="utf-8"
)

handler.suffix = "%Y-%m-%d.log"

formatter = logging.Formatter(                                # Log format: timestamp | log level | message
    "%(asctime)s | %(levelname)s | %(message)s",
    "%Y-%m-%d %H:%M:%S"
)

handler.setFormatter(formatter)                    # Set the formatter for the handler
logger.addHandler(handler)                     # Add the handler to the logger