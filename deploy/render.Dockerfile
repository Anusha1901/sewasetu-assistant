FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*
ENV TZ=Asia/Kolkata PYTHONUNBUFFERED=1
WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ .
RUN cp config/app.ini.example config/app.ini
COPY smsgw/app.py simulator/app.py
COPY deploy/render_start.py deploy/initialize_hosted.py /app/hosting/
COPY seed/seed.sql /app/hosting/seed.sql
RUN mkdir -p /var/sewasetu/uploads /var/log/sewasetu
CMD ["python", "/app/hosting/render_start.py"]
