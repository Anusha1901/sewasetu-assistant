FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir Flask==2.2.5 gunicorn==20.1.0
COPY app.py .
# The simulator holds its inbox in process memory: use exactly one worker.
CMD ["gunicorn", "--bind", "0.0.0.0:8025", "--workers", "1", "--threads", "4", "--no-sendfile", "app:app"]
