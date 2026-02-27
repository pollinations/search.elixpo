#!/bin/bash
set -e

# LixSearch Entrypoint Script
# Supports both load_balancer and worker modes

APP_MODE=${APP_MODE:-worker}
WORKER_PORT=${WORKER_PORT:-8001}
WORKER_ID=${WORKER_ID:-1}
LOG_LEVEL=${LOG_LEVEL:-INFO}

echo "Starting LixSearch in $APP_MODE mode..."
echo "Log level: $LOG_LEVEL"

if [ "$APP_MODE" = "load_balancer" ]; then
    echo "Starting Load Balancer on port 8000..."
    cd /app
    python -m lixsearch.load_balancer
elif [ "$APP_MODE" = "worker" ]; then
    echo "Starting Worker $WORKER_ID on port $WORKER_PORT..."
    cd /app
    # Dynamically set WORKER_PORT environment variable
    export WORKER_PORT=$WORKER_PORT
    python -m lixsearch.app.main
else
    echo "Unknown APP_MODE: $APP_MODE"
    exit 1
fi
