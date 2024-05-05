FROM python:3.11
WORKDIR /app
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade -r requirements.txt
COPY . .
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app", "--workers", "4", "--preload", "--log-file", "/var/log/gunicorn.log"]
