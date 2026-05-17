# Medical AI Backend

FastAPI backend for medical AI inference with background job processing.

## Features

- JWT Authentication
- Case and Image Management
- Background Inference Jobs (Celery)
- PDF Report Generation with Signing
- Audit Logging
- Rate Limiting
- Structured Results API

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Copy environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Start PostgreSQL and Redis:
```bash
docker-compose up -d
```

4. Run migrations:
```bash
bash scripts/migrate_db.sh
# Or manually: alembic upgrade head
```

5. Start the API server:
```bash
bash scripts/start_server.sh
# Or manually: uvicorn app.main:app --reload
```

6. Start Celery worker (in separate terminal):
```bash
bash scripts/start_celery.sh
# Or manually: celery -A app.celery_app worker --loglevel=info
```

**Quick Start (macOS/Linux):**
```bash
# Start both server and celery in separate terminals
bash scripts/start_all.sh
```

## CORS Configuration

CORS (Cross-Origin Resource Sharing) is enabled by default. Configure it in your `.env` file:

```env
# Allow all origins (development)
CORS_ORIGINS=*

# Allow specific origins (production)
CORS_ORIGINS=http://localhost:3000,https://yourdomain.com

# Allow credentials (cookies, authorization headers)
CORS_ALLOW_CREDENTIALS=true

# Allowed HTTP methods
CORS_ALLOW_METHODS=*

# Allowed headers
CORS_ALLOW_HEADERS=*
```

**Default Configuration:**
- `CORS_ORIGINS=*` - Allows all origins
- `CORS_ALLOW_CREDENTIALS=true` - Allows credentials (automatically disabled when using `*`)
- `CORS_ALLOW_METHODS=*` - Allows all HTTP methods
- `CORS_ALLOW_HEADERS=*` - Allows all headers

**Important Note:** When `CORS_ORIGINS=*` is used, `CORS_ALLOW_CREDENTIALS` is automatically set to `false` due to CORS specification limitations. To use credentials, specify explicit origins instead of `*`.

## API Endpoints

- `POST /api/v1/auth/request-otp` - Request OTP code
- `POST /api/v1/auth/login` - Login with email and OTP
- `POST /api/v1/cases` - Create a new case
- `POST /api/v1/cases/{case_id}/images` - Upload images for a case
- `POST /api/v1/inference` - Start inference job
- `GET /api/v1/inference/{job_id}/status` - Get inference job status
- `GET /api/v1/cases/{case_id}/results` - Get case results
- `GET /api/v1/cases/{case_id}/summary.pdf` - Download signed PDF summary
- `POST /api/v1/cases/{case_id}/notes` - Add clinician notes

## Project Structure

```
app/
├── main.py              # FastAPI application entry point
├── config.py            # Configuration settings
├── database.py          # Database connection
├── models.py            # SQLAlchemy models
├── schemas.py           # Pydantic schemas
├── celery_app.py        # Celery configuration
├── api/
│   ├── __init__.py
│   ├── deps.py          # Dependencies (auth, db)
│   ├── routes/
│   │   ├── auth.py      # Authentication routes
│   │   ├── cases.py     # Case management routes
│   │   ├── inference.py # Inference routes
│   │   └── results.py   # Results routes
│   └── middleware.py    # Audit logging, rate limiting
├── core/
│   ├── security.py      # JWT, password hashing
│   ├── pdf_generator.py # PDF generation and signing
│   └── audit.py         # Audit logging utilities
└── tasks/
    └── inference.py     # Celery inference tasks
alembic/
    └── versions/        # Migration files
```

