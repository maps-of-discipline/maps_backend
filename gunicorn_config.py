import sys

# ------------------------------
# Server Socket Configuration
# ------------------------------
bind = "0.0.0.0:5000"  # Server socket to bind
backlog = 2048  # Pending connections queue size

# ------------------------------
# Worker Processes
# ------------------------------
workers = 4  # Number of worker processes
worker_class = "sync"  # Worker type: sync, eventlet, gevent, tornado, gthread
worker_connections = 1000  # Max number of connections per worker
timeout = 30  # Worker timeout in seconds

# ------------------------------
# Process Naming
# ------------------------------
proc_name = "maps-gunicorn"  # Process name
pythonpath = "."  # Python path

# ------------------------------
# Logging Configuration
# ------------------------------
# Basic logging settings
loglevel = "info"
errorlog = "-"  # stderr
accesslog = "-"  # stdout
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'
capture_output = True  # Redirect stdout/stderr from the application

# Detailed logging configuration
logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "generic": {
            "format": "%(asctime)s [%(process)d] [%(levelname)s] %(message)s",
            "datefmt": "[%Y-%m-%d %H:%M:%S %z]",
            "class": "logging.Formatter",
        },
        "access": {
            "format": "%(asctime)s [%(process)d] [ACCESS] %(message)s",
            "datefmt": "[%Y-%m-%d %H:%M:%S %z]",
            "class": "logging.Formatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "generic",
            "stream": sys.stdout,
        },
        "error_console": {
            "class": "logging.StreamHandler",
            "formatter": "generic",
            "stream": sys.stderr,
        },
        "access_console": {
            "class": "logging.StreamHandler",
            "formatter": "access",
            "stream": sys.stdout,
        },
    },
    "loggers": {
        "gunicorn.error": {
            "level": "INFO",
            "handlers": ["error_console"],
            "propagate": False,
        },
        "gunicorn.access": {
            "level": "INFO",
            "handlers": ["access_console"],
            "propagate": False,
        },
        # Root logger - for application logs
        "": {"level": "INFO", "handlers": ["console"], "propagate": True},
    },
}


# ------------------------------
# Server Hooks
# ------------------------------
def on_starting(server):
    """Log when the server starts up"""
    server.log.info("Starting Gunicorn server...")


def on_reload(server):
    """Log when the server reloads"""
    server.log.info("Reloading Gunicorn server...")


def post_fork(server, worker):
    """Actions to run after worker is forked"""
    server.log.info(f"Worker spawned (pid: {worker.pid})")


def worker_exit(server, worker):
    """Log when a worker exits"""
    server.log.info(f"Worker exited (pid: {worker.pid})")


def on_exit(server):
    """Log when the server exits"""
    server.log.info("Shutting down Gunicorn server")


# Production performance settings
graceful_timeout = 30  # Seconds to forcefully kill workers
