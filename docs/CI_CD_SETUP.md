# CI/CD Setup

The repository includes `.github/workflows/deploy-backend.yml` for manual backend deployments.

## AWS Role

Created role:

```text
arn:aws:iam::100161936735:role/orthoai-github-actions-deploy-role
```

## Required GitHub Secret

Add this repository secret in GitHub:

- Name: `AWS_ROLE_TO_ASSUME`
- Value: `arn:aws:iam::100161936735:role/orthoai-github-actions-deploy-role`

Path:

```text
GitHub repo -> Settings -> Secrets and variables -> Actions -> New repository secret
```

## Required Role Permissions

The role needs permission to:

- Push images to ECR repository `medical-ai-production-backend`.
- Describe/register ECS task definitions.
- Update ECS services in cluster `medical-ai-production-cluster`.
- Run and inspect one-off ECS migration tasks.
- Pass the existing ECS task and execution roles.

The AWS OIDC provider and deploy role have been created. The remaining manual step is adding the GitHub repository secret above.
