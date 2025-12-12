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
"""

from flask import Blueprint, jsonify, request
from app_utils import validate_payload, queue_task_wrapper
from services.authentication import authenticate
from services.v1.autoedit.workflow import (
    get_workflow_manager,
    WORKFLOW_STATES
)
import logging

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
                "skip_hitl_2": {"type": "boolean"}
            }
        },
        "id": {"type": "string"}
    },
    "required": ["video_url"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=True)
def create_workflow(job_id, data):
    """Create a new AutoEdit workflow.

    Request body:
        {
            "video_url": "https://...",
            "options": {
                "language": "es",
                "style": "dynamic",
                "skip_hitl_1": false,
                "skip_hitl_2": false
            }
        }

    Returns:
        {
            "workflow_id": "uuid",
            "status": "created",
            "message": "Workflow created successfully"
        }
    """
    video_url = data['video_url']
    options = data.get('options', {})

    logger.info(f"Creating workflow for video: {video_url[:50]}...")

    try:
        manager = get_workflow_manager()
        workflow_id = manager.create(video_url, options)

        return {
            "workflow_id": workflow_id,
            "status": "created",
            "status_message": WORKFLOW_STATES["created"],
            "message": "Workflow created successfully"
        }, "/v1/autoedit/workflow", 201

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
        "updated_xml": {"type": "string", "minLength": 1}
    },
    "required": ["updated_xml"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=True)
def submit_reviewed_xml(job_id, data):
    """Submit the user-reviewed XML after HITL 1 modifications.

    Request body:
        {
            "updated_xml": "<resultado>...(with user changes)...</resultado>"
        }

    Returns:
        {
            "workflow_id": "...",
            "status": "xml_approved",
            "message": "XML approved. Ready for processing."
        }
    """
    # Get workflow_id from URL
    workflow_id = request.view_args.get('workflow_id')
    _ = job_id  # Not used for this endpoint
    endpoint = f"/v1/autoedit/workflow/{workflow_id}/analysis"

    logger.info(f"Submitting reviewed XML for workflow: {workflow_id}")

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

        if success:
            return {
                "workflow_id": workflow_id,
                "status": "xml_approved",
                "message": "XML approved. Ready for processing to blocks."
            }, endpoint, 200
        else:
            return {
                "error": "Failed to save XML",
                "workflow_id": workflow_id
            }, endpoint, 500

    except Exception as e:
        logger.error(f"Error submitting XML for {workflow_id}: {e}")
        return {"error": str(e), "workflow_id": workflow_id}, endpoint, 500
