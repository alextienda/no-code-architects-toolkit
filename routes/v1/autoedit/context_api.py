# Copyright (c) 2025
#
# Context API for AutoEdit Multi-Video Projects
#
# Provides REST endpoints for:
# - Project consolidation
# - Redundancy analysis
# - Narrative analysis
# - Cut recommendations

"""
Context API Endpoints

Handles cross-video context operations for multi-video projects:
- Consolidation: Analyze all videos together for redundancies
- Redundancy Detection: Find similar content across videos
- Narrative Analysis: Global storytelling structure
- Recommendations: Suggested cuts based on analysis
"""

from flask import Blueprint, request, jsonify
import logging

from services.authentication import authenticate
from app_utils import validate_payload, queue_task_wrapper

from services.v1.autoedit.project import get_project, update_project
from services.v1.autoedit.project_consolidation import (
    consolidate_project,
    get_consolidation_status,
    ProjectConsolidator
)
from services.v1.autoedit.redundancy_detector import (
    load_redundancy_analysis,
    calculate_project_redundancy_score
)
from services.v1.autoedit.context_builder import (
    load_project_context,
    load_all_video_summaries
)

logger = logging.getLogger(__name__)

v1_autoedit_context_bp = Blueprint('v1_autoedit_context', __name__)


# ============================================================================
# Schemas
# ============================================================================

consolidate_schema = {
    "type": "object",
    "properties": {
        "force_regenerate": {
            "type": "boolean",
            "description": "Force regeneration of embeddings and summaries"
        },
        "redundancy_threshold": {
            "type": "number",
            "minimum": 0.5,
            "maximum": 1.0,
            "description": "Similarity threshold for redundancy detection (default: 0.85)"
        },
        "auto_apply": {
            "type": "boolean",
            "description": "Automatically apply recommendations (skip HITL 3)"
        },
        "webhook_url": {
            "type": "string",
            "format": "uri",
            "description": "Webhook URL for async notification"
        }
    },
    "additionalProperties": False
}

apply_recommendations_schema = {
    "type": "object",
    "properties": {
        "recommendation_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "IDs of recommendations to apply (empty = apply all)"
        },
        "webhook_url": {
            "type": "string",
            "format": "uri"
        }
    },
    "additionalProperties": False
}

reorder_videos_schema = {
    "type": "object",
    "properties": {
        "workflow_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Workflow IDs in the new sequence order"
        }
    },
    "required": ["workflow_ids"],
    "additionalProperties": False
}


# ============================================================================
# Consolidation Endpoints
# ============================================================================

