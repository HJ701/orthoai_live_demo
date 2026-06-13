# OrthoAI Frontend

Local development targets the FastAPI backend in this repository.

## Backend

```bash
ENVIRONMENT=development \
DATABASE_URL=sqlite:///./data/local_e2e.db \
ORTHOAI_CLINICAL_DB=./data/orthoai_clinical_e2e.db \
AUTO_CREATE_TABLES=true \
DEV_EXPOSE_OTP=true \
DEV_MOCK_INFERENCE=true \
CELERY_TASK_ALWAYS_EAGER=true \
RATE_LIMIT_ENABLED=false \
AWS_S3_BUCKET_NAME= \
UPLOAD_DIR=./uploads/e2e \
PYTHONPATH=. .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8020
```

## Frontend

```bash
cd frontend
npm install
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8020 npm run dev -- --hostname 127.0.0.1 --port 3000
```

## Browser E2E

```bash
cd frontend
E2E_BASE_URL=http://127.0.0.1:3000 npm run e2e
```
