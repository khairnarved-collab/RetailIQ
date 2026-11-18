#!/bin/sh
# Container start-up: apply migrations, load demo data if requested, start the API.
set -e
echo "Applying database migrations..."
alembic upgrade head
if [ "${SEED_DEMO_DATA:-true}" = "true" ]; then
  echo "Loading demo users and SYNTHETIC sample data (skipped if already present)..."
  python -m scripts.seed
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers "${WEB_CONCURRENCY:-2}" --proxy-headers --forwarded-allow-ips="*"
