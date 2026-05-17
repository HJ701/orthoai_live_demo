#!/bin/bash

# Database migration script

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

# Check if database is accessible
echo "🔍 Checking database connection..."
python3 -c "
import os
from app.config import settings
try:
    import psycopg2
    conn = psycopg2.connect(settings.database_url)
    conn.close()
    print('✅ Database connection successful')
except Exception as e:
    print(f'❌ Database connection failed: {e}')
    print('💡 Make sure PostgreSQL is running and DATABASE_URL is correct')
    exit(1)
" || exit 1

# Parse command line arguments
COMMAND="${1:-upgrade}"

case "$COMMAND" in
    upgrade|up)
        echo "⬆️  Running database migrations (upgrade to head)..."
        alembic upgrade head
        echo "✅ Migrations completed successfully"
        ;;
    
    downgrade|down)
        REVISION="${2:--1}"
        echo "⬇️  Downgrading database by $REVISION revision(s)..."
        alembic downgrade "$REVISION"
        echo "✅ Downgrade completed successfully"
        ;;
    
    revision|new)
        MESSAGE="${2:-Auto migration}"
        echo "📝 Creating new migration: $MESSAGE"
        alembic revision --autogenerate -m "$MESSAGE"
        echo "✅ Migration file created"
        ;;
    
    current|status)
        echo "📊 Current database revision:"
        alembic current
        echo ""
        echo "📋 Migration history:"
        alembic history
        ;;
    
    *)
        echo "Usage: $0 {upgrade|downgrade|revision|current} [options]"
        echo ""
        echo "Commands:"
        echo "  upgrade, up          Upgrade database to latest migration (default)"
        echo "  downgrade, down [N]  Downgrade database by N revisions (default: -1)"
        echo "  revision, new [MSG]  Create new migration with message (default: 'Auto migration')"
        echo "  current, status      Show current revision and history"
        echo ""
        echo "Examples:"
        echo "  $0                    # Upgrade to head (default)"
        echo "  $0 upgrade            # Upgrade to head"
        echo "  $0 downgrade -1       # Downgrade by 1 revision"
        echo "  $0 revision 'Add new table'  # Create new migration"
        echo "  $0 current           # Show current status"
        exit 1
        ;;
esac

