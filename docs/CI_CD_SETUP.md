# CI/CD Setup

The repository includes `.github/workflows/deploy-backend.yml` for manual backend deployments.

## Required GitHub Secret

- `AWS_ROLE_TO_ASSUME`: IAM role ARN trusted by GitHub Actions OIDC for this repository.

## Required Role Permissions

The role needs permission to:

- Push images to ECR repository `medical-ai-production-backend`.
- Describe/register ECS task definitions.
- Update ECS services in cluster `medical-ai-production-cluster`.
- Run and inspect one-off ECS migration tasks.
- Pass the existing ECS task and execution roles.

The current `deploy_agent` AWS user does not have IAM permissions to create this role.
