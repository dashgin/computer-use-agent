#!/bin/bash
set -e

alembic upgrade head

# Create data directories
mkdir -p /home/computeruse/data /home/computeruse/logs



# Start VNC services
echo "🔧 Starting VNC services..."
./start_all.sh
./novnc_startup.sh

echo "✨ All services started!"
echo "➡️  FastAPI Backend: http://localhost:8000"
echo "➡️  API Documentation: http://localhost:8000/docs"
echo "➡️  VNC Interface: http://localhost:6080"

# Start FastAPI backend
echo "🔧 Starting FastAPI backend on port 8000..."
uvicorn app.main:app --host 0.0.0.0 --port 8000