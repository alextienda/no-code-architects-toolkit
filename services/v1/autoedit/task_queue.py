# Copyright (c) 2025 Stephen G. Pope
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

"""
AutoEdit Task Queue Service

Uses Google Cloud Tasks for robust async task processing.
Handles automatic pipeline execution: transcribe -> analyze -> (HITL 1) -> process -> preview -> (HITL 2) -> render

Environment Variables:
    GCP_PROJECT_ID: GCP project ID
    GCP_LOCATION: GCP region (default: us-central1)
    CLOUD_TASKS_QUEUE: Queue name (default: autoedit-pipeline)
    SERVICE_URL: URL of this service for task callbacks
"""

import os
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Configuration
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "autoedit-at")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "us-central1")
CLOUD_TASKS_QUEUE = os.environ.get("CLOUD_TASKS_QUEUE", "autoedit-pipeline")
SERVICE_URL = os.environ.get("SERVICE_URL", "https://nca-toolkit-djwypu7xmq-uc.a.run.app")

# Task types that can be enqueued
TASK_TYPES = {
    "transcribe": "/v1/autoedit/tasks/transcribe",
    "analyze": "/v1/autoedit/tasks/analyze",
    "analyze_broll": "/v1/autoedit/tasks/analyze-broll",  # B-Roll visual analysis
    "process": "/v1/autoedit/tasks/process",
    "preview": "/v1/autoedit/tasks/preview",
    "render": "/v1/autoedit/tasks/render",
    # Multi-video context tasks (Fase 4B)
    "generate_embeddings": "/v1/autoedit/tasks/generate-embeddings",
    "generate_summary": "/v1/autoedit/tasks/generate-summary",
    "consolidate": "/v1/autoedit/tasks/consolidate"
}

# Pipeline flow: what task comes after each task
PIPELINE_FLOW = {
    "transcribe": "analyze",      # After transcribe -> analyze
    "analyze": None,              # After analyze -> HITL 1 (stop)
    "process": "preview",         # After process -> preview
    "preview": None,              # After preview -> HITL 2 (stop)
    "render": None                # After render -> done
}


def get_tasks_client():
    """Get Cloud Tasks client with proper credentials."""
    try:
        from google.cloud import tasks_v2
        from google.oauth2 import service_account

        # Try to use service account credentials if available
        gcp_sa_credentials = os.environ.get("GCP_SA_CREDENTIALS")
        if gcp_sa_credentials:
            credentials_info = json.loads(gcp_sa_credentials)
            credentials = service_account.Credentials.from_service_account_info(credentials_info)
            return tasks_v2.CloudTasksClient(credentials=credentials)

        # Fall back to default credentials (ADC)
        return tasks_v2.CloudTasksClient()
    except Exception as e:
        logger.error(f"Failed to create Cloud Tasks client: {e}")
        raise


def enqueue_task(
    task_type: str,
    workflow_id: str,
    payload: Optional[Dict[str, Any]] = None,
    delay_seconds: int = 0
) -> Dict[str, Any]:
    """
    Enqueue a task for async processing.

    Args:
        task_type: Type of task (transcribe, analyze, process, preview, render)
        workflow_id: The workflow ID to process
        payload: Additional payload data for the task
        delay_seconds: Delay before executing (for rate limiting)

    Returns:
        dict with task_name and success status
    """
    if task_type not in TASK_TYPES:
        raise ValueError(f"Invalid task type: {task_type}. Valid types: {list(TASK_TYPES.keys())}")

    try:
        from google.cloud import tasks_v2
        from google.protobuf import timestamp_pb2
        import datetime

        client = get_tasks_client()

        # Build the queue path
        queue_path = client.queue_path(GCP_PROJECT_ID, GCP_LOCATION, CLOUD_TASKS_QUEUE)

        # Build the task URL
        task_url = f"{SERVICE_URL}{TASK_TYPES[task_type]}"

        # Build the payload
        task_payload = {
            "workflow_id": workflow_id,
            "task_type": task_type,
            **(payload or {})
        }

        # Get API key for authentication
        api_key = os.environ.get("API_KEY", "")

        # Create the task
        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": task_url,
                "headers": {
                    "Content-Type": "application/json",
                    "X-API-Key": api_key,
                    "X-Cloud-Tasks": "true"  # Marker to identify task requests
                },
                "body": json.dumps(task_payload).encode()
            }
        }

        # Add delay if specified
        if delay_seconds > 0:
            schedule_time = timestamp_pb2.Timestamp()
            schedule_time.FromDatetime(
                datetime.datetime.utcnow() + datetime.timedelta(seconds=delay_seconds)
            )
            task["schedule_time"] = schedule_time

        # Create the task
        response = client.create_task(parent=queue_path, task=task)

        logger.info(f"Enqueued task {task_type} for workflow {workflow_id}: {response.name}")

        return {
            "success": True,
            "task_name": response.name,
            "task_type": task_type,
            "workflow_id": workflow_id
        }

    except Exception as e:
        logger.error(f"Failed to enqueue task {task_type} for workflow {workflow_id}: {e}")
        return {
            "success": False,
            "error": str(e),
            "task_type": task_type,
            "workflow_id": workflow_id
        }


