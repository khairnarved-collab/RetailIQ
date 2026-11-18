# RetailIQ API (FastAPI + ML)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# libgomp is needed by XGBoost / scikit-learn
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/backend
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ .
COPY data/sample /srv/data/sample
RUN useradd --create-home appuser && mkdir -p /srv/data/uploads /srv/data/processed /srv/models /srv/reports \
    && chown -R appuser /srv
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD curl -fs http://localhost:8000/api/health || exit 1
# migrate -> (optionally) seed demo data -> serve
CMD ["sh", "scripts/docker-entrypoint.sh"]
