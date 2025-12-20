# Copyright (c) 2025 Stephen G. Pope
# Licensed under GPL-2.0

"""
Visual API for AutoEdit Phase 5

Endpoints for visual enhancement recommendations: B-Roll, graphics,
animations, maps, data visualizations, and other supporting elements.

Endpoints:
- POST /v1/autoedit/project/{id}/visual/analyze-needs
- GET  /v1/autoedit/project/{id}/visual/recommendations
- GET  /v1/autoedit/workflow/{id}/visual/recommendations
- PATCH /v1/autoedit/project/{id}/visual/recommendations/{rec_id}/status
"""

import logging
from flask import Blueprint, request, jsonify

from services.authentication import authenticate

logger = logging.getLogger(__name__)

v1_autoedit_visual_bp = Blueprint(
    'v1_autoedit_visual',
    __name__
)


# =============================================================================
# ANALYZE VISUAL NEEDS
# =============================================================================

@v1_autoedit_visual_bp.route(
    '/v1/autoedit/project/<project_id>/visual/analyze-needs',
    methods=['POST']
)
@authenticate
def analyze_visual_needs(project_id: str):
    """
    Trigger visual enhancement analysis for all videos in a project.

    Analyzes content to identify opportunities for:
    - B-Roll footage
    - Diagrams and illustrations
    - Data visualizations
    - Maps and geographic elements
    - Text overlays

    Request Body (optional):
    {
        "workflow_ids": ["wf_001"],   // Specific workflows (default: all)
        "types": ["broll", "diagram"], // Filter recommendation types
        "force_reanalyze": false
    }

    Returns:
    {
        "project_id": "...",
        "status": "completed",
        "total_recommendations": 15,
        "by_type": {"broll": 8, "diagram": 4, "data_visualization": 3},
        "high_priority_count": 5
    }
    """
    try:
        from services.v1.autoedit.project import get_project, update_project
        from services.v1.autoedit.workflow import get_workflow
        from services.v1.autoedit.visual_analyzer import get_visual_analyzer
        from config import PHASE5_AGENTS_ENABLED, CREATOR_GLOBAL_PROFILE

        # Check feature flag
        if not PHASE5_AGENTS_ENABLED:
            return jsonify({
                "error": "Phase 5 agents not enabled",
                "hint": "Set PHASE5_AGENTS_ENABLED=true"
            }), 400

        # Get project
        project = get_project(project_id)
        if not project:
            return jsonify({"error": "Project not found"}), 404

        # Parse options
        data = request.get_json() or {}
        target_workflows = data.get("workflow_ids")
        type_filter = data.get("types")
        force = data.get("force_reanalyze", False)

        # Check cache
        if not force:
            existing = project.get("visual_analysis")
            if existing and existing.get("status") == "completed":
                return jsonify({
                    "project_id": project_id,
                    "status": "cached",
                    "message": "Analysis exists. Use force_reanalyze=true to refresh.",
                    "total_recommendations": existing.get("total_recommendations", 0),
                    "analyzed_at": existing.get("analyzed_at")
                })

        # Check analyzer
        analyzer = get_visual_analyzer()
        if not analyzer.is_available():
            return jsonify({
                "error": "Visual analyzer not available",
                "hint": "Set GEMINI_API_KEY environment variable"
            }), 503

        # Get creator context
        project_context = project.get("project_context", {})
        if not project_context.get("creator_name"):
            project_context = {
                "creator_name": CREATOR_GLOBAL_PROFILE.get("name", "Creator"),
                "content_type": CREATOR_GLOBAL_PROFILE.get("typical_content", ["general"])[0] if CREATOR_GLOBAL_PROFILE.get("typical_content") else "general",
                "brand_style": CREATOR_GLOBAL_PROFILE.get("style", "professional")
            }

        # Determine target workflows
        workflow_ids = target_workflows or project.get("workflow_ids", [])

        # Analyze each workflow
        all_recommendations = []
        workflow_results = []

        for wf_id in workflow_ids:
            wf = get_workflow(wf_id)
            if not wf:
                continue

            workflow_data = {
                "workflow_id": wf_id,
                "blocks": wf.get("blocks", []),
                "analysis": wf.get("analysis", {})
            }

            result = analyzer.analyze_visual_needs(workflow_data, project_context)

            if result:
                recs = result.get("visual_recommendations", [])

                # Apply type filter if specified
                if type_filter:
                    recs = [r for r in recs if r.get("type") in type_filter]

                all_recommendations.extend(recs)
                workflow_results.append({
                    "workflow_id": wf_id,
                    "recommendation_count": len(recs),
                    "high_priority": sum(1 for r in recs if r.get("priority") == "high")
                })

        # Aggregate statistics
        type_counts = {}
        priority_counts = {"high": 0, "medium": 0, "low": 0}

        for rec in all_recommendations:
            rec_type = rec.get("type", "unknown")
            type_counts[rec_type] = type_counts.get(rec_type, 0) + 1
            priority = rec.get("priority", "medium")
            priority_counts[priority] = priority_counts.get(priority, 0) + 1

        # Save analysis
        visual_analysis = {
            "status": "completed",
            "analyzed_at": __import__('datetime').datetime.utcnow().isoformat(),
            "total_recommendations": len(all_recommendations),
            "by_type": type_counts,
            "by_priority": priority_counts,
            "recommendations": all_recommendations,
            "workflow_results": workflow_results
        }

        update_project(project_id, {"visual_analysis": visual_analysis})

        return jsonify({
            "project_id": project_id,
            "status": "completed",
            "total_recommendations": len(all_recommendations),
            "by_type": type_counts,
            "high_priority_count": priority_counts["high"],
            "workflows_analyzed": len(workflow_results),
            "analyzed_at": visual_analysis["analyzed_at"]
        })

    except Exception as e:
        logger.error(f"Visual analysis failed for {project_id}: {e}")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# GET PROJECT RECOMMENDATIONS