def enqueue_next_task(current_task: str, workflow_id: str, payload: Optional[Dict] = None) -> Optional[Dict]:
    """
    Enqueue the next task in the pipeline flow.

    Args:
        current_task: The task that just completed
        workflow_id: The workflow ID
        payload: Additional payload for the next task

    Returns:
        Result of enqueueing, or None if no next task (HITL point)
    """
    next_task = PIPELINE_FLOW.get(current_task)

    if next_task is None:
        logger.info(f"No automatic next task after {current_task} for workflow {workflow_id} (HITL point)")
        return None

    logger.info(f"Auto-enqueueing {next_task} after {current_task} for workflow {workflow_id}")
    return enqueue_task(next_task, workflow_id, payload)


def start_pipeline(workflow_id: str, language: str = "es", style: str = "dynamic") -> Dict[str, Any]:
    """
    Start the AutoEdit pipeline for a workflow.

    This will enqueue the first task (transcribe), which will automatically
    chain to analyze. The pipeline stops at HITL points.

    Args:
        workflow_id: The workflow ID to process
        language: Language code for transcription
        style: Analysis style for Gemini

    Returns:
        Result of enqueueing the first task
    """
    logger.info(f"Starting pipeline for workflow {workflow_id}")

    return enqueue_task(
        task_type="transcribe",
        workflow_id=workflow_id,
        payload={
            "language": language,
            "style": style  # Pass through for analyze step
        }
    )


