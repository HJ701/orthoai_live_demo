# Production AWS Checklist

## Current Routing

- Wix frontend: `https://demo.orthoai.co`
- AWS backend: `https://api.demo.orthoai.co`
- Existing legacy backend alias: `https://demo-backend.orthoai.co`

## AWS Resources

- Region: `eu-north-1`
- ECR: `medical-ai-production-backend`
- ECS cluster: `medical-ai-production-cluster`
- API service: `medical-ai-production-backend-service`
- Celery service: `medical-ai-production-celery-service`
- ALB: `medical-ai-production-alb-1314844270.eu-north-1.elb.amazonaws.com`
- RDS: `medical-ai-production-db`
- Redis: `medical-ai-production-redis-001`
- S3 uploads bucket: `medical-ai-production-assets`

## Verified

- `https://api.demo.orthoai.co/health` returns `200`.
- `https://api.demo.orthoai.co/ready` returns `ready` with database and Redis checks passing.
- `https://api.demo.orthoai.co/docs` returns `200`.
- DNS validation for `api.demo.orthoai.co` completed.
- ACM certificate for `api.demo.orthoai.co` is issued and attached to the ALB HTTPS listener.
- Docker image pushed to ECR:
  - Tag: `fd3557a`
  - Digest: `sha256:80732c53845e283949b642e6de1e58a0cce7f601057db77327f5b27d677bca2b`
- ECS services are stable:
  - Backend task definition: `medical-ai-production-backend:7`
  - Celery task definition: `medical-ai-production-celery:8`
- RDS PostgreSQL instance `medical-ai-production-db` created in private subnets.
- Alembic migrations applied through revision `3279515f6aee`.
- Git LFS checkpoint downloaded locally:
  - `orthoai_multimodel_best_model/weights/late_fusion_best.ckpt`
  - Expected size: `713964702` bytes
- Client model source files are now present:
  - `OrthoPatientFusion/ortho_patient_fusion_core.py`
  - `data_pipeline.py`
  - `train_exp1_6_malocclusion.py`
- Python compile check passes for the backend and model source files.

## Remaining

- Run authenticated end-to-end workflow from Wix frontend to AWS backend.
- Test upload, inference, results, and PDF download paths with real user data.
- Trigger a real inference job and verify the model loads successfully inside the Celery worker.
- Move sensitive ECS environment values into AWS Secrets Manager or SSM Parameter Store.
- Set up or confirm CI/CD for future image builds and ECS deployments.
- Add CloudWatch alarms for ALB 5xx, ECS task failures, RDS health, Redis health, and high latency.

## Deployment Notes

- The deployed API now exposes `/ready`.
- Do not commit `.aws-local/`.
- Do not commit `.merge-backup/`.
- Do not recommit the expanded checkpoint as a normal Git file; it must remain managed by Git LFS.
- Use CPU-only PyTorch wheels in Docker builds unless GPU-backed ECS capacity is introduced.
