# Copyright (c) 2025 Stephen G. Pope
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.

"""
AutoEdit Render API Endpoints

Provides REST API for final render:
- POST /v1/autoedit/workflow/{id}/render - Approve and start final render
- GET /v1/autoedit/workflow/{id}/render - Get render status
- GET /v1/autoedit/workflow/{id}/result - Get final video
- POST /v1/autoedit/workflow/{id}/rerender - Re-render with different quality
"""

from flask import Blueprint, jsonify, request
from app_utils import validate_payload, queue_task_wrapper
from services.authentication import authenticate
from services.v1.autoedit.workflow import get_workflow_manager
from services.v1.autoedit.preview import (
    generate_final_render,
    estimate_render_time_for_blocks
)
from services.v1.autoedit.ffmpeg_builder import blocks_to_cuts
import logging

v1_autoedit_render_api_bp = Blueprint('v1_autoedit_render_api', __name__)
logger = logging.getLogger(__name__)


# =============================================================================
# FINAL RENDER
# =============================================================================

@v1_autoedit_render_api_bp.route('/v1/autoedit/workflow/<workflow_id>/render', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "quality": {"type": "string", "enum": ["standard", "high", "4k"]},
        "crossfade_duration": {"type": "number", "minimum": 0.01, "maximum": 0.5},
        "async_render": {"type": "boolean", "default": True}
    },
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=True)
def approve_and_render(job_id, data, **kwargs):
    """Approve blocks and start final high-quality render.

    With async_render=true (default), uses Cloud Tasks for async processing.
    With async_render=false, renders synchronously (blocks until done).

    Request body:
        {
            "quality": "high",
            "crossfade_duration": 0.025,
            "async_render": true
        }

    Returns:
        async=true: {"workflow_id": "...", "status": "rendering", "message": "Poll GET /render for status"}
        async=false: {"workflow_id": "...", "status": "completed", "output_url": "..."}
    """
    workflow_id = request.view_args.get('workflow_id')
    quality = data.get('quality', 'high')
    crossfade_duration = data.get('crossfade_duration', 0.025)
    async_render = data.get('async_render', True)

    logger.info(f"Starting final render for workflow {workflow_id} at {quality} quality (async={async_render})")

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return {"error": "Workflow not found", "workflow_id": workflow_id}, "/v1/autoedit/workflow/render", 404

        # Check workflow state
        valid_states = ["pending_review_2", "modifying_blocks", "regenerating_preview", "blocks_approved"]
        if workflow["status"] not in valid_states:
            return {
                "error": f"Cannot render. Status is '{workflow['status']}'. Expected one of: {valid_states}",
                "workflow_id": workflow_id
            }, "/v1/autoedit/workflow/render", 400

        blocks = workflow.get("blocks")
        if not blocks:
            return {"error": "No blocks available for render", "workflow_id": workflow_id}, "/v1/autoedit/workflow/render", 400

        # Async render via Cloud Tasks
        if async_render:
            try:
                from services.v1.autoedit.task_queue import continue_after_hitl2

                enqueue_result = continue_after_hitl2(
                    workflow_id,
                    quality=quality,
                    crossfade_duration=crossfade_duration
                )

                if enqueue_result.get("success"):
                    manager.set_status(workflow_id, "rendering")
                    return {
                        "workflow_id": workflow_id,
                        "status": "rendering",
                        "message": "Render started. Poll GET /workflow/{id}/render for status.",
                        "task_enqueued": enqueue_result
                    }, "/v1/autoedit/workflow/render", 202
                else:
                    logger.warning(f"Failed to enqueue render: {enqueue_result}")
                    # Fall back to sync render
                    async_render = False

            except Exception as enqueue_error:
                logger.warning(f"Async render failed to enqueue: {enqueue_error}. Falling back to sync.")
                async_render = False

        # Sync render (fallback or requested)
        if not async_render:
            # Update status to rendering
            manager.set_status(workflow_id, "rendering")

            # Get video duration
            video_duration_ms = workflow.get("stats", {}).get("original_duration_ms", 0)

            # Generate final render
            result = generate_final_render(
                workflow_id=workflow_id,
                video_url=workflow["video_url"],
                blocks=blocks,
                video_duration_ms=video_duration_ms,
                quality=quality,
                fade_duration=crossfade_duration
            )

            # Update workflow with output
            manager.set_output(
                workflow_id=workflow_id,
                output_url=result["output_url"],
                output_duration_ms=result["output_duration_ms"],
                render_time_sec=result["stats"]["render_time_sec"]
            )

            # Store the final cuts for reference
            cuts = blocks_to_cuts(blocks)
            manager.update(workflow_id, {"cuts": cuts})

            logger.info(f"Final render completed for workflow {workflow_id}: {result['output_url']}")

            return {
                "workflow_id": workflow_id,
                "status": "completed",
                "output_url": result["output_url"],
                "output_duration_ms": result["output_duration_ms"],
                "stats": result["stats"],
                "message": "Final render complete"
            }, "/v1/autoedit/workflow/render", 200

    except Exception as e:
        logger.error(f"Error rendering workflow {workflow_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        manager.set_status(workflow_id, "error", error=str(e))
        return {"error": str(e), "workflow_id": workflow_id}, "/v1/autoedit/workflow/render", 500


@v1_autoedit_render_api_bp.route('/v1/autoedit/workflow/<workflow_id>/render', methods=['GET'])
@authenticate
def get_render_status(workflow_id):
    """Get the current render status.

    Returns:
        {
            "workflow_id": "...",
            "status": "rendering|completed|error",
            "progress_percent": 45,
            "output_url": "..." (only if completed),
            "stats": {...}
        }
    """
    logger.info(f"Getting render status for workflow {workflow_id}")

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return jsonify({
                "error": "Workflow not found",
                "workflow_id": workflow_id
            }), 404

        response = {
            "workflow_id": workflow_id,
            "status": workflow["status"]
        }

        if workflow["status"] == "rendering":
            # Estimate progress (in practice, you'd track actual progress)
            response["progress_percent"] = 50  # Placeholder
            response["message"] = "Rendering in progress..."

        elif workflow["status"] == "completed":
            response["output_url"] = workflow.get("output_url")
            response["output_duration_ms"] = workflow.get("output_duration_ms")
            response["stats"] = workflow.get("stats", {})
            response["message"] = "Render complete"

        elif workflow["status"] == "error":
            response["error"] = workflow.get("error")
            response["error_details"] = workflow.get("error_details")
            response["message"] = "Render failed"

        else:
            response["message"] = f"Workflow is in '{workflow['status']}' state, not rendering"

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error getting render status for {workflow_id}: {e}")
        return jsonify({"error": str(e), "workflow_id": workflow_id}), 500


@v1_autoedit_render_api_bp.route('/v1/autoedit/workflow/<workflow_id>/result', methods=['GET'])
@authenticate
def get_result(workflow_id):
    """Get the final video result.

    Returns:
        {
            "workflow_id": "...",
            "status": "completed",
            "output_url": "https://...",
            "output_duration_ms": 27340,
            "stats": {...}
        }
    """
    logger.info(f"Getting result for workflow {workflow_id}")

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return jsonify({
                "error": "Workflow not found",
                "workflow_id": workflow_id
            }), 404

        if workflow["status"] != "completed":
            return jsonify({
                "error": f"Workflow not completed. Current status: '{workflow['status']}'",
                "workflow_id": workflow_id,
                "status": workflow["status"]
            }), 400

        output_url = workflow.get("output_url")
        if not output_url:
            return jsonify({
                "error": "No output URL available",
                "workflow_id": workflow_id
            }), 400

        return jsonify({
            "workflow_id": workflow_id,
            "status": "completed",
            "output_url": output_url,
            "output_duration_ms": workflow.get("output_duration_ms"),
            "video_url": workflow.get("video_url"),
            "stats": workflow.get("stats", {}),
            "cuts": workflow.get("cuts", []),
            "created_at": workflow.get("created_at"),
            "updated_at": workflow.get("updated_at")
        }), 200

    except Exception as e:
        logger.error(f"Error getting result for {workflow_id}: {e}")
        return jsonify({"error": str(e), "workflow_id": workflow_id}), 500


@v1_autoedit_render_api_bp.route('/v1/autoedit/workflow/<workflow_id>/rerender', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "quality": {"type": "string", "enum": ["standard", "high", "4k"]},
        "crossfade_duration": {"type": "number", "minimum": 0.01, "maximum": 0.5}
    },
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def rerender(job_id, data, **kwargs):
    """Re-render the video with different quality settings.

    Uses the already-approved blocks without requiring another HITL review.

    Request body:
        {
            "quality": "4k",
            "crossfade_duration": 0.025
        }

    Returns:
        Same as /render endpoint
    """
    workflow_id = request.view_args.get('workflow_id')
    quality = data.get('quality', 'high')
    crossfade_duration = data.get('crossfade_duration', 0.025)

    logger.info(f"Re-rendering workflow {workflow_id} at {quality} quality")

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return {"error": "Workflow not found", "workflow_id": workflow_id}, "/v1/autoedit/workflow/rerender", 404

        # Only allow re-render if workflow was previously completed or had blocks approved
        valid_states = ["completed", "blocks_approved", "error"]
        if workflow["status"] not in valid_states:
            return {
                "error": f"Cannot re-render. Status is '{workflow['status']}'. Must be completed first.",
                "workflow_id": workflow_id
            }, "/v1/autoedit/workflow/rerender", 400

        blocks = workflow.get("blocks")
        if not blocks:
            return {"error": "No blocks available for re-render", "workflow_id": workflow_id}, "/v1/autoedit/workflow/rerender", 400

        # Update status to rendering
        manager.set_status(workflow_id, "rendering")

        # Get video duration
        video_duration_ms = workflow.get("stats", {}).get("original_duration_ms", 0)

        # Generate final render
        result = generate_final_render(
            workflow_id=workflow_id,
            video_url=workflow["video_url"],
            blocks=blocks,
            video_duration_ms=video_duration_ms,
            quality=quality,
            fade_duration=crossfade_duration
        )

        # Update workflow with new output
        manager.set_output(
            workflow_id=workflow_id,
            output_url=result["output_url"],
            output_duration_ms=result["output_duration_ms"],
            render_time_sec=result["stats"]["render_time_sec"]
        )

        logger.info(f"Re-render completed for workflow {workflow_id}: {result['output_url']}")

        return {
            "workflow_id": workflow_id,
            "status": "completed",
            "output_url": result["output_url"],
            "output_duration_ms": result["output_duration_ms"],
            "stats": result["stats"],
            "message": f"Re-render complete at {quality} quality"
        }, "/v1/autoedit/workflow/rerender", 200

    except Exception as e:
        logger.error(f"Error re-rendering workflow {workflow_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        manager.set_status(workflow_id, "error", error=str(e))
        return {"error": str(e), "workflow_id": workflow_id}, "/v1/autoedit/workflow/rerender", 500


@v1_autoedit_render_api_bp.route('/v1/autoedit/workflow/<workflow_id>/estimate', methods=['GET'])
@authenticate
def estimate_render(workflow_id):
    """Get an estimate of render time for this workflow.

    Query params:
        quality: Render quality (standard, high, 4k)

    Returns:
        {
            "workflow_id": "...",
            "estimated_preview_seconds": 12,
            "estimated_render_seconds": {...}
        }
    """
    quality = request.args.get('quality', 'high')

    logger.info(f"Estimating render time for workflow {workflow_id}")

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return jsonify({
                "error": "Workflow not found",
                "workflow_id": workflow_id
            }), 404

        blocks = workflow.get("blocks", [])

        if not blocks:
            return jsonify({
                "error": "No blocks available for estimation",
                "workflow_id": workflow_id
            }), 400

        # Calculate estimates
        preview_time = estimate_render_time_for_blocks(blocks, "preview")
        render_times = {
            "standard": estimate_render_time_for_blocks(blocks, "standard"),
            "high": estimate_render_time_for_blocks(blocks, "high"),
            "4k": estimate_render_time_for_blocks(blocks, "4k")
        }

        return jsonify({
            "workflow_id": workflow_id,
            "block_count": len(blocks),
            "estimated_preview_seconds": round(preview_time, 1),
            "estimated_render_seconds": {
                k: round(v, 1) for k, v in render_times.items()
            },
            "recommended_quality": quality
        }), 200

    except Exception as e:
        logger.error(f"Error estimating render for {workflow_id}: {e}")
        return jsonify({"error": str(e), "workflow_id": workflow_id}), 500
