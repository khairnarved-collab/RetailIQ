# Single-container image (frontend + API in one service) for PaaS hosts such as
# Render, Railway or Fly.io. Point DATABASE_URL at a managed PostgreSQL database.
FROM node:20-alpine AS web
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 FRONTEND_DIST=/srv/web \
    UPLOAD_DIR=/srv/data/uploads PROCESSED_DIR=/srv/data/processed SAMPLE_DIR=/srv/data/sample \
    MODEL_DIR=/srv/models REPORT_DIR=/srv/reports WEB_CONCURRENCY=1 MALLOC_ARENA_MAX=2
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl && rm -rf /var/lib/apt/lists/*
WORKDIR /srv/backend
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ .
COPY data/sample /srv/data/sample
COPY --from=web /app/dist /srv/web
RUN useradd --create-home appuser && mkdir -p /srv/data/uploads /srv/data/processed /srv/models /srv/reports && chown -R appuser /srv
USER appuser
EXPOSE 8000
CMD ["sh", "scripts/docker-entrypoint.sh"]
