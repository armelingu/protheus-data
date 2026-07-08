FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl gnupg2 tzdata unixodbc-dev \
        libxml2-dev libxslt-dev && \
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql17 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ENV TZ=America/Sao_Paulo
ENV APP_TIMEZONE=America/Sao_Paulo
ENV PYTHONUNBUFFERED=1
# Suprime o bootstrap automatico embutido no app.py (inicializar() no import).
# O bootstrap e disparado explicitamente pelo gunicorn_conf.py:post_fork
# apenas no SCHEDULER_OWNER (primeiro worker), evitando jobs duplicados.
ENV GUNICORN_WORKER_BOOT=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/data/backups

EXPOSE 5000

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=5 \
    CMD curl -fsS http://localhost:5000/health || exit 1

CMD ["gunicorn", "-c", "config/gunicorn_conf.py", "app:app"]
