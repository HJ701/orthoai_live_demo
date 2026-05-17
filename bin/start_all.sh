#!/bin/bash

# Start all services (server + celery) script
# This script starts both the FastAPI server and Celery worker in separate terminal windows/tabs

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

echo "🚀 Starting Medical AI Backend services..."
echo ""

# Detect OS and use appropriate terminal command
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS - use osascript to open new terminal windows
    echo "📱 Opening new terminal windows for services..."
    
    # Start server in new terminal window
    osascript -e "tell application \"Terminal\" to do script \"cd '$PROJECT_DIR' && bash scripts/start_server.sh\""
    
    # Wait a moment
    sleep 2
    
    # Start Celery in new terminal window
    osascript -e "tell application \"Terminal\" to do script \"cd '$PROJECT_DIR' && bash scripts/start_celery.sh\""
    
    echo "✅ Services started in separate terminal windows"
    echo "📍 Server: http://localhost:8000"
    echo "📚 API docs: http://localhost:8000/docs"
    
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux - try to detect available terminal emulator
    if command -v gnome-terminal &> /dev/null; then
        echo "📱 Opening new terminal tabs for services..."
        gnome-terminal --tab --title="FastAPI Server" -- bash -c "cd '$PROJECT_DIR' && bash scripts/start_server.sh; exec bash"
        gnome-terminal --tab --title="Celery Worker" -- bash -c "cd '$PROJECT_DIR' && bash scripts/start_celery.sh; exec bash"
        echo "✅ Services started in separate terminal tabs"
    elif command -v xterm &> /dev/null; then
        echo "📱 Opening new xterm windows for services..."
        xterm -e "cd '$PROJECT_DIR' && bash scripts/start_server.sh" &
        xterm -e "cd '$PROJECT_DIR' && bash scripts/start_celery.sh" &
        echo "✅ Services started in separate xterm windows"
    else
        echo "⚠️  Could not detect terminal emulator. Starting in background..."
        echo "💡 You can manually start services:"
        echo "   Terminal 1: bash scripts/start_server.sh"
        echo "   Terminal 2: bash scripts/start_celery.sh"
        bash scripts/start_server.sh &
        bash scripts/start_celery.sh &
    fi
else
    echo "⚠️  Unsupported OS. Please start services manually:"
    echo "   Terminal 1: bash scripts/start_server.sh"
    echo "   Terminal 2: bash scripts/start_celery.sh"
    exit 1
fi

echo ""
echo "📍 Server: http://localhost:8000"
echo "📚 API docs: http://localhost:8000/docs"
echo ""
echo "To stop services, close the terminal windows or press Ctrl+C in each"

