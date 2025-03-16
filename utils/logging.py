import logging


logger = logging.getLogger("Console logger")
logger.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter(
    "[\033[93m%(levelname)s\033[0m] %(asctime)s -- %(message)s"
)
console_handler.setFormatter(formatter)

logger.addHandler(console_handler)
