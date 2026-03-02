#!/bin/sh
set -e

echo "[entrypoint] Running Alembic migrations..."
python -m alembic upgrade head
echo "[entrypoint] Migrations complete."

echo "[entrypoint] Starting Omninet server..."
exec python -m uvicorn omninet.main:app --host 0.0.0.0 --port 8000
