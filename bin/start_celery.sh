#!/bin/bash

# Start Celery worker script

set -e

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found"
    echo "💡 Please copy .env.example to .env and configure it"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "⚠️  Virtual environment not found. Creating one..."
    python3 -m venv venv
    echo "📥 Installing dependencies..."
    source venv/bin/activate
    pip install -r requirements.txt
else
    # Activate virtual environment
    source venv/bin/activate
fi

# Check if Redis is accessible
echo "🔍 Checking Redis connection..."
python3 -c "
import redis
from app.config import settings
try:
    r = redis.from_url(settings.redis_url)
    r.ping()
    print('✅ Redis connection successful')
except Exception as e:
    print(f'❌ Redis connection failed: {e}')
    print('💡 Make sure Redis is running and REDIS_URL is correct')
    exit(1)
" || exit 1

# Start Celery worker
echo "🚀 Starting Celery worker..."
echo "📋 Worker will process background inference jobs"
echo ""
echo "Press Ctrl+C to stop the worker"
echo ""

celery -A app.celery_app worker --loglevel=info

