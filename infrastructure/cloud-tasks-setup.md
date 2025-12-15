# Cloud Tasks Setup for AutoEdit Pipeline

## Overview

Cloud Tasks provides robust async task processing for the AutoEdit pipeline.
This replaces the need for frontend to orchestrate multiple API calls.

## Architecture

```
Client                      Cloud Tasks                    NCA Toolkit
  |                              |                              |
  | POST /workflow               |                              |
  |----------------------------->|                              |
  |                              | enqueue transcribe           |
  |                              |----------------------------->|
  |                              |     /tasks/transcribe        |
  |                              |                              |
  |                              |<-----------------------------|
  |                              | enqueue analyze              |
  |                              |----------------------------->|
  |                              |     /tasks/analyze           |
  |                              |                              |
  |<-----------------------------|------------------------------|
  | Poll: status=pending_review_1                               |
  |                                                             |
  | PUT /analysis (HITL 1)                                      |
  |------------------------------------------------------------>|
  |                              | enqueue process              |
  |                              |----------------------------->|
  |                              |     /tasks/process           |
  |                              |----------------------------->|
  |                              |     /tasks/preview           |
  |                              |                              |
  |<-----------------------------|------------------------------|
  | Poll: status=pending_review_2                               |
  |                                                             |
  | POST /render (HITL 2)                                       |
  |------------------------------------------------------------>|
  |                              | enqueue render               |
  |                              |----------------------------->|
  |                              |     /tasks/render            |
  |                              |                              |
  |<-----------------------------|------------------------------|
  | Poll: status=completed, output_url                          |
```

## GCP Setup Commands

### 1. Enable Cloud Tasks API

```bash
gcloud services enable cloudtasks.googleapis.com --project=autoedit-at
```

### 2. Create the Queue

```bash
# Create queue for AutoEdit pipeline
gcloud tasks queues create autoedit-pipeline \
  --location=us-central1 \
  --project=autoedit-at \
  --max-concurrent-dispatches=10 \
  --max-dispatches-per-second=5 \
  --max-attempts=3 \
  --min-backoff=10s \
  --max-backoff=300s
```

### 3. Grant Service Account Permissions

The Cloud Run service account needs permission to create tasks:

```bash
# Get the Cloud Run service account
SERVICE_ACCOUNT="nca-toolkit-sa@autoedit-at.iam.gserviceaccount.com"

# Grant Cloud Tasks Enqueuer role
gcloud projects add-iam-policy-binding autoedit-at \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/cloudtasks.enqueuer"

# Grant Cloud Tasks Task Runner role (to receive tasks)
gcloud projects add-iam-policy-binding autoedit-at \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/cloudtasks.taskRunner"
```

### 4. Update Cloud Run Service

Add required environment variables:

```bash
gcloud run services update nca-toolkit \
  --region=us-central1 \
  --project=autoedit-at \
  --update-env-vars="CLOUD_TASKS_QUEUE=autoedit-pipeline,SERVICE_URL=https://nca-toolkit-djwypu7xmq-uc.a.run.app"
```

### 5. Allow Unauthenticated Task Execution (if using OIDC)

If your Cloud Run service requires authentication, configure the task to use OIDC:

```bash
# This is handled in code - the task_queue.py sends X-API-Key header
# No additional configuration needed if using API key authentication
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CLOUD_TASKS_QUEUE` | `autoedit-pipeline` | Name of the Cloud Tasks queue |
| `GCP_PROJECT_ID` | `autoedit-at` | GCP project ID |
| `GCP_LOCATION` | `us-central1` | GCP region |
| `SERVICE_URL` | (auto-detect) | Base URL of the service for task callbacks |

## Queue Configuration

The queue is configured for:
- **Max concurrent**: 10 tasks running simultaneously
- **Rate limit**: 5 tasks/second dispatch rate
- **Retries**: 3 attempts with exponential backoff (10s to 5min)

## Monitoring

### View Queue Status
```bash
gcloud tasks queues describe autoedit-pipeline \
  --location=us-central1 \
  --project=autoedit-at
```

### List Pending Tasks
```bash
gcloud tasks list \
  --queue=autoedit-pipeline \
  --location=us-central1 \
  --project=autoedit-at
```

### View Task Details
```bash
gcloud tasks describe TASK_ID \
  --queue=autoedit-pipeline \
  --location=us-central1 \
  --project=autoedit-at
```

## Troubleshooting

### Task fails with 401 Unauthorized
- Check that `API_KEY` environment variable is set on Cloud Run
- Verify the X-API-Key header is being sent

### Task fails with 404 Not Found
- Verify `SERVICE_URL` environment variable is correct
- Check that task handler routes are registered

### Queue not found
- Run the queue creation command
- Verify location matches `GCP_LOCATION` environment variable

### Tasks not being processed
- Check queue state: `gcloud tasks queues describe ...`
- Verify service account has correct IAM roles
