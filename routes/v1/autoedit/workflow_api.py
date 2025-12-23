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
AutoEdit Workflow API Endpoints

Provides REST API for AutoEdit workflow management:
- POST /v1/autoedit/workflow - Create new workflow
- GET /v1/autoedit/workflow/{id} - Get workflow status
- DELETE /v1/autoedit/workflow/{id} - Delete workflow
- GET /v1/autoedit/workflow/{id}/analysis - Get XML for HITL 1
- PUT /v1/autoedit/workflow/{id}/analysis - Submit reviewed XML
- POST /v1/autoedit/workflow/{id}/retry - Retry a stuck workflow
- POST /v1/autoedit/workflow/{id}/fail - Manually mark workflow as failed
"""

import os
import logging

from flask import Blueprint, jsonify, request
from app_utils import validate_payload, queue_task_wrapper
from services.authentication import authenticate
from services.v1.autoedit.workflow import (
    get_workflow_manager,
    WORKFLOW_STATES
)

v1_autoedit_workflow_api_bp = Blueprint('v1_autoedit_workflow_api', __name__)
logger = logging.getLogger(__name__)


# =============================================================================
# WORKFLOW LIFECYCLE
# =============================================================================

@v1_autoedit_workflow_api_bp.route('/v1/autoedit/workflow', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "video_url": {"type": "string", "format": "uri"},
        "options": {
            "type": "object",
            "properties": {
                "language": {"type": "string"},
                "style": {"type": "string", "enum": ["dynamic", "conservative", "aggressive"]},
                "skip_hitl_1": {"type": "boolean"},
                "skip_hitl_2": {"type": "boolean"},
                "webhook_url": {"type": "string", "format": "uri"}
            }
        },
        "auto_start": {"type": "boolean", "default": True},
        "id": {"type": "string"}
    },
    "required": ["video_url"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=True)
def create_workflow(job_id, data):
    """Create a new AutoEdit workflow.

    With auto_start=true (default), the pipeline automatically executes:
    1. Transcription (ElevenLabs)
    2. Analysis (Gemini)
    -> Stops at HITL 1 for user review

    Request body:
        {
            "video_url": "https://...",
            "auto_start": true,
            "options": {
                "language": "es",
                "style": "dynamic",
                "webhook_url": "https://..." (optional)
            }
        }

    Returns:
        {
            "workflow_id": "uuid",
            "status": "created" | "processing",
            "message": "..."
        }
    """
    video_url = data['video_url']
    options = data.get('options', {})
    auto_start = data.get('auto_start', True)  # Default: auto-start pipeline

    logger.info(f"Creating workflow for video: {video_url[:50]}... (auto_start={auto_start})")

    try:
        manager = get_workflow_manager()
        workflow_id = manager.create(video_url, options)

        response = {
            "workflow_id": workflow_id,
            "status": "created",
            "status_message": WORKFLOW_STATES["created"],
            "message": "Workflow created successfully"
        }

        # Auto-start pipeline if requested
        if auto_start:
            try:
                from services.v1.autoedit.task_queue import start_pipeline

                language = options.get("language", "es")
                style = options.get("style", "dynamic")

                enqueue_result = start_pipeline(workflow_id, language=language, style=style)

                if enqueue_result.get("success"):
                    response["status"] = "processing"
                    response["status_message"] = "Pipeline iniciado automáticamente"
                    response["message"] = "Workflow created and pipeline started. Poll GET /workflow/{id} until status=pending_review_1"
                    response["task_enqueued"] = enqueue_result
                    manager.set_status(workflow_id, "transcribing")
                else:
                    logger.warning(f"Failed to enqueue pipeline: {enqueue_result}")
                    response["message"] = "Workflow created but auto-start failed. Call POST /transcribe manually."
                    response["enqueue_error"] = enqueue_result.get("error")

            except Exception as enqueue_error:
                logger.warning(f"Auto-start failed: {enqueue_error}")
                response["message"] = f"Workflow created but auto-start failed: {str(enqueue_error)}. Call POST /transcribe manually."

        return response, "/v1/autoedit/workflow", 201

    except Exception as e:
        logger.error(f"Error creating workflow: {e}")
        return {"error": str(e)}, "/v1/autoedit/workflow", 500


@v1_autoedit_workflow_api_bp.route('/v1/autoedit/workflow/<workflow_id>', methods=['GET'])
@authenticate
def get_workflow_status(workflow_id):
    """Get the current status and data of a workflow.

    Returns:
        Full workflow state including status, data, and statistics
    """
    logger.info(f"Getting workflow status: {workflow_id}")

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return jsonify({
                "error": "Workflow not found",
                "workflow_id": workflow_id
            }), 404

        # Build response with relevant fields based on status
        response = {
            "workflow_id": workflow["workflow_id"],
            "status": workflow["status"],
            "status_message": workflow.get("status_message", WORKFLOW_STATES.get(workflow["status"], "")),
            "created_at": workflow["created_at"],
            "updated_at": workflow["updated_at"],
            "video_url": workflow["video_url"],
            "options": workflow.get("options", {})
        }

        # Include data based on workflow progress
        status = workflow["status"]

        if status in ["transcribed", "analyzing", "pending_review_1", "xml_approved", "processing"]:
            response["has_transcript"] = workflow.get("transcript") is not None

        if status in ["pending_review_1", "xml_approved", "processing"]:
            response["has_xml"] = workflow.get("gemini_xml") is not None

        if status in ["generating_preview", "pending_review_2", "modifying_blocks", "regenerating_preview", "rendering", "completed"]:
            response["has_blocks"] = workflow.get("blocks") is not None
            response["block_count"] = len(workflow.get("blocks", [])) if workflow.get("blocks") else 0

        if status in ["pending_review_2", "modifying_blocks", "regenerating_preview", "rendering", "completed"]:
            response["preview_url"] = workflow.get("preview_url")
            response["preview_duration_ms"] = workflow.get("preview_duration_ms")

        if status == "completed":
            response["output_url"] = workflow.get("output_url")
            response["output_duration_ms"] = workflow.get("output_duration_ms")

        if status == "error":
            response["error"] = workflow.get("error")
            response["error_details"] = workflow.get("error_details")

        # Always include stats if available
        if workflow.get("stats"):
            response["stats"] = workflow["stats"]

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error getting workflow {workflow_id}: {e}")
        return jsonify({"error": str(e), "workflow_id": workflow_id}), 500


@v1_autoedit_workflow_api_bp.route('/v1/autoedit/workflow/<workflow_id>', methods=['DELETE'])
@authenticate
def delete_workflow(workflow_id):
    """Delete a workflow and its associated data.

    Returns:
        Success message
    """
    logger.info(f"Deleting workflow: {workflow_id}")

    try:
        manager = get_workflow_manager()

        if not manager.get(workflow_id):
            return jsonify({
                "error": "Workflow not found",
                "workflow_id": workflow_id
            }), 404

        success = manager.delete(workflow_id)

        if success:
            return jsonify({
                "message": "Workflow deleted successfully",
                "workflow_id": workflow_id
            }), 200
        else:
            return jsonify({
                "error": "Failed to delete workflow",
                "workflow_id": workflow_id
            }), 500

    except Exception as e:
        logger.error(f"Error deleting workflow {workflow_id}: {e}")
        return jsonify({"error": str(e), "workflow_id": workflow_id}), 500


@v1_autoedit_workflow_api_bp.route('/v1/autoedit/workflows', methods=['GET'])
@authenticate
def list_workflows():
    """List all workflows, optionally filtered by status.

    Query params:
        status: Filter by workflow status

    Returns:
        List of workflow summaries
    """
    status_filter = request.args.get('status')

    logger.info(f"Listing workflows (status filter: {status_filter})")

    try:
        manager = get_workflow_manager()
        workflows = manager.list_workflows(status=status_filter)

        return jsonify({
            "workflows": workflows,
            "total": len(workflows),
            "filter": {"status": status_filter} if status_filter else None
        }), 200

    except Exception as e:
        logger.error(f"Error listing workflows: {e}")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# HITL 1: XML REVIEW
# =============================================================================

@v1_autoedit_workflow_api_bp.route('/v1/autoedit/workflow/<workflow_id>/analysis', methods=['GET'])
@authenticate
def get_analysis_for_review(workflow_id):
    """Get the Gemini XML analysis for HITL 1 review.

    Returns the combined XML that the frontend can render for
    user review (toggle mantener/eliminar).

    Returns:
        {
            "workflow_id": "...",
            "status": "pending_review_1",
            "combined_xml": "<resultado>...</resultado>",
            "transcript_text": "full text for reference"
        }
    """
    logger.info(f"Getting analysis for review: {workflow_id}")

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return jsonify({
                "error": "Workflow not found",
                "workflow_id": workflow_id
            }), 404

        # Check if analysis is available
        if workflow["status"] not in ["pending_review_1", "xml_approved"]:
            return jsonify({
                "error": f"Analysis not available. Workflow status is '{workflow['status']}'. Expected 'pending_review_1'.",
                "workflow_id": workflow_id,
                "current_status": workflow["status"]
            }), 400

        gemini_xml = workflow.get("gemini_xml") or workflow.get("user_xml")
        if not gemini_xml:
            return jsonify({
                "error": "No XML analysis available",
                "workflow_id": workflow_id
            }), 400

        # Build transcript text for reference
        transcript_text = ""
        if workflow.get("transcript_internal"):
            transcript_text = " ".join(
                w.get("text", "") for w in workflow["transcript_internal"]
            )

        return jsonify({
            "workflow_id": workflow_id,
            "status": workflow["status"],
            "combined_xml": gemini_xml,
            "transcript_text": transcript_text,
            "message": "Review the XML and submit modifications via PUT"
        }), 200

    except Exception as e:
        logger.error(f"Error getting analysis for {workflow_id}: {e}")
        return jsonify({"error": str(e), "workflow_id": workflow_id}), 500


@v1_autoedit_workflow_api_bp.route('/v1/autoedit/workflow/<workflow_id>/analysis', methods=['PUT'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "updated_xml": {"type": "string", "minLength": 1},
        "auto_continue": {"type": "boolean", "default": True},
        "config": {
            "type": "object",
            "properties": {
                "padding_before_ms": {"type": "number", "minimum": 0, "maximum": 500},
                "padding_after_ms": {"type": "number", "minimum": 0, "maximum": 500},
                "silence_threshold_ms": {"type": "number", "minimum": 0, "maximum": 500},
                "merge_threshold_ms": {"type": "number", "minimum": 0, "maximum": 1000}
            }
        }
    },
    "required": ["updated_xml"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=True)
def submit_reviewed_xml(job_id, data, **kwargs):
    """Submit the user-reviewed XML after HITL 1 modifications.

    With auto_continue=true (default), the pipeline automatically continues:
    1. Process XML to blocks
    2. Generate preview
    -> Stops at HITL 2 for user review

    Request body:
        {
            "updated_xml": "<resultado>...(with user changes)...</resultado>",
            "auto_continue": true,
            "config": {
                "padding_before_ms": 90,
                "padding_after_ms": 130
            }
        }

    Returns:
        {
            "workflow_id": "...",
            "status": "xml_approved" | "processing",
            "message": "..."
        }
    """
    # Get workflow_id from URL
    workflow_id = request.view_args.get('workflow_id')
    _ = job_id  # Not used for this endpoint
    endpoint = f"/v1/autoedit/workflow/{workflow_id}/analysis"

    auto_continue = data.get("auto_continue", True)
    config = data.get("config", {})

    logger.info(f"Submitting reviewed XML for workflow: {workflow_id} (auto_continue={auto_continue})")

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return {
                "error": "Workflow not found",
                "workflow_id": workflow_id
            }, endpoint, 404

        # Validate workflow is in correct state
        if workflow["status"] not in ["pending_review_1", "xml_approved"]:
            return {
                "error": f"Cannot submit XML. Workflow status is '{workflow['status']}'. Expected 'pending_review_1'.",
                "workflow_id": workflow_id
            }, endpoint, 400

        updated_xml = data["updated_xml"]

        # Basic XML validation
        if "<resultado>" not in updated_xml:
            return {
                "error": "Invalid XML format. Expected <resultado> root element.",
                "workflow_id": workflow_id
            }, endpoint, 400

        # Store the user-modified XML
        success = manager.set_user_xml(workflow_id, updated_xml)

        if not success:
            return {
                "error": "Failed to save XML",
                "workflow_id": workflow_id
            }, endpoint, 500

        response = {
            "workflow_id": workflow_id,
            "status": "xml_approved",
            "message": "XML approved. Ready for processing to blocks."
        }

        # Auto-continue pipeline if requested
        if auto_continue:
            try:
                from services.v1.autoedit.task_queue import continue_after_hitl1

                enqueue_result = continue_after_hitl1(workflow_id, config=config)

                if enqueue_result.get("success"):
                    response["status"] = "processing"
                    response["message"] = "XML approved. Processing started. Poll GET /workflow/{id} until status=pending_review_2"
                    response["task_enqueued"] = enqueue_result
                    manager.set_status(workflow_id, "processing")
                else:
                    logger.warning(f"Failed to enqueue process: {enqueue_result}")
                    response["message"] = "XML approved but auto-continue failed. Call POST /process manually."
                    response["enqueue_error"] = enqueue_result.get("error")

            except Exception as enqueue_error:
                logger.warning(f"Auto-continue failed: {enqueue_error}")
                response["message"] = f"XML approved but auto-continue failed: {str(enqueue_error)}. Call POST /process manually."

        return response, endpoint, 200

    except Exception as e:
        logger.error(f"Error submitting XML for {workflow_id}: {e}")
        return {"error": str(e), "workflow_id": workflow_id}, endpoint, 500


# =============================================================================
# TRANSCRIPTION
# =============================================================================

@v1_autoedit_workflow_api_bp.route('/v1/autoedit/workflow/<workflow_id>/transcribe', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "language": {"type": "string", "default": "es"}
    },
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def transcribe_workflow(job_id, data, **kwargs):
    """Transcribe the workflow's video using ElevenLabs.

    Request body:
        {
            "language": "es"  (optional)
        }

    Returns:
        {
            "workflow_id": "...",
            "status": "transcribed",
            "word_count": 1234,
            "duration_ms": 120000
        }
    """
    import os
    from services.v1.autoedit.pipeline import (
        transcribe_with_elevenlabs,
        transform_to_internal_format
    )

    workflow_id = request.view_args.get('workflow_id')
    language = data.get('language', 'es')
    endpoint = f"/v1/autoedit/workflow/{workflow_id}/transcribe"

    logger.info(f"Transcribing workflow {workflow_id} with language: {language}")

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return {
                "error": "Workflow not found",
                "workflow_id": workflow_id
            }, endpoint, 404

        # Check workflow state
        if workflow["status"] not in ["created", "transcribing"]:
            return {
                "error": f"Cannot transcribe. Workflow status is '{workflow['status']}'. Expected 'created'.",
                "workflow_id": workflow_id
            }, endpoint, 400

        # Update status to transcribing
        manager.set_status(workflow_id, "transcribing")

        # Get ElevenLabs API key
        elevenlabs_api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not elevenlabs_api_key:
            manager.set_status(workflow_id, "error", error="ELEVENLABS_API_KEY not configured")
            return {
                "error": "ELEVENLABS_API_KEY not configured",
                "workflow_id": workflow_id
            }, endpoint, 500

        # Transcribe with ElevenLabs
        video_url = workflow["video_url"]
        elevenlabs_result = transcribe_with_elevenlabs(video_url, elevenlabs_api_key)

        # Transform to internal format
        transcript_internal = transform_to_internal_format(elevenlabs_result)

        # Calculate duration
        duration_ms = 0
        if transcript_internal:
            duration_ms = max(w["outMs"] for w in transcript_internal)

        # Store in workflow
        manager.set_transcript(
            workflow_id,
            transcript=elevenlabs_result.get("words", []),
            transcript_internal=transcript_internal
        )

        # Update stats
        manager.update(workflow_id, {
            "stats": {
                "original_duration_ms": duration_ms,
                "word_count": len(transcript_internal)
            }
        })

        logger.info(f"Transcription complete for {workflow_id}: {len(transcript_internal)} words, {duration_ms}ms")

        return {
            "workflow_id": workflow_id,
            "status": "transcribed",
            "word_count": len(transcript_internal),
            "duration_ms": duration_ms,
            "message": "Transcription complete. Ready for Gemini analysis."
        }, endpoint, 200

    except Exception as e:
        logger.error(f"Error transcribing workflow {workflow_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        manager.set_status(workflow_id, "error", error=str(e))
        return {"error": str(e), "workflow_id": workflow_id}, endpoint, 500


# =============================================================================
# GEMINI ANALYSIS
# =============================================================================

@v1_autoedit_workflow_api_bp.route('/v1/autoedit/workflow/<workflow_id>/analyze', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "style": {"type": "string", "enum": ["dynamic", "conservative", "aggressive"]},
        "custom_prompt": {"type": "string"}
    },
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def analyze_workflow(job_id, data, **kwargs):
    """Analyze the transcript with Gemini to identify content to keep/remove.

    Request body:
        {
            "style": "dynamic",  (optional: dynamic, conservative, aggressive)
            "custom_prompt": "..." (optional)
        }

    Returns:
        {
            "workflow_id": "...",
            "status": "pending_review_1",
            "block_count": 5,
            "message": "Analysis complete. Review XML."
        }
    """
    import os
    from services.v1.autoedit.pipeline import (
        prepare_blocks_for_gemini,
        analyze_with_gemini,
        combine_gemini_outputs
    )

    workflow_id = request.view_args.get('workflow_id')
    style = data.get('style', 'dynamic')
    custom_prompt = data.get('custom_prompt')
    endpoint = f"/v1/autoedit/workflow/{workflow_id}/analyze"

    logger.info(f"Analyzing workflow {workflow_id} with style: {style}")

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return {
                "error": "Workflow not found",
                "workflow_id": workflow_id
            }, endpoint, 404

        # Check workflow state
        if workflow["status"] not in ["transcribed", "analyzing"]:
            return {
                "error": f"Cannot analyze. Workflow status is '{workflow['status']}'. Expected 'transcribed'.",
                "workflow_id": workflow_id
            }, endpoint, 400

        # Get transcript
        transcript_internal = workflow.get("transcript_internal")
        if not transcript_internal:
            return {
                "error": "No transcript available. Run transcription first.",
                "workflow_id": workflow_id
            }, endpoint, 400

        # Update status to analyzing
        manager.set_status(workflow_id, "analyzing")

        # Prepare blocks for Gemini
        blocks_data = prepare_blocks_for_gemini(transcript_internal)
        blocks = blocks_data.get("blocks", [])
        formatted_text = blocks_data.get("formatted_text", "")

        if not blocks or not formatted_text:
            return {
                "error": "No text blocks to analyze",
                "workflow_id": workflow_id
            }, endpoint, 400

        # Get GCP access token for Vertex AI
        import google.auth
        import google.auth.transport.requests

        try:
            credentials, project = google.auth.default()
            auth_req = google.auth.transport.requests.Request()
            credentials.refresh(auth_req)
            access_token = credentials.token
        except Exception as auth_error:
            logger.error(f"Failed to get GCP credentials: {auth_error}")
            return {
                "error": f"Failed to authenticate with GCP: {str(auth_error)}",
                "workflow_id": workflow_id
            }, endpoint, 500

        # Build config for Gemini
        gemini_config = {
            "gcp_project_id": os.environ.get("GCP_PROJECT_ID", "autoedit-at"),
            "gcp_location": os.environ.get("GCP_LOCATION", "us-central1"),
            "gemini_model": "gemini-2.5-pro",
            "gemini_temperature": 0.0
        }

        # Analyze with Gemini
        gemini_results = analyze_with_gemini(
            formatted_text=formatted_text,
            access_token=access_token,
            config=gemini_config
        )

        # Combine outputs into single XML
        combined_xml = combine_gemini_outputs(gemini_results)

        # Store in workflow
        manager.set_gemini_xml(workflow_id, combined_xml)

        logger.info(f"Analysis complete for {workflow_id}: {len(blocks)} blocks analyzed")

        return {
            "workflow_id": workflow_id,
            "status": "pending_review_1",
            "block_count": len(blocks),
            "message": "Analysis complete. Review and approve the XML via GET/PUT /analysis"
        }, endpoint, 200

    except Exception as e:
        logger.error(f"Error analyzing workflow {workflow_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        manager.set_status(workflow_id, "error", error=str(e))
        return {"error": str(e), "workflow_id": workflow_id}, endpoint, 500


# =============================================================================
# WORKFLOW RECOVERY (RETRY / FAIL)
# =============================================================================

# Mapping of stuck states to the step that should be retried
RETRY_STEP_MAPPING = {
    "transcribing": "transcription",
    "analyzing": "analysis",
    "processing": "process",
    "generating_preview": "preview",
    "rendering": "render"
}


@v1_autoedit_workflow_api_bp.route('/v1/autoedit/workflow/<workflow_id>/retry', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "from_step": {
            "type": "string",
            "enum": ["transcription", "analysis", "process", "preview", "render"]
        }
    },
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=True)
def retry_workflow(job_id, data, **kwargs):
    """Retry a stuck workflow from its current step or a specified step.

    This endpoint:
    1. Resets the workflow status to allow re-processing
    2. Re-enqueues the Cloud Task for the step
    3. Preserves all existing data (video_url, transcript, etc.)

    Request body:
        {
            "from_step": "transcription"  // optional: restart from specific step
        }

    Returns:
        {
            "status": "success",
            "workflow_id": "...",
            "previous_status": "transcribing",
            "new_status": "created",
            "step_to_retry": "transcription",
            "message": "Workflow queued for retry"
        }
    """
    workflow_id = request.view_args.get('workflow_id')
    from_step = data.get('from_step')
    endpoint = f"/v1/autoedit/workflow/{workflow_id}/retry"

    logger.info(f"Retry requested for workflow {workflow_id}, from_step={from_step}")

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return {
                "error": "Workflow not found",
                "workflow_id": workflow_id
            }, endpoint, 404

        previous_status = workflow["status"]

        # Determine which step to retry
        if from_step:
            step_to_retry = from_step
        else:
            # Auto-detect from current status
            step_to_retry = RETRY_STEP_MAPPING.get(previous_status)
            if not step_to_retry:
                return {
                    "error": f"Cannot auto-detect retry step for status '{previous_status}'. "
                             f"Specify 'from_step' parameter.",
                    "workflow_id": workflow_id,
                    "current_status": previous_status,
                    "valid_stuck_states": list(RETRY_STEP_MAPPING.keys())
                }, endpoint, 400

        # Map step to new status and task type
        step_config = {
            "transcription": {"new_status": "created", "task_type": "transcribe"},
            "analysis": {"new_status": "transcribed", "task_type": "analyze"},
            "process": {"new_status": "xml_approved", "task_type": "process"},
            "preview": {"new_status": "processing", "task_type": "preview"},
            "render": {"new_status": "pending_review_2", "task_type": "render"}
        }

        config = step_config.get(step_to_retry)
        if not config:
            return {
                "error": f"Invalid step: {step_to_retry}",
                "valid_steps": list(step_config.keys())
            }, endpoint, 400

        new_status = config["new_status"]
        task_type = config["task_type"]

        # Reset workflow status
        manager.set_status(workflow_id, new_status)

        # Clear any previous error
        manager.update(workflow_id, {
            "error": None,
            "retry_count": workflow.get("retry_count", 0) + 1,
            "last_retry_at": __import__('datetime').datetime.utcnow().isoformat()
        })

        # Enqueue the task
        from services.v1.autoedit.task_queue import enqueue_task
        enqueue_result = enqueue_task(
            task_type=task_type,
            workflow_id=workflow_id,
            payload={"retry": True, "from_status": previous_status}
        )

        # Update status to "in progress" state
        in_progress_status = {
            "transcription": "transcribing",
            "analysis": "analyzing",
            "process": "processing",
            "preview": "generating_preview",
            "render": "rendering"
        }
        manager.set_status(workflow_id, in_progress_status[step_to_retry])

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "previous_status": previous_status,
            "new_status": in_progress_status[step_to_retry],
            "step_to_retry": step_to_retry,
            "task_enqueued": enqueue_result.get("success", False),
            "message": f"Workflow queued for retry from {step_to_retry}"
        }, endpoint, 200

    except Exception as e:
        logger.error(f"Error retrying workflow {workflow_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {"error": str(e), "workflow_id": workflow_id}, endpoint, 500


@v1_autoedit_workflow_api_bp.route('/v1/autoedit/workflow/<workflow_id>/fail', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "reason": {"type": "string", "minLength": 1, "maxLength": 500}
    },
    "required": ["reason"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=True)
def fail_workflow(job_id, data, **kwargs):
    """Manually mark a workflow as failed.

    Use this to:
    - Mark stuck workflows as failed so the project can proceed
    - Document the reason for failure
    - Allow the project stats to update correctly

    Request body:
        {
            "reason": "ElevenLabs timeout after 60 minutes"
        }

    Returns:
        {
            "status": "success",
            "workflow_id": "...",
            "previous_status": "transcribing",
            "new_status": "error",
            "message": "Workflow marked as failed"
        }
    """
    workflow_id = request.view_args.get('workflow_id')
    reason = data.get('reason', 'Manually marked as failed')
    endpoint = f"/v1/autoedit/workflow/{workflow_id}/fail"

    logger.info(f"Manual fail requested for workflow {workflow_id}: {reason}")

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return {
                "error": "Workflow not found",
                "workflow_id": workflow_id
            }, endpoint, 404

        previous_status = workflow["status"]

        # Don't allow failing already completed workflows
        if previous_status == "completed":
            return {
                "error": "Cannot fail a completed workflow",
                "workflow_id": workflow_id,
                "current_status": previous_status
            }, endpoint, 400

        # Already in error state
        if previous_status == "error":
            return {
                "status": "already_failed",
                "workflow_id": workflow_id,
                "previous_status": previous_status,
                "existing_error": workflow.get("error"),
                "message": "Workflow was already in error state"
            }, endpoint, 200

        # Mark as failed
        manager.set_status(workflow_id, "error", error=reason)

        # Record failure details
        manager.update(workflow_id, {
            "failed_at": __import__('datetime').datetime.utcnow().isoformat(),
            "failed_from_status": previous_status,
            "manual_fail": True
        })

        # Update project stats if this workflow belongs to a project
        project_id = workflow.get("project_id")
        if project_id:
            try:
                from services.v1.autoedit.project import refresh_project_stats
                refresh_project_stats(project_id)
                logger.info(f"Refreshed stats for project {project_id} after failing workflow {workflow_id}")
            except Exception as stats_error:
                logger.warning(f"Could not refresh project stats: {stats_error}")

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "previous_status": previous_status,
            "new_status": "error",
            "reason": reason,
            "message": "Workflow marked as failed"
        }, endpoint, 200

    except Exception as e:
        logger.error(f"Error failing workflow {workflow_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {"error": str(e), "workflow_id": workflow_id}, endpoint, 500