@v1_autoedit_context_bp.route('/v1/autoedit/project/<project_id>/consolidate', methods=['POST'])
@authenticate
@validate_payload(consolidate_schema)
@queue_task_wrapper(bypass_queue=False)
def consolidate_project_endpoint(job_id, data, project_id):
    """
    Start project consolidation process.

    Consolidation performs:
    1. Generate embeddings for all videos (if not already done)
    2. Generate video summaries
    3. Build project context
    4. Detect cross-video redundancies
    5. Analyze narrative structure
    6. Generate cut recommendations

    Args:
        project_id: The project ID

    Request Body:
        force_regenerate (bool): Force regeneration of embeddings/summaries
        redundancy_threshold (float): Similarity threshold (default: 0.85)
        auto_apply (bool): Auto-apply recommendations (default: false)
        webhook_url (str): Webhook for async notification

    Returns:
        Consolidation results or task acknowledgment
    """
    logger.info(f"Consolidation request for project {project_id}")

    # Verify project exists
    project = get_project(project_id)
    if not project:
        return {
            "success": False,
            "error": "Project not found"
        }, "/v1/autoedit/project/{id}/consolidate", 404

    # Check if project has videos
    workflow_ids = project.get("workflow_ids", [])
    if len(workflow_ids) < 2:
        return {
            "success": False,
            "error": "Project needs at least 2 videos for consolidation"
        }, "/v1/autoedit/project/{id}/consolidate", 400

    # Run consolidation
    try:
        results = consolidate_project(
            project_id=project_id,
            force_regenerate=data.get("force_regenerate", False),
            redundancy_threshold=data.get("redundancy_threshold", 0.85),
            auto_apply=data.get("auto_apply", False)
        )

        return {
            "success": True,
            "project_id": project_id,
            "consolidation": results
        }, "/v1/autoedit/project/{id}/consolidate", 200

    except Exception as e:
        logger.error(f"Consolidation failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }, "/v1/autoedit/project/{id}/consolidate", 500


@v1_autoedit_context_bp.route('/v1/autoedit/project/<project_id>/consolidation-status', methods=['GET'])
@authenticate
def get_consolidation_status_endpoint(project_id):
    """
    Get current consolidation status for a project.

    Returns:
        Status information including:
        - consolidation_state
        - has_redundancy_analysis
        - has_project_context
        - redundancy_count
        - topics_covered
    """
    try:
        status = get_consolidation_status(project_id)

        if status.get("status") == "error":
            return jsonify({
                "success": False,
                "error": status.get("error")
            }), 404

        return jsonify({
            "success": True,
            **status
        }), 200

    except Exception as e:
        logger.error(f"Error getting consolidation status: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# Redundancy Endpoints
# ============================================================================

@v1_autoedit_context_bp.route('/v1/autoedit/project/<project_id>/redundancies', methods=['GET'])
@authenticate
def get_redundancies_endpoint(project_id):
    """
    Get redundancy analysis for a project.

    Query Params:
        include_segments (bool): Include full segment details (default: false)
        min_severity (str): Filter by minimum severity (high, medium, low)

    Returns:
        Redundancy analysis with:
        - redundancy_count
        - redundancy_score
        - redundancies list
        - recommendations list
    """
    include_segments = request.args.get("include_segments", "false").lower() == "true"
    min_severity = request.args.get("min_severity")

    try:
        # Verify project exists
        project = get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": "Project not found"
            }), 404

        # Load redundancy analysis
        analysis = load_redundancy_analysis(project_id)

        if not analysis:
            return jsonify({
                "success": False,
                "error": "No redundancy analysis found. Run consolidation first."
            }), 404

        # Filter by severity if requested
        redundancies = analysis.get("redundancies", [])
        if min_severity:
            severity_order = {"high": 0, "medium": 1, "low": 2}
            min_order = severity_order.get(min_severity, 2)
            redundancies = [
                r for r in redundancies
                if severity_order.get(r.get("severity"), 3) <= min_order
            ]

        # Calculate score
        score = calculate_project_redundancy_score(project_id, analysis)

        # Prepare response
        response = {
            "success": True,
            "project_id": project_id,
            "redundancy_count": len(redundancies),
            "redundancy_score": score.get("redundancy_score", 0),
            "interpretation": score.get("interpretation", ""),
            "removable_duration_sec": score.get("removable_duration_sec", 0),
            "analyzed_at": analysis.get("analyzed_at"),
            "recommendations": analysis.get("recommendations", [])
        }

        if include_segments:
            response["redundancies"] = redundancies
        else:
            # Summary view
            response["redundancies_summary"] = [
                {
                    "id": r.get("id"),
                    "severity": r.get("severity"),
                    "similarity": r.get("similarity"),
                    "video_a_index": r.get("video_a", {}).get("sequence_index"),
                    "video_b_index": r.get("video_b", {}).get("sequence_index")
                }
                for r in redundancies
            ]

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error getting redundancies: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# Narrative Analysis Endpoints
# ============================================================================

