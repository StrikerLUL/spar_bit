FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    SPARBIT_IN_DOCKER=1

WORKDIR /app

# curl fuer den Healthcheck; sonst nichts.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# Build-Kontext ist die Projektwurzel (siehe docker-compose.yml), damit
# cli.py mit ins Image kann. Die Pfade sind darum backend/-relativ.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/tools ./tools
# Die Kommandozeile: "docker compose exec backend python cli.py status"
# bzw. bequemer "./sparbit cli status".
COPY cli.py ./cli.py

# Nicht als root laufen.
RUN useradd --system --uid 10001 --create-home sparbit \
 && mkdir -p /data \
 && chown -R sparbit:sparbit /app /data
USER sparbit

ENV SPARBIT_DATA_DIR=/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
