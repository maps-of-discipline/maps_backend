FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade -r requirements.txt
COPY . .
CMD ["gunicorn", \
        "--bind", "0.0.0.0:5000", \
        "app:app", \
        "--workers", "4", \
        "--preload", \
        "--log-file", "/app/logs/gunicorn.log", \
        "--access-logfile", "/app/logs/access.log", \
        "--error-logfile", "/app/logs/error.log" \
]