def continue_after_hitl1(workflow_id: str, config: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Continue the pipeline after HITL 1 (XML review).

    Enqueues the process task, which will automatically chain to preview.

    Args:
        workflow_id: The workflow ID
        config: Processing configuration (padding, thresholds, etc.)

    Returns:
        Result of enqueueing process task
    """
    logger.info(f"Continuing pipeline after HITL 1 for workflow {workflow_id}")

    return enqueue_task(
        task_type="process",
        workflow_id=workflow_id,
        payload={"config": config or {}}
    )


def continue_after_hitl2(workflow_id: str, quality: str = "high", crossfade_duration: float = 0.025) -> Dict[str, Any]:
    """
    Continue the pipeline after HITL 2 (preview review).

    Enqueues the render task for final video generation.

    Args:
        workflow_id: The workflow ID
        quality: Render quality (standard, high, 4k)
        crossfade_duration: Crossfade duration in seconds

    Returns:
        Result of enqueueing render task
    """
    logger.info(f"Continuing pipeline after HITL 2 for workflow {workflow_id}")

    return enqueue_task(
        task_type="render",
        workflow_id=workflow_id,
        payload={
            "quality": quality,
            "crossfade_duration": crossfade_duration
        }
    )


def start_project_pipeline(
    project_id: str,
    parallel_limit: int = 3,
    webhook_url: Optional[str] = None,
    workflow_ids: Optional[list] = None,
    include_failed: bool = False
) -> Dict[str, Any]:
    """
    Start batch processing for videos in a project.

    Enqueues transcription tasks for workflows in "startable" states.
    Only processes workflows with status "created" (or "error" if include_failed=True).
    Tasks are staggered to respect parallel_limit.

    Args:
        project_id: The project ID to process
        parallel_limit: Max workflows to process in parallel (default 3)
        webhook_url: Optional webhook for progress notifications
        workflow_ids: Optional list of specific workflow IDs to process (must belong to project)
        include_failed: If True, also process workflows with status "error" (retry failed)

    Returns:
        Result dict with tasks_enqueued count, skipped details, and errors
    """
    from services.v1.autoedit.project import get_project
    from services.v1.autoedit.workflow import get_workflow

    logger.info(f"Starting batch pipeline for project {project_id} (parallel_limit={parallel_limit}, include_failed={include_failed})")

    project = get_project(project_id)
    if not project:
        return {
            "success": False,
            "error": "Project not found",
            "project_id": project_id
        }

    project_workflow_ids = project.get("workflow_ids", [])
    if not project_workflow_ids:
        return {
            "success": False,
            "error": "No videos in project",
            "project_id": project_id
        }

    # Get project options for all workflows
    project_options = project.get("options", {})
    language = project_options.get("language", "es")
    style = project_options.get("style", "dynamic")

    # Define startable states
    startable_states = ["created"]
    if include_failed:
        startable_states.append("error")

    # Determine target workflows
    invalid_workflow_ids = []
    if workflow_ids:
        # Filter to only workflows that belong to this project
        target_workflow_ids = []
        for wf_id in workflow_ids:
            if wf_id in project_workflow_ids:
                target_workflow_ids.append(wf_id)
            else:
                invalid_workflow_ids.append(wf_id)
        if invalid_workflow_ids:
            logger.warning(f"Invalid workflow_ids (not in project): {invalid_workflow_ids}")
    else:
        # Use all project workflows
        target_workflow_ids = project_workflow_ids

    tasks_enqueued = []
    errors = []

    # Filter by status and track skipped workflows
    pending_workflows = []
    skipped_by_status = {}

    for wf_id in target_workflow_ids:
        wf = get_workflow(wf_id)
        if not wf:
            errors.append({"workflow_id": wf_id, "error": "Workflow not found"})
            continue

        status = wf.get("status", "unknown")
        if status in startable_states:
            pending_workflows.append(wf_id)
        else:
            # Group skipped workflows by status
            if status not in skipped_by_status:
                skipped_by_status[status] = []
            skipped_by_status[status].append(wf_id)

    logger.info(
        f"Project {project_id}: {len(pending_workflows)} startable workflows, "
        f"{sum(len(v) for v in skipped_by_status.values())} skipped, "
        f"out of {len(target_workflow_ids)} target workflows"
    )

    # Enqueue tasks with staggered delays for parallel processing
    for i, workflow_id in enumerate(pending_workflows):
        # Calculate delay to stagger starts (respect parallel_limit)
        batch_number = i // parallel_limit
        delay_seconds = batch_number * 5  # 5 second stagger between batches

        try:
            result = enqueue_task(
                task_type="transcribe",
                workflow_id=workflow_id,
                payload={
                    "language": language,
                    "style": style,
                    "project_id": project_id,
                    "webhook_url": webhook_url
                },
                delay_seconds=delay_seconds
            )

            if result.get("success"):
                tasks_enqueued.append({
                    "workflow_id": workflow_id,
                    "task_name": result.get("task_name"),
                    "delay_seconds": delay_seconds
                })
            else:
                errors.append({
                    "workflow_id": workflow_id,
                    "error": result.get("error")
                })

        except Exception as e:
            errors.append({
                "workflow_id": workflow_id,
                "error": str(e)
            })

    # Build enhanced response
    skipped_count = sum(len(v) for v in skipped_by_status.values())

    return {
        "success": len(tasks_enqueued) > 0 or (len(pending_workflows) == 0 and skipped_count > 0),
        "project_id": project_id,
        "tasks_enqueued": len(tasks_enqueued),
        "total_workflows": len(project_workflow_ids),
        "pending_workflows": len(pending_workflows),
        "skipped_count": skipped_count,
        "skipped_by_status": skipped_by_status if skipped_by_status else None,
        "invalid_workflow_ids": invalid_workflow_ids if invalid_workflow_ids else None,
        "tasks": tasks_enqueued,
        "errors": errors if errors else None
    }


# Fallback for local development without Cloud Tasks
def enqueue_task_local(
    task_type: str,
    workflow_id: str,
    payload: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Local fallback that executes tasks synchronously.
    Used when Cloud Tasks is not available (local development).
    """
    import requests

    task_url = f"http://localhost:8080{TASK_TYPES[task_type]}"
    api_key = os.environ.get("API_KEY", "")

    task_payload = {
        "workflow_id": workflow_id,
        "task_type": task_type,
        **(payload or {})
    }

    try:
        response = requests.post(
            task_url,
            json=task_payload,
            headers={
                "X-API-Key": api_key,
                "X-Cloud-Tasks": "true"
            },
            timeout=300  # 5 minutes for long tasks
        )

        return {
            "success": response.status_code == 200,
            "task_type": task_type,
            "workflow_id": workflow_id,
            "response": response.json() if response.status_code == 200 else response.text
        }
    except Exception as e:
        logger.error(f"Local task execution failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "task_type": task_type,
            "workflow_id": workflow_id
        }


# ============================================================================
# Multi-Video Context Task Functions (Fase 4B)
# ============================================================================

def enqueue_embeddings_task(
    workflow_id: str,
    project_id: Optional[str] = None,
    video_url: Optional[str] = None,
    video_duration_sec: Optional[float] = None
) -> Dict[str, Any]:
    """
    Enqueue a task to generate video embeddings using TwelveLabs.

    Args:
        workflow_id: The workflow ID
        project_id: Optional project ID for context
        video_url: Video URL (if not in workflow)
        video_duration_sec: Known duration to choose sync/async

    Returns:
        Task enqueueing result
    """
    logger.info(f"Enqueuing embeddings task for workflow {workflow_id}")

    return enqueue_task(
        task_type="generate_embeddings",
        workflow_id=workflow_id,
        payload={
            "project_id": project_id,
            "video_url": video_url,
            "video_duration_sec": video_duration_sec
        }
    )


def enqueue_summary_task(
    workflow_id: str,
    project_id: str,
    sequence_index: int
) -> Dict[str, Any]:
    """
    Enqueue a task to generate video summary for context.

    Args:
        workflow_id: The workflow ID
        project_id: The project ID
        sequence_index: Video position in project sequence

    Returns:
        Task enqueueing result
    """
    logger.info(f"Enqueuing summary task for workflow {workflow_id} (seq {sequence_index})")

    return enqueue_task(
        task_type="generate_summary",
        workflow_id=workflow_id,
        payload={
            "project_id": project_id,
            "sequence_index": sequence_index
        }
    )


def enqueue_consolidation_task(
    project_id: str,
    force_regenerate: bool = False,
    redundancy_threshold: float = 0.85,
    auto_apply: bool = False,
    webhook_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Enqueue a project consolidation task.

    This will:
    1. Generate embeddings for all videos (if needed)
    2. Generate summaries (if needed)
    3. Detect cross-video redundancies
    4. Analyze narrative structure
    5. Generate recommendations

    Args:
        project_id: The project ID
        force_regenerate: Force regeneration of embeddings/summaries
        redundancy_threshold: Similarity threshold (default: 0.85)
        auto_apply: Auto-apply recommendations (skip HITL 3)
        webhook_url: Webhook for async notification

    Returns:
        Task enqueueing result
    """
    logger.info(f"Enqueuing consolidation task for project {project_id}")

    return enqueue_task(
        task_type="consolidate",
        workflow_id=f"project_{project_id}",  # Use project ID as workflow_id
        payload={
            "project_id": project_id,
            "force_regenerate": force_regenerate,
            "redundancy_threshold": redundancy_threshold,
            "auto_apply": auto_apply,
            "webhook_url": webhook_url
        }
    )


def start_project_embeddings(
    project_id: str,
    parallel_limit: int = 2
) -> Dict[str, Any]:
    """
    Generate embeddings for all videos in a project.

    Args:
        project_id: The project ID
        parallel_limit: Max concurrent embedding tasks

    Returns:
        Result with tasks enqueued
    """
    from services.v1.autoedit.project import get_project, update_project
    from services.v1.autoedit.workflow import get_workflow
    from services.v1.autoedit.twelvelabs_embeddings import load_embeddings_from_gcs

    logger.info(f"Starting embeddings generation for project {project_id}")

    project = get_project(project_id)
    if not project:
        return {
            "success": False,
            "error": "Project not found",
            "project_id": project_id
        }

    # Update consolidation state
    update_project(project_id, {"consolidation_state": "generating_embeddings"})

    workflow_ids = project.get("workflow_ids", [])
    tasks_enqueued = []
    already_have = []
    errors = []

    for i, wf_id in enumerate(workflow_ids):
        # Check if embeddings already exist
        existing = load_embeddings_from_gcs(wf_id)
        if existing:
            already_have.append(wf_id)
            continue

        # Get workflow for video URL and duration
        wf = get_workflow(wf_id)
        if not wf:
            errors.append({"workflow_id": wf_id, "error": "Workflow not found"})
            continue

        video_url = wf.get("video_url")
        duration = wf.get("stats", {}).get("original_duration_ms", 0) / 1000

        # Stagger tasks
        batch_number = len(tasks_enqueued) // parallel_limit
        delay_seconds = batch_number * 10  # 10 second stagger

        try:
            result = enqueue_task(
                task_type="generate_embeddings",
                workflow_id=wf_id,
                payload={
                    "project_id": project_id,
                    "video_url": video_url,
                    "video_duration_sec": duration
                },
                delay_seconds=delay_seconds
            )

            if result.get("success"):
                tasks_enqueued.append({
                    "workflow_id": wf_id,
                    "task_name": result.get("task_name"),
                    "delay_seconds": delay_seconds
                })
            else:
                errors.append({"workflow_id": wf_id, "error": result.get("error")})

        except Exception as e:
            errors.append({"workflow_id": wf_id, "error": str(e)})

    return {
        "success": True,
        "project_id": project_id,
        "tasks_enqueued": len(tasks_enqueued),
        "already_have_embeddings": len(already_have),
        "total_workflows": len(workflow_ids),
        "tasks": tasks_enqueued,
        "errors": errors if errors else None
    }
