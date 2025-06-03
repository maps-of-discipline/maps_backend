FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
        PYTHONUNBUFFERED=1 \
        PIP_NO_CACHE_DIR=1 \
        FLASK_APP=app.py \
        FLASK_ENV=production

WORKDIR /app
COPY requirements.txt requirements.txt

RUN pip install --no-cache-dir --upgrade -r requirements.txt
COPY . .
CMD ["gunicorn", "app:app", "--config", "gunicorn_config.py" ]
