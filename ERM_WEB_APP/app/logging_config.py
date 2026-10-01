import logging
from logging.handlers import RotatingFileHandler
import os

def setup_logging(app):

    if not os.path.exists("logs"):
        os.mkdir("logs")

    formatter = logging.Formatter(
        '{"time":"%(asctime)s","level":"%(levelname)s","message":"%(message)s"}'
    )

    # App Log
    file_handler = RotatingFileHandler(
        "logs/app.log",
        maxBytes=10_000_000,
        backupCount=10
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # Error Log
    error_handler = RotatingFileHandler(
        "logs/error.log",
        maxBytes=10_000_000,
        backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    app.logger.addHandler(file_handler)
    app.logger.addHandler(error_handler)
    app.logger.setLevel(logging.INFO)