@v1_autoedit_context_bp.route('/v1/autoedit/project/<project_id>/narrative', methods=['GET'])
@authenticate
def get_narrative_analysis_endpoint(project_id):
    """
    Get global narrative analysis for a project.

    Returns:
        Narrative analysis with:
        - arc_type (complete, open_ended, in_medias_res, episodic)
        - narrative_functions breakdown
        - tone_consistency score
        - video_sequence with function/tone per video
    """
    try:
        # Verify project exists
        project = get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": "Project not found"
            }), 404

        # Load narrative analysis from GCS
        from google.cloud import storage
        import os
        import json

        bucket_name = os.environ.get("GCP_BUCKET_NAME")
        if not bucket_name:
            return jsonify({
                "success": False,
                "error": "GCP_BUCKET_NAME not configured"
            }), 500

        client = storage.Client()
        bucket = client.bucket(bucket_name)

        path = f"projects/{project_id}/context/narrative_arc.json"
        blob = bucket.blob(path)

        if not blob.exists():
            return jsonify({
                "success": False,
                "error": "No narrative analysis found. Run consolidation first."
            }), 404

        content = blob.download_as_string()
        narrative = json.loads(content)

        return jsonify({
            "success": True,
            "project_id": project_id,
            **narrative
        }), 200

    except Exception as e:
        logger.error(f"Error getting narrative analysis: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# Recommendations Endpoints
# ============================================================================

@v1_autoedit_context_bp.route('/v1/autoedit/project/<project_id>/recommendations', methods=['GET'])
@authenticate
def get_recommendations_endpoint(project_id):
    """
    Get cut recommendations for a project.

    Query Params:
        priority (str): Filter by priority (high, medium, low)

    Returns:
        List of recommendations with:
        - id
        - type
        - priority
        - action (workflow_id, segment to remove)
        - reason
        - estimated_savings_sec
    """
    priority_filter = request.args.get("priority")

    try:
        # Verify project exists
        project = get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": "Project not found"
            }), 404

        # Load redundancy analysis
        analysis = load_redundancy_analysis(project_id)

        if not analysis:
            return jsonify({
                "success": False,
                "error": "No analysis found. Run consolidation first."
            }), 404

        recommendations = analysis.get("recommendations", [])

        # Filter by priority if requested
        if priority_filter:
            recommendations = [
                r for r in recommendations
                if r.get("priority") == priority_filter
            ]

        # Calculate total savings
        total_savings = sum(r.get("estimated_savings_sec", 0) for r in recommendations)

        return jsonify({
            "success": True,
            "project_id": project_id,
            "recommendation_count": len(recommendations),
            "total_savings_sec": round(total_savings, 1),
            "recommendations": recommendations
        }), 200

    except Exception as e:
        logger.error(f"Error getting recommendations: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@v1_autoedit_context_bp.route('/v1/autoedit/project/<project_id>/apply-recommendations', methods=['POST'])
@authenticate
@validate_payload(apply_recommendations_schema)
@queue_task_wrapper(bypass_queue=False)
def apply_recommendations_endpoint(job_id, data, project_id):
    """
    Apply cut recommendations to workflows.

    Request Body:
        recommendation_ids (list): Specific IDs to apply (empty = all)
        webhook_url (str): Webhook for async notification

    Returns:
        Applied count and any failures
    """
    logger.info(f"Applying recommendations for project {project_id}")

    try:
        # Verify project exists
        project = get_project(project_id)
        if not project:
            return {
                "success": False,
                "error": "Project not found"
            }, "/v1/autoedit/project/{id}/apply-recommendations", 404

        # Load redundancy analysis
        analysis = load_redundancy_analysis(project_id)
        if not analysis:
            return {
                "success": False,
                "error": "No analysis found. Run consolidation first."
            }, "/v1/autoedit/project/{id}/apply-recommendations", 404

        recommendations = analysis.get("recommendations", [])

        # Filter by IDs if specified
        rec_ids = data.get("recommendation_ids", [])
        if rec_ids:
            recommendations = [r for r in recommendations if r.get("id") in rec_ids]

        if not recommendations:
            return {
                "success": True,
                "applied_count": 0,
                "message": "No recommendations to apply"
            }, "/v1/autoedit/project/{id}/apply-recommendations", 200

        # Apply recommendations
        consolidator = ProjectConsolidator(project_id)
        result = consolidator._apply_recommendations(recommendations)

        return {
            "success": True,
            "project_id": project_id,
            **result
        }, "/v1/autoedit/project/{id}/apply-recommendations", 200

    except Exception as e:
        logger.error(f"Error applying recommendations: {e}")
        return {
            "success": False,
            "error": str(e)
        }, "/v1/autoedit/project/{id}/apply-recommendations", 500


# ============================================================================
# Video Sequence Endpoints
# ============================================================================

@v1_autoedit_context_bp.route('/v1/autoedit/project/<project_id>/videos/reorder', methods=['PUT'])
@authenticate
@validate_payload(reorder_videos_schema)
@queue_task_wrapper(bypass_queue=True)
def reorder_videos_endpoint(job_id, data, project_id):
    """
    Reorder videos in the project sequence.

    This affects:
    - The order in which context is passed between videos
    - Which video is considered "first mention" for redundancy

    Request Body:
        workflow_ids (list): Workflow IDs in new order

    Returns:
        Updated project with new sequence
    """
    logger.info(f"Reordering videos for project {project_id}")

    try:
        # Verify project exists
        project = get_project(project_id)
        if not project:
            return {
                "success": False,
                "error": "Project not found"
            }, "/v1/autoedit/project/{id}/videos/reorder", 404

        current_ids = set(project.get("workflow_ids", []))
        new_ids = data.get("workflow_ids", [])

        # Validate: same videos, different order
        if set(new_ids) != current_ids:
            return {
                "success": False,
                "error": "workflow_ids must contain exactly the same videos"
            }, "/v1/autoedit/project/{id}/videos/reorder", 400

        # Update project
        update_project(project_id, {"workflow_ids": new_ids})

        # Invalidate consolidation if it was done
        if project.get("consolidation_state") in ["consolidated", "completed"]:
            update_project(project_id, {
                "consolidation_state": "invalidated",
                "consolidation_invalidation_reason": "Video sequence reordered"
            })

        return {
            "success": True,
            "project_id": project_id,
            "workflow_ids": new_ids,
            "message": "Videos reordered successfully"
        }, "/v1/autoedit/project/{id}/videos/reorder", 200

    except Exception as e:
        logger.error(f"Error reordering videos: {e}")
        return {
            "success": False,
            "error": str(e)
        }, "/v1/autoedit/project/{id}/videos/reorder", 500


# ============================================================================
# Context Endpoints
# ============================================================================

@v1_autoedit_context_bp.route('/v1/autoedit/project/<project_id>/context', methods=['GET'])
@authenticate
def get_project_context_endpoint(project_id):
    """
    Get accumulated project context.

    Returns:
        Project context with:
        - covered_topics: All topics discussed across videos
        - entities_introduced: Named entities mentioned
        - narrative_functions: Distribution of narrative functions
        - total_videos: Number of videos with summaries
    """
    try:
        # Verify project exists
        project = get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": "Project not found"
            }), 404

        # Load project context
        context = load_project_context(project_id)

        if not context:
            return jsonify({
                "success": False,
                "error": "No context found. Run consolidation first."
            }), 404

        return jsonify({
            "success": True,
            "project_id": project_id,
            **context
        }), 200

    except Exception as e:
        logger.error(f"Error getting project context: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@v1_autoedit_context_bp.route('/v1/autoedit/project/<project_id>/summaries', methods=['GET'])
@authenticate
def get_video_summaries_endpoint(project_id):
    """
    Get all video summaries for a project.

    Returns:
        List of video summaries in sequence order
    """
    try:
        # Verify project exists
        project = get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": "Project not found"
            }), 404

        workflow_ids = project.get("workflow_ids", [])

        # Load all summaries
        summaries = load_all_video_summaries(project_id, workflow_ids)

        return jsonify({
            "success": True,
            "project_id": project_id,
            "summary_count": len(summaries),
            "summaries": summaries
        }), 200

    except Exception as e:
        logger.error(f"Error getting video summaries: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
