import logging
import config

logger = logging.getLogger("Console logger")
logger.setLevel(config.LOG_LEVEL)

console_handler = logging.StreamHandler()
console_handler.setLevel(config.LOG_LEVEL)

formatter = logging.Formatter(
    "[\033[93m%(levelname)s\033[0m] %(asctime)s -- %(message)s"
)
console_handler.setFormatter(formatter)

logger.addHandler(console_handler)