# =============================================================================

@v1_autoedit_visual_bp.route(
    '/v1/autoedit/project/<project_id>/visual/recommendations',
    methods=['GET']
)
@authenticate
def get_project_visual_recommendations(project_id: str):
    """
    Get all visual recommendations for a project.

    Query Parameters:
        type: Filter by type (broll, diagram, data_visualization, map_animation, etc.)
        priority: Filter by priority (high, medium, low)
        status: Filter by status (pending, accepted, rejected)
        limit: Max results (default: 50)
        offset: Pagination offset

    Returns:
    {
        "project_id": "...",
        "recommendations": [...],
        "total": 15,
        "filtered": 10
    }
    """
    try:
        from services.v1.autoedit.project import get_project

        project = get_project(project_id)
        if not project:
            return jsonify({"error": "Project not found"}), 404

        analysis = project.get("visual_analysis")
        if not analysis or analysis.get("status") != "completed":
            return jsonify({
                "project_id": project_id,
                "status": "not_analyzed",
                "message": "Run analyze-needs first",
                "recommendations": []
            })

        # Get all recommendations
        all_recs = analysis.get("recommendations", [])

        # Apply filters
        type_filter = request.args.get("type")
        priority_filter = request.args.get("priority")
        status_filter = request.args.get("status")

        filtered = all_recs
        if type_filter:
            filtered = [r for r in filtered if r.get("type") == type_filter]
        if priority_filter:
            filtered = [r for r in filtered if r.get("priority") == priority_filter]
        if status_filter:
            filtered = [r for r in filtered if r.get("status", "pending") == status_filter]

        # Pagination
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
        paginated = filtered[offset:offset + limit]

        return jsonify({
            "project_id": project_id,
            "recommendations": paginated,
            "total": len(all_recs),
            "filtered": len(filtered),
            "returned": len(paginated),
            "pagination": {
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < len(filtered)
            },
            "analyzed_at": analysis.get("analyzed_at")
        })

    except Exception as e:
        logger.error(f"Get visual recommendations failed for {project_id}: {e}")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# GET WORKFLOW RECOMMENDATIONS
# =============================================================================

