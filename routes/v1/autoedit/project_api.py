# Copyright (c) 2025
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

"""
AutoEdit Project API Endpoints

Provides REST API for managing multi-video projects.
Projects group multiple workflows (videos) together for batch processing.

Endpoints:
    POST   /v1/autoedit/project                    - Create project
    GET    /v1/autoedit/project/<id>               - Get project
    DELETE /v1/autoedit/project/<id>               - Delete project
    GET    /v1/autoedit/projects                   - List projects
    POST   /v1/autoedit/project/<id>/videos        - Add video(s)
    GET    /v1/autoedit/project/<id>/videos        - List videos
    DELETE /v1/autoedit/project/<id>/videos/<wf>   - Remove video
    POST   /v1/autoedit/project/<id>/start         - Start batch processing
    GET    /v1/autoedit/project/<id>/stats         - Get statistics
"""

from functools import wraps
from flask import Blueprint, request, jsonify
import logging

from services.authentication import authenticate
from app_utils import validate_payload, queue_task_wrapper
from services.v1.autoedit.project import (
    get_project_manager,
    create_project,
    get_project,
    update_project,
    delete_project,
    list_projects,
    add_workflow_to_project,
    remove_workflow_from_project,
    get_project_workflows,
    refresh_project_stats
)
from services.v1.autoedit.workflow import create_workflow, get_workflow

logger = logging.getLogger(__name__)

v1_autoedit_project_bp = Blueprint('v1_autoedit_project', __name__)

# =============================================================================
# SCHEMAS
# =============================================================================

CREATE_PROJECT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200,
            "description": "Project name"
        },
        "description": {
            "type": "string",
            "maxLength": 1000,
            "description": "Optional project description"
        },
        "options": {
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "default": "es",
                    "description": "Language for transcription"
                },
                "style": {
                    "type": "string",
                    "enum": ["dynamic", "moderate", "conservative"],
                    "default": "dynamic",
                    "description": "Analysis style"
                },
                "padding_before_ms": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 500,
                    "default": 90
                },
                "padding_after_ms": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 500,
                    "default": 90
                }
            },
            "additionalProperties": True
        }
    },
    "required": ["name"],
    "additionalProperties": False
}

ADD_VIDEOS_SCHEMA = {
    "type": "object",
    "properties": {
        "video_urls": {
            "type": "array",
            "items": {
                "type": "string",
                "format": "uri"
            },
            "minItems": 1,
            "maxItems": 50,
            "description": "List of video URLs to add (gs:// or https://)"
        },
        "workflow_ids": {
            "type": "array",
            "items": {
                "type": "string"
            },
            "description": "List of existing workflow IDs to add"
        }
    },
    "additionalProperties": False
}

START_PROJECT_SCHEMA = {
    "type": "object",
    "properties": {
        "parallel_limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "default": 3,
            "description": "Max videos to process in parallel"
        },
        "webhook_url": {
            "type": "string",
            "format": "uri",
            "description": "Webhook URL for progress notifications"
        },
        "workflow_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional: specific workflow IDs to process (must belong to project)"
        },
        "include_failed": {
            "type": "boolean",
            "default": False,
            "description": "Include failed workflows in processing (retry failed)"
        }
    },
    "additionalProperties": False
}

UPDATE_PROJECT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200
        },
        "description": {
            "type": "string",
            "maxLength": 1000
        },
        "options": {
            "type": "object",
            "additionalProperties": True
        }
    },
    "additionalProperties": False
}


# =============================================================================
# ENDPOINTS
# =============================================================================

