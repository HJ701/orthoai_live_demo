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
- DNS validation for `api.demo.orthoai.co` completed.
- ACM certificate for `api.demo.orthoai.co` is issued and attached to the ALB HTTPS listener.
- Git LFS checkpoint downloaded locally:
  - `orthoai_multimodel_best_model/weights/late_fusion_best.ckpt`
  - Expected size: `713964702` bytes
- Client model source files are now present:
  - `OrthoPatientFusion/ortho_patient_fusion_core.py`
  - `data_pipeline.py`
  - `train_exp1_6_malocclusion.py`
- Python compile check passes for the backend and model source files.

## Remaining Before Deploying New Model Code

- Merge `integrate-multimodel-backend` into `main`.
- Build and push the new backend Docker image to ECR.
- Update ECS API and Celery services to the new task definition/image.
- Run database migrations if needed.
- Verify `/health`, `/ready`, auth, upload, inference, results, and PDF download paths.
- Verify the model loads in the production container with the checkpoint and Python dependencies.

## Deployment Notes

- The current deployed API does not expose `/ready`; that endpoint exists only in the integration branch until a new image is built and deployed.
- Do not commit `.aws-local/`.
- Do not commit `.merge-backup/`.
- Do not recommit the expanded checkpoint as a normal Git file; it must remain managed by Git LFS.
- Current AWS CLI profile must be valid before deployment; `InvalidClientTokenId` means the local access key must be replaced or reactivated.
