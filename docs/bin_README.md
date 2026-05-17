# Scripts Directory

This directory contains utility scripts for managing the Medical AI Backend.

## Available Scripts

### `start_server.sh`
Starts the FastAPI server with hot-reload enabled.

**Usage:**
```bash
bash scripts/start_server.sh
```

**Features:**
- Checks for `.env` file
- Creates virtual environment if needed
- Verifies database connection
- Starts server on http://localhost:8000

### `start_celery.sh`
Starts the Celery worker for processing background inference jobs.

**Usage:**
```bash
bash scripts/start_celery.sh
```

**Features:**
- Checks for `.env` file
- Creates virtual environment if needed
- Verifies Redis connection
- Starts Celery worker

### `migrate_db.sh`
Manages database migrations using Alembic.

**Usage:**
```bash
# Upgrade to latest migration (default)
bash scripts/migrate_db.sh
bash scripts/migrate_db.sh upgrade

# Downgrade by 1 revision
bash scripts/migrate_db.sh downgrade -1

# Create new migration
bash scripts/migrate_db.sh revision "Add new table"

# Show current status
bash scripts/migrate_db.sh current
```

**Commands:**
- `upgrade` or `up` - Upgrade database to latest migration (default)
- `downgrade` or `down [N]` - Downgrade database by N revisions
- `revision` or `new [MSG]` - Create new migration with message
- `current` or `status` - Show current revision and history

### `start_all.sh`
Starts both the FastAPI server and Celery worker in separate terminal windows/tabs.

**Usage:**
```bash
bash scripts/start_all.sh
```

**Features:**
- macOS: Opens new Terminal windows
- Linux: Opens new terminal tabs (gnome-terminal) or windows (xterm)
- Automatically starts both services

### `create_test_user.py`
Creates a test user for development and testing.

**Usage:**
```bash
# Create default test user (username: testuser, password: testpass)
python scripts/create_test_user.py

# Create custom user
python scripts/create_test_user.py myuser mypassword myuser@example.com
```

## Examples

### Complete Setup Flow

```bash
# 1. Setup environment
cp .env.example .env
# Edit .env with your configuration

# 2. Start infrastructure (PostgreSQL + Redis)
docker-compose up -d

# 3. Run migrations
bash scripts/migrate_db.sh

# 4. Create test user
python scripts/create_test_user.py

# 5. Start all services (macOS/Linux)
bash scripts/start_all.sh

# Or start manually in separate terminals:
# Terminal 1:
bash scripts/start_server.sh

# Terminal 2:
bash scripts/start_celery.sh
```

### Database Migration Workflow

```bash
# Check current status
bash scripts/migrate_db.sh current

# Create new migration after model changes
bash scripts/migrate_db.sh revision "Add new field to cases"

# Review the generated migration file
# Edit if needed, then upgrade
bash scripts/migrate_db.sh upgrade

# If something goes wrong, downgrade
bash scripts/migrate_db.sh downgrade -1
```

## Notes

- All scripts check for `.env` file and virtual environment
- Scripts automatically create virtual environment if missing
- Scripts verify database/Redis connections before starting
- Use `Ctrl+C` to stop running services
- On macOS, `start_all.sh` uses `osascript` to open Terminal windows
- On Linux, `start_all.sh` tries to detect available terminal emulator

