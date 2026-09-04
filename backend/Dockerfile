FROM python:3.12-slim

WORKDIR /app

# Systemabhängigkeiten
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    postgresql-client \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-xlib-2.0-0 \
    libffi-dev \
    shared-mime-info \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*
# Bewusst NICHT mehr enthalten: git und docker-ce-cli. Beides brauchte nur das
# In-App-Update (gestrichen am 04.09.2026, Audit SEC-002 / K-21). curl bleibt
# für den Container-Healthcheck.

# Python-Abhängigkeiten
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
