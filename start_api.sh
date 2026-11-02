#!/bin/bash
set -e

echo "=========================================="
echo "Starting FastAPI application..."
echo "=========================================="
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
