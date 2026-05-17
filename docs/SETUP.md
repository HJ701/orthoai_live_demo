# Setup Guide

## Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Docker and Docker Compose (optional, for running PostgreSQL and Redis)

## Installation Steps

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy the example environment file and configure it:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:
- Set `DATABASE_URL` to your PostgreSQL connection string
- Set `SECRET_KEY` to a secure random string (use `openssl rand -hex 32`)
- Configure Redis URLs for Celery
- Adjust other settings as needed

### 3. Start Infrastructure Services

Using Docker Compose (recommended):

```bash
docker-compose up -d
```

Or manually start PostgreSQL and Redis.

### 4. Run Database Migrations

```bash
alembic upgrade head
```

### 5. Create a Test User (Optional)

```bash
python scripts/create_test_user.py
# Or with custom credentials:
python scripts/create_test_user.py myuser mypassword myuser@example.com
```

### 6. Start the Application

Terminal 1 - API Server:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Terminal 2 - Celery Worker:
```bash
celery -A app.celery_app worker --loglevel=info
```

### 7. Access the API

- API: http://localhost:8000
- Interactive API Docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API Endpoints

### Authentication
- `POST /api/v1/auth/login` - Login and get JWT token
- `POST /api/v1/auth/register` - Register new user (development only)

### Cases
- `POST /api/v1/cases` - Create a new case
- `POST /api/v1/cases/{case_id}/images` - Upload images (multipart)
- `POST /api/v1/cases/{case_id}/notes` - Add clinician notes

### Inference
- `POST /api/v1/inference` - Start inference job
- `GET /api/v1/inference/{job_id}/status` - Get job status
- `POST /api/v1/inference/{job_id}/cancel` - Cancel running job

### Results
- `GET /api/v1/cases/{case_id}/results` - Get case results (JSON)
- `GET /api/v1/cases/{case_id}/summary.pdf` - Download signed PDF

## Testing the API

### 1. Login

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=testuser&password=testpass"
```

Response:
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

### 2. Create a Case

```bash
curl -X POST "http://localhost:8000/api/v1/cases" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"consent_checked": true}'
```

### 3. Upload Images

```bash
curl -X POST "http://localhost:8000/api/v1/cases/1/images" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "files=@image1.jpg" \
  -F "files=@image2.jpg"
```

### 4. Start Inference

```bash
curl -X POST "http://localhost:8000/api/v1/inference" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"case_id": 1}'
```

### 5. Check Status

```bash
curl -X GET "http://localhost:8000/api/v1/inference/1/status" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 6. Get Results

```bash
curl -X GET "http://localhost:8000/api/v1/cases/1/results" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 7. Download PDF

```bash
curl -X GET "http://localhost:8000/api/v1/cases/1/summary.pdf" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -o summary.pdf
```

## Project Structure

```
medical-ai-backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry point
│   ├── config.py             # Configuration settings
│   ├── database.py           # Database connection
│   ├── models.py             # SQLAlchemy models
│   ├── schemas.py            # Pydantic schemas
│   ├── celery_app.py         # Celery configuration
│   ├── api/
│   │   ├── deps.py           # Dependencies (auth, db)
│   │   ├── middleware.py     # Audit logging, rate limiting
│   │   └── routes/
│   │       ├── auth.py       # Authentication routes
│   │       ├── cases.py      # Case management routes
│   │       ├── inference.py  # Inference routes
│   │       └── results.py    # Results routes
│   ├── core/
│   │   ├── security.py       # JWT, password hashing
│   │   ├── audit.py          # Audit logging utilities
│   │   └── pdf_generator.py  # PDF generation and signing
│   └── tasks/
│       └── inference.py      # Celery inference tasks
├── alembic/
│   ├── versions/             # Migration files
│   ├── env.py                # Alembic environment
│   └── script.py.mako        # Migration template
├── scripts/
│   └── create_test_user.py   # Utility script
├── requirements.txt          # Python dependencies
├── alembic.ini               # Alembic configuration
├── docker-compose.yml        # Docker services
└── README.md                 # Project documentation
```

## Features Implemented

✅ JWT Authentication
✅ Case Management
✅ Image Upload (multipart)
✅ Background Inference Jobs (Celery)
✅ Job Status Tracking
✅ Results API (JSON)
✅ PDF Generation with Signing
✅ Audit Logging
✅ Rate Limiting
✅ Error Handling
✅ Database Migrations (Alembic)

## Notes

- The inference task (`app/tasks/inference.py`) contains mock inference logic. Replace with your actual ML model.
- PDF signing is a placeholder. Implement proper PDF signing for production.
- Rate limiting uses in-memory storage. For production, use Redis.
- Audit logs are stored in the database. Consider archiving old logs.
- Upload directory is configurable via `UPLOAD_DIR` in `.env`.

