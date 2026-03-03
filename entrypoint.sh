#!/bin/sh
set -e

echo "[entrypoint] Running Alembic migrations..."
python -m alembic upgrade head
echo "[entrypoint] Migrations complete."

echo "[entrypoint] Starting Omninet server (ROOT_PATH=${ROOT_PATH:-})..."
exec python -m uvicorn omninet.main:app --host 0.0.0.0 --port 8000 --root-path "${ROOT_PATH:-}"
