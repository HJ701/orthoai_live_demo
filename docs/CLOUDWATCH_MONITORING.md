# CloudWatch Monitoring

## Dashboard

- Dashboard name: `OrthoAI-Production`
- Region: `eu-north-1`

The dashboard covers:

- ALB request count, 5xx errors, latency, and target health
- ECS backend and Celery CPU/memory
- RDS CPU, connections, free storage, and free memory
- Redis CPU, connections, and free memory
- Application error log metric

## Alerts

- SNS topic: `orthoai-production-alerts`
- Topic ARN: `arn:aws:sns:eu-north-1:100161936735:orthoai-production-alerts`

Configured alarms:

- `OrthoAI-Application-Errors`
- `OrthoAI-ALB-ELB-5XX`
- `OrthoAI-ALB-Target-5XX`
- `OrthoAI-ALB-High-Latency`
- `OrthoAI-ALB-Unhealthy-Targets`
- `OrthoAI-ECS-Backend-CPU-High`
- `OrthoAI-ECS-Backend-Memory-High`
- `OrthoAI-ECS-Celery-CPU-High`
- `OrthoAI-ECS-Celery-Memory-High`
- `OrthoAI-RDS-CPU-High`
- `OrthoAI-RDS-Free-Storage-Low`
- `OrthoAI-RDS-Free-Memory-Low`
- `OrthoAI-RDS-Connections-High`
- `OrthoAI-Redis-CPU-High`
- `OrthoAI-Redis-Free-Memory-Low`
- `OrthoAI-Redis-Connections-High`

Some alarms may show `INSUFFICIENT_DATA` immediately after creation until CloudWatch receives enough datapoints.

## Notification Subscription

The SNS topic exists, but at least one subscription should be added for real alert delivery.

Example:

```powershell
.\venv\awscli\Scripts\python.exe -m awscli sns subscribe `
  --topic-arn arn:aws:sns:eu-north-1:100161936735:orthoai-production-alerts `
  --protocol email `
  --notification-endpoint alerts@example.com `
  --profile orthoai-setup `
  --region eu-north-1
```

The recipient must confirm the subscription from the email AWS sends.
