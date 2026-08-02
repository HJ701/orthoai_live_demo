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
- Separated patient-level classification and quantitative dental instance segmentation

## v2 model integration

The v2 pilot runs the existing malocclusion classifier alongside a 31-class dental YOLOv8 segmentation model. Outputs, confidence scores, provenance, and timings remain task-specific; no cross-model score fusion is performed. The stock 91-class COCO DINO checkpoint is registered as initialization-only and is blocked from inference until dental fine-tuning and validation are complete.

See [docs/MODEL_INTEGRATION_V2.md](docs/MODEL_INTEGRATION_V2.md) for the result contract, quantitative measurements, fail-closed controls, artifact roles, and GPU deployment settings.

## Research Mode v3

Research Mode v3 is the prospective HCI study workflow at `/research`. It is
separate from the legacy clinical-validation demo and provides:

- a blank, AI-blinded clinician assessment that must be locked server-side;
- an owner-only source-image viewer that exposes no result or patient metadata;
- a controlled AI reveal with an immutable payload and model/UI/epoch provenance;
- a separate locked post-AI decision and active-time interaction telemetry;
- governed clinician, reviewer, adjudicator, and research-administrator roles;
- blinded source-image review by independent reviewers;
- adjudication only after the configured number of distinct reviews;
- versioned study instruments, append-only responses and corrections;
- a de-identified linked export for research analysis.

The architecture and component responsibilities are documented in
[docs/RESEARCH_MODE_V3_ARCHITECTURE.md](docs/RESEARCH_MODE_V3_ARCHITECTURE.md).
The research rationale and release gates are in
[docs/ORTHOAI_PILOT_V3_RESEARCH_REQUIREMENTS.md](docs/ORTHOAI_PILOT_V3_RESEARCH_REQUIREMENTS.md).

Development bootstrap is disabled by default. For an isolated local workspace,
set `RESEARCH_BOOTSTRAP_ENABLED=true` and restrict
`RESEARCH_ADMIN_EMAILS` to the signed-in administrator. Never enable bootstrap
in production; the production configuration validator rejects it.

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
- `GET /api/v1/research/context` - Resolve governed study identity and epoch
- `POST /api/v1/research/episodes` - Start a blinded decision episode
- `GET /api/v1/research/episodes/{id}/source-case` - View clinician source-image metadata without AI output
- `POST /api/v1/research/episodes/{id}/pre-ai` - Lock unaided assessment
- `POST /api/v1/research/episodes/{id}/reveal` - Reveal and snapshot AI
- `POST /api/v1/research/episodes/{id}/final` - Lock post-AI decision
- `GET /api/v1/research/reference-queue` - List blinded review cases
- `POST /api/v1/research/episodes/{id}/adjudication` - Lock reference standard
- `GET /api/v1/research/studies/{code}/export` - Export linked research data

## Verification

```bash
python -m pytest -q
alembic upgrade head
cd frontend && npm run typecheck && npm run build
```

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