@v1_autoedit_project_bp.route('/v1/autoedit/project', methods=['POST'])
@authenticate
@validate_payload(CREATE_PROJECT_SCHEMA)
@queue_task_wrapper(bypass_queue=True)
def create_project_endpoint(job_id, data):
    """
    Create a new multi-video project.

    Request:
        {
            "name": "Viaje a México",
            "description": "Videos del viaje Diciembre 2025",
            "options": {
                "language": "es",
                "style": "dynamic"
            }
        }

    Response:
        {
            "project_id": "proj_abc123",
            "name": "Viaje a México",
            "state": "created",
            ...
        }
    """
    try:
        name = data["name"]
        description = data.get("description")
        options = data.get("options", {})

        project_id = create_project(name, description, options)
        project_data = get_project(project_id)

        logger.info(f"Created project {project_id}: {name}")

        return {
            "status": "success",
            "message": "Project created successfully",
            **project_data
        }, "/v1/autoedit/project", 201

    except Exception as e:
        logger.error(f"Error creating project: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "status": "error",
            "error": str(e)
        }, "/v1/autoedit/project", 500


@v1_autoedit_project_bp.route('/v1/autoedit/project/<project_id>', methods=['GET'])
@authenticate
def get_project_endpoint(project_id):
    """
    Get project details by ID.

    Response:
        {
            "project_id": "proj_abc123",
            "name": "Viaje a México",
            "state": "processing",
            "workflow_ids": ["wf_1", "wf_2"],
            "stats": {...},
            ...
        }
    """
    try:
        project_data = get_project(project_id)

        if not project_data:
            return jsonify({
                "status": "error",
                "error": "Project not found",
                "project_id": project_id
            }), 404

        # Refresh stats on get
        refresh_project_stats(project_id)
        project_data = get_project(project_id)

        return jsonify({
            "status": "success",
            **project_data
        }), 200

    except Exception as e:
        logger.error(f"Error getting project {project_id}: {e}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@v1_autoedit_project_bp.route('/v1/autoedit/project/<project_id>', methods=['PUT'])
@authenticate
@validate_payload(UPDATE_PROJECT_SCHEMA)
@queue_task_wrapper(bypass_queue=True)
def update_project_endpoint(job_id, data, project_id=None):
    """
    Update project metadata.

    Request:
        {
            "name": "New Name",
            "description": "Updated description"
        }
    """
    # Get project_id from URL if not in data
    if project_id is None:
        project_id = request.view_args.get('project_id')

    try:
        project_data = get_project(project_id)
        if not project_data:
            return {
                "status": "error",
                "error": "Project not found"
            }, "/v1/autoedit/project", 404

        # Build updates
        updates = {}
        if "name" in data:
            updates["name"] = data["name"]
        if "description" in data:
            updates["description"] = data["description"]
        if "options" in data:
            current_options = project_data.get("options", {})
            current_options.update(data["options"])
            updates["options"] = current_options

        if updates:
            update_project(project_id, updates)

        project_data = get_project(project_id)

        return {
            "status": "success",
            "message": "Project updated",
            **project_data
        }, "/v1/autoedit/project", 200

    except Exception as e:
        logger.error(f"Error updating project {project_id}: {e}")
        return {
            "status": "error",
            "error": str(e)
        }, "/v1/autoedit/project", 500


@v1_autoedit_project_bp.route('/v1/autoedit/project/<project_id>', methods=['DELETE'])
@authenticate
def delete_project_endpoint(project_id):
    """
    Delete a project (does NOT delete associated workflows).
    """
    try:
        project_data = get_project(project_id)
        if not project_data:
            return jsonify({
                "status": "error",
                "error": "Project not found"
            }), 404

        deleted = delete_project(project_id)

        if deleted:
            return jsonify({
                "status": "success",
                "message": "Project deleted",
                "project_id": project_id,
                "note": "Associated workflows were NOT deleted"
            }), 200
        else:
            return jsonify({
                "status": "error",
                "error": "Failed to delete project"
            }), 500

    except Exception as e:
        logger.error(f"Error deleting project {project_id}: {e}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@v1_autoedit_project_bp.route('/v1/autoedit/projects', methods=['GET'])
@authenticate
def list_projects_endpoint():
    """
    List all projects.

    Query params:
        state: Filter by state (created, ready, processing, completed, failed)
        limit: Max results (default 50)

    Response:
        {
            "status": "success",
            "projects": [...]
        }
    """
    try:
        state = request.args.get('state')
        limit = int(request.args.get('limit', 50))

        projects = list_projects(state=state, limit=limit)

        return jsonify({
            "status": "success",
            "count": len(projects),
            "projects": projects
        }), 200

    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


# =============================================================================
# VIDEO MANAGEMENT ENDPOINTS
# =============================================================================

@v1_autoedit_project_bp.route('/v1/autoedit/project/<project_id>/videos', methods=['POST'])
@authenticate
@validate_payload(ADD_VIDEOS_SCHEMA)
@queue_task_wrapper(bypass_queue=True)
def add_videos_endpoint(job_id, data, project_id=None):
    """
    Add videos to a project.

    Can either:
    1. Add new videos by URL (creates new workflows)
    2. Add existing workflows by ID

    Request:
        {
            "video_urls": ["gs://bucket/video1.mp4", "gs://bucket/video2.mp4"]
        }
        OR
        {
            "workflow_ids": ["wf_existing_1", "wf_existing_2"]
        }

    Response:
        {
            "status": "success",
            "added": [...],
            "project": {...}
        }
    """
    if project_id is None:
        project_id = request.view_args.get('project_id')

    try:
        project_data = get_project(project_id)
        if not project_data:
            return {
                "status": "error",
                "error": "Project not found"
            }, "/v1/autoedit/project/videos", 404

        added = []
        errors = []

        # Add new videos by URL
        video_urls = data.get("video_urls", [])
        for url in video_urls:
            try:
                # Create workflow with project_id
                workflow_id = create_workflow(
                    video_url=url,
                    options={
                        "project_id": project_id,
                        **project_data.get("options", {})
                    }
                )
                add_workflow_to_project(project_id, workflow_id)
                added.append({
                    "workflow_id": workflow_id,
                    "video_url": url,
                    "status": "created"
                })
            except Exception as e:
                errors.append({
                    "video_url": url,
                    "error": str(e)
                })

        # Add existing workflows by ID
        workflow_ids = data.get("workflow_ids", [])
        for wf_id in workflow_ids:
            try:
                wf_data = get_workflow(wf_id)
                if not wf_data:
                    errors.append({
                        "workflow_id": wf_id,
                        "error": "Workflow not found"
                    })
                    continue

                add_workflow_to_project(project_id, wf_id)
                added.append({
                    "workflow_id": wf_id,
                    "video_url": wf_data.get("video_url", ""),
                    "status": "added"
                })
            except Exception as e:
                errors.append({
                    "workflow_id": wf_id,
                    "error": str(e)
                })

        # Refresh project stats
        refresh_project_stats(project_id)
        project_data = get_project(project_id)

        return {
            "status": "success" if not errors else "partial",
            "message": f"Added {len(added)} video(s) to project",
            "added": added,
            "errors": errors if errors else None,
            "project": project_data
        }, "/v1/autoedit/project/videos", 200 if not errors else 207

    except Exception as e:
        logger.error(f"Error adding videos to project {project_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "status": "error",
            "error": str(e)
        }, "/v1/autoedit/project/videos", 500


@v1_autoedit_project_bp.route('/v1/autoedit/project/<project_id>/videos', methods=['GET'])
@authenticate
def list_project_videos_endpoint(project_id):
    """
    List all videos (workflows) in a project.

    Response:
        {
            "status": "success",
            "project_id": "proj_abc123",
            "videos": [
                {
                    "workflow_id": "wf_1",
                    "status": "completed",
                    "video_url": "...",
                    "preview_url": "...",
                    "output_url": "..."
                }
            ]
        }
    """
    try:
        project_data = get_project(project_id)
        if not project_data:
            return jsonify({
                "status": "error",
                "error": "Project not found"
            }), 404

        workflows = get_project_workflows(project_id)

        return jsonify({
            "status": "success",
            "project_id": project_id,
            "count": len(workflows),
            "videos": workflows
        }), 200

    except Exception as e:
        logger.error(f"Error listing videos for project {project_id}: {e}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@v1_autoedit_project_bp.route('/v1/autoedit/project/<project_id>/videos/<workflow_id>', methods=['DELETE'])
@authenticate
def remove_video_endpoint(project_id, workflow_id):
    """
    Remove a video from a project (does NOT delete the workflow).
    """
    try:
        project_data = get_project(project_id)
        if not project_data:
            return jsonify({
                "status": "error",
                "error": "Project not found"
            }), 404

        if workflow_id not in project_data.get("workflow_ids", []):
            return jsonify({
                "status": "error",
                "error": "Workflow not in project"
            }), 404

        removed = remove_workflow_from_project(project_id, workflow_id)
        refresh_project_stats(project_id)

        if removed:
            return jsonify({
                "status": "success",
                "message": "Video removed from project",
                "workflow_id": workflow_id,
                "note": "Workflow was NOT deleted"
            }), 200
        else:
            return jsonify({
                "status": "error",
                "error": "Failed to remove video"
            }), 500

    except Exception as e:
        logger.error(f"Error removing video {workflow_id} from project {project_id}: {e}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


# =============================================================================
# BATCH PROCESSING ENDPOINTS
# =============================================================================

@v1_autoedit_project_bp.route('/v1/autoedit/project/<project_id>/start', methods=['POST'])
@authenticate
@validate_payload(START_PROJECT_SCHEMA)
@queue_task_wrapper(bypass_queue=True)
def start_project_endpoint(job_id, data, project_id=None):
    """
    Start batch processing for all videos in the project.

    This will enqueue transcription tasks for all pending videos.
    Videos are processed in parallel up to the specified limit.

    Request:
        {
            "parallel_limit": 3,
            "webhook_url": "https://..."
        }

    Response:
        {
            "status": "success",
            "message": "Started processing 5 videos",
            "tasks_enqueued": [...]
        }
    """
    if project_id is None:
        project_id = request.view_args.get('project_id')

    try:
        from services.v1.autoedit.task_queue import start_project_pipeline

        project_data = get_project(project_id)
        if not project_data:
            return {
                "status": "error",
                "error": "Project not found"
            }, "/v1/autoedit/project/start", 404

        if not project_data.get("workflow_ids"):
            return {
                "status": "error",
                "error": "No videos in project"
            }, "/v1/autoedit/project/start", 400

        parallel_limit = data.get("parallel_limit", 3)
        webhook_url = data.get("webhook_url")
        workflow_ids = data.get("workflow_ids")  # Optional: specific workflows to process
        include_failed = data.get("include_failed", False)  # Include failed workflows

        # Start the batch pipeline
        result = start_project_pipeline(
            project_id=project_id,
            parallel_limit=parallel_limit,
            webhook_url=webhook_url,
            workflow_ids=workflow_ids,
            include_failed=include_failed
        )

        # Update project state
        update_project(project_id, {"state": "processing"})

        return {
            "status": "success",
            "message": f"Started processing {result.get('tasks_enqueued', 0)} video(s)",
            **result
        }, "/v1/autoedit/project/start", 202

    except Exception as e:
        logger.error(f"Error starting project {project_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "status": "error",
            "error": str(e)
        }, "/v1/autoedit/project/start", 500


@v1_autoedit_project_bp.route('/v1/autoedit/project/<project_id>/stats', methods=['GET'])
@authenticate
def get_project_stats_endpoint(project_id):
    """
    Get aggregated statistics for a project.

    Response:
        {
            "status": "success",
            "project_id": "proj_abc123",
            "stats": {
                "total_videos": 5,
                "completed": 3,
                "pending": 1,
                "failed": 1,
                "total_original_duration_ms": 540000,
                "total_result_duration_ms": 324000,
                "avg_removal_percentage": 40.0
            }
        }
    """
    try:
        project_data = get_project(project_id)
        if not project_data:
            return jsonify({
                "status": "error",
                "error": "Project not found"
            }), 404

        # Refresh stats
        refresh_project_stats(project_id)
        project_data = get_project(project_id)

        return jsonify({
            "status": "success",
            "project_id": project_id,
            "state": project_data.get("state"),
            "state_message": project_data.get("state_message"),
            "stats": project_data.get("stats", {})
        }), 200

    except Exception as e:
        logger.error(f"Error getting stats for project {project_id}: {e}")
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500