@v1_autoedit_visual_bp.route(
    '/v1/autoedit/workflow/<workflow_id>/visual/recommendations',
    methods=['GET']
)
@authenticate
def get_workflow_visual_recommendations(workflow_id: str):
    """
    Get visual recommendations for a specific workflow/video.

    Query Parameters:
        type: Filter by type
        priority: Filter by priority
        include_ai_prompts: Include AI generation prompts (default: true)
        include_stock: Include stock search keywords (default: true)

    Returns:
    {
        "workflow_id": "...",
        "recommendations": [
            {
                "id": "vis_001",
                "segment_id": "seg_123",
                "type": "diagram",
                "priority": "high",
                "content": {...},
                "generation": {
                    "ai_prompt": "...",
                    "recommended_tool": "DALL-E 3"
                },
                "alternatives": {
                    "stock_keywords": ["..."]
                }
            }
        ],
        "gaps": [...]
    }
    """
    try:
        from services.v1.autoedit.workflow import get_workflow
        from services.v1.autoedit.visual_analyzer import get_visual_analyzer
        from config import CREATOR_GLOBAL_PROFILE

        wf = get_workflow(workflow_id)
        if not wf:
            return jsonify({"error": "Workflow not found"}), 404

        # Check for cached analysis
        cached = wf.get("visual_analysis")

        # Parse options
        type_filter = request.args.get("type")
        priority_filter = request.args.get("priority")
        include_ai = request.args.get("include_ai_prompts", "true").lower() == "true"
        include_stock = request.args.get("include_stock", "true").lower() == "true"

        # Use cached or generate fresh
        if cached and cached.get("recommendations"):
            recommendations = cached.get("recommendations", [])
            gaps = cached.get("segment_gaps", [])
        else:
            # Generate analysis
            analyzer = get_visual_analyzer()

            project_context = {
                "creator_name": CREATOR_GLOBAL_PROFILE.get("name", "Creator"),
                "content_type": "educational",
                "brand_style": CREATOR_GLOBAL_PROFILE.get("style", "professional")
            }

            workflow_data = {
                "workflow_id": workflow_id,
                "blocks": wf.get("blocks", []),
                "analysis": wf.get("analysis", {})
            }

            result = analyzer.analyze_visual_needs(workflow_data, project_context)

            if result:
                recommendations = result.get("visual_recommendations", [])
                gaps = result.get("segment_gaps", [])
            else:
                recommendations = []
                gaps = []

        # Apply filters
        if type_filter:
            recommendations = [r for r in recommendations if r.get("type") == type_filter]
        if priority_filter:
            recommendations = [r for r in recommendations if r.get("priority") == priority_filter]

        # Optionally strip AI prompts or stock keywords
        if not include_ai:
            for rec in recommendations:
                rec.pop("generation", None)
        if not include_stock:
            for rec in recommendations:
                if "alternatives" in rec:
                    rec["alternatives"].pop("stock_keywords", None)

        return jsonify({
            "workflow_id": workflow_id,
            "recommendations": recommendations,
            "gaps": gaps,
            "total": len(recommendations)
        })

    except Exception as e:
        logger.error(f"Get workflow visual recommendations failed for {workflow_id}: {e}")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# UPDATE RECOMMENDATION STATUS
# =============================================================================

@v1_autoedit_visual_bp.route(
    '/v1/autoedit/project/<project_id>/visual/recommendations/<rec_id>/status',
    methods=['PATCH']
)
@authenticate
def update_recommendation_status(project_id: str, rec_id: str):
    """
    Update the status of a visual recommendation (HITL review).

    Request Body:
    {
        "status": "accepted" | "rejected" | "pending",
        "notes": "Optional user notes",
        "assigned_to": "designer_name",  // Optional
        "custom_prompt": "Modified AI prompt"  // Optional override
    }

    Returns:
    {
        "project_id": "...",
        "recommendation_id": "...",
        "status": "accepted",
        "updated_at": "..."
    }
    """
    try:
        from services.v1.autoedit.project import get_project, update_project
        from datetime import datetime

        project = get_project(project_id)
        if not project:
            return jsonify({"error": "Project not found"}), 404

        analysis = project.get("visual_analysis")
        if not analysis:
            return jsonify({"error": "No visual analysis found"}), 404

        data = request.get_json()
        if not data or "status" not in data:
            return jsonify({"error": "status is required"}), 400

        new_status = data["status"]
        if new_status not in ["accepted", "rejected", "pending"]:
            return jsonify({"error": "status must be: accepted, rejected, or pending"}), 400

        # Find and update recommendation
        recommendations = analysis.get("recommendations", [])
        found = False

        for rec in recommendations:
            if rec.get("id") == rec_id:
                rec["status"] = new_status
                rec["updated_at"] = datetime.utcnow().isoformat()

                if data.get("notes"):
                    rec["notes"] = data["notes"]
                if data.get("assigned_to"):
                    rec["assigned_to"] = data["assigned_to"]
                if data.get("custom_prompt"):
                    if "generation" not in rec:
                        rec["generation"] = {}
                    rec["generation"]["custom_prompt"] = data["custom_prompt"]

                found = True
                break

        if not found:
            return jsonify({"error": f"Recommendation {rec_id} not found"}), 404

        # Save updated analysis
        update_project(project_id, {"visual_analysis": analysis})

        # Calculate review progress
        total = len(recommendations)
        accepted = sum(1 for r in recommendations if r.get("status") == "accepted")
        rejected = sum(1 for r in recommendations if r.get("status") == "rejected")
        pending = total - accepted - rejected

        return jsonify({
            "project_id": project_id,
            "recommendation_id": rec_id,
            "status": new_status,
            "updated_at": datetime.utcnow().isoformat(),
            "review_progress": {
                "total": total,
                "accepted": accepted,
                "rejected": rejected,
                "pending": pending
            }
        })

    except Exception as e:
        logger.error(f"Update recommendation status failed: {e}")
        return jsonify({"error": str(e)}), 500
