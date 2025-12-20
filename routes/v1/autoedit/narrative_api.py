# Copyright (c) 2025 Stephen G. Pope
# Licensed under GPL-2.0

"""
Narrative API for AutoEdit Phase 5

Endpoints for narrative structure analysis, pacing, emotional arcs,
and video reordering suggestions.

Endpoints:
- POST /v1/autoedit/project/{id}/narrative/analyze-structure
- GET  /v1/autoedit/project/{id}/narrative/structure
- GET  /v1/autoedit/project/{id}/narrative/reorder-suggestions
- POST /v1/autoedit/project/{id}/narrative/apply-reorder
"""

import logging
from flask import Blueprint, request, jsonify

from services.authentication import authenticate

logger = logging.getLogger(__name__)

v1_autoedit_narrative_bp = Blueprint(
    'v1_autoedit_narrative',
    __name__
)


# =============================================================================
# ANALYZE NARRATIVE STRUCTURE
# =============================================================================

@v1_autoedit_narrative_bp.route(
    '/v1/autoedit/project/<project_id>/narrative/analyze-structure',
    methods=['POST']
)
@authenticate
def analyze_narrative_structure(project_id: str):
    """
    Trigger comprehensive narrative analysis for a project.

    Analyzes:
    - Narrative structure (Three-Act, Hero's Journey, etc.)
    - Pacing and tension curves
    - Emotional arcs
    - Narrative gaps and issues

    Request Body (optional):
    {
        "include_pacing": true,
        "include_emotional": true,
        "include_gaps": true,
        "force_reanalyze": false
    }

    Returns:
    {
        "project_id": "...",
        "status": "completed" | "analyzing",
        "detected_structure": "three_act",
        "confidence": 0.85
    }
    """
    try:
        from services.v1.autoedit.project import get_project, update_project
        from services.v1.autoedit.workflow import get_workflow
        from services.v1.autoedit.narrative_analyzer import get_narrative_analyzer
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
        include_pacing = data.get("include_pacing", True)
        include_emotional = data.get("include_emotional", True)
        include_gaps = data.get("include_gaps", True)
        force = data.get("force_reanalyze", False)

        # Check cache
        if not force:
            existing = project.get("narrative_analysis")
            if existing and existing.get("status") == "completed":
                return jsonify({
                    "project_id": project_id,
                    "status": "cached",
                    "message": "Analysis exists. Use force_reanalyze=true to refresh.",
                    "detected_structure": existing.get("structure_analysis", {}).get("detected_structure", {}).get("type"),
                    "analyzed_at": existing.get("analyzed_at")
                })

        # Check analyzer
        analyzer = get_narrative_analyzer()
        if not analyzer.is_available():
            return jsonify({
                "error": "Narrative analyzer not available",
                "hint": "Set GEMINI_API_KEY environment variable"
            }), 503

        # Build project data for analysis
        workflow_ids = project.get("workflow_ids", [])
        videos = []

        for wf_id in workflow_ids:
            wf = get_workflow(wf_id)
            if wf:
                videos.append({
                    "workflow_id": wf_id,
                    "sequence_index": wf.get("sequence_index", 0),
                    "title": wf.get("title", wf_id),
                    "duration_ms": wf.get("stats", {}).get("original_duration_ms", 0),
                    "summary": wf.get("summary", ""),
                    "topics": wf.get("analysis", {}).get("main_topics", []),
                    "emotional_tone": wf.get("analysis", {}).get("emotional_tone", "neutral"),
                    "key_points": wf.get("analysis", {}).get("key_points", []),
                    "blocks": wf.get("blocks", [])[:20]  # Limit for context
                })

        # Get creator context from project or global
        creator_context = project.get("project_context", {})
        if not creator_context.get("name"):
            creator_context = {
                "name": CREATOR_GLOBAL_PROFILE.get("name", "Creator"),
                "style": CREATOR_GLOBAL_PROFILE.get("style", ""),
                "typical_content": CREATOR_GLOBAL_PROFILE.get("typical_content", [])
            }

        project_data = {
            "project_id": project_id,
            "videos": videos,
            "creator_context": creator_context
        }

        # Run analysis
        result = analyzer.analyze_structure(project_data)

        # Add optional analyses
        full_result = {
            "status": "completed",
            **result
        }

        if include_pacing and videos:
            pacing_results = []
            for video in videos[:5]:  # Limit for performance
                pacing = analyzer.analyze_pacing(video)
                if pacing:
                    pacing_results.append(pacing)
            full_result["pacing_analysis"] = pacing_results

        if include_emotional:
            emotional = analyzer.analyze_emotional_arc(project_data)
            if emotional:
                full_result["emotional_arc"] = emotional

        if include_gaps:
            gaps = analyzer.detect_narrative_gaps(project_data)
            if gaps:
                full_result["narrative_gaps"] = gaps

        # Save to project
        update_project(project_id, {"narrative_analysis": full_result})

        return jsonify({
            "project_id": project_id,
            "status": "completed",
            "detected_structure": result.get("structure_analysis", {}).get("detected_structure", {}).get("type"),
            "confidence": result.get("structure_analysis", {}).get("detected_structure", {}).get("confidence"),
            "video_count": len(videos),
            "analyzed_at": result.get("analyzed_at")
        })

    except Exception as e:
        logger.error(f"Narrative analysis failed for {project_id}: {e}")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# GET NARRATIVE STRUCTURE
# =============================================================================

@v1_autoedit_narrative_bp.route(
    '/v1/autoedit/project/<project_id>/narrative/structure',
    methods=['GET']
)
@authenticate
def get_narrative_structure(project_id: str):
    """
    Get the narrative structure analysis for a project.

    Query Parameters:
        section: "structure" | "pacing" | "emotional" | "gaps" | "all" (default: all)

    Returns:
    {
        "project_id": "...",
        "structure_analysis": {
            "detected_structure": {
                "type": "three_act",
                "confidence": 0.85,
                "elements_found": {...}
            }
        },
        "pacing_analysis": [...],
        "emotional_arc": {...},
        "narrative_gaps": [...]
    }
    """
    try:
        from services.v1.autoedit.project import get_project

        project = get_project(project_id)
        if not project:
            return jsonify({"error": "Project not found"}), 404

        analysis = project.get("narrative_analysis")
        if not analysis:
            return jsonify({
                "project_id": project_id,
                "status": "not_analyzed",
                "message": "Run analyze-structure first"
            })

        if analysis.get("status") != "completed":
            return jsonify({
                "project_id": project_id,
                "status": analysis.get("status", "unknown"),
                "message": "Analysis not complete"
            })

        # Filter by section
        section = request.args.get("section", "all")

        if section == "all":
            return jsonify({
                "project_id": project_id,
                "status": "completed",
                **analysis
            })
        elif section == "structure":
            return jsonify({
                "project_id": project_id,
                "structure_analysis": analysis.get("structure_analysis")
            })
        elif section == "pacing":
            return jsonify({
                "project_id": project_id,
                "pacing_analysis": analysis.get("pacing_analysis")
            })
        elif section == "emotional":
            return jsonify({
                "project_id": project_id,
                "emotional_arc": analysis.get("emotional_arc")
            })
        elif section == "gaps":
            return jsonify({
                "project_id": project_id,
                "narrative_gaps": analysis.get("narrative_gaps")
            })
        else:
            return jsonify({"error": f"Unknown section: {section}"}), 400

    except Exception as e:
        logger.error(f"Get structure failed for {project_id}: {e}")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# GET REORDER SUGGESTIONS
# =============================================================================

@v1_autoedit_narrative_bp.route(
    '/v1/autoedit/project/<project_id>/narrative/reorder-suggestions',
    methods=['GET']
)
@authenticate
def get_reorder_suggestions(project_id: str):
    """
    Get video reordering suggestions for optimal narrative flow.

    Query Parameters:
        min_confidence: Minimum confidence for suggestions (default: 0.6)

    Returns:
    {
        "project_id": "...",
        "current_order": ["wf_001", "wf_002", "wf_003"],
        "suggestions": [
            {
                "proposed_order": ["wf_001", "wf_003", "wf_002"],
                "confidence": 0.8,
                "rationale": "Video 3 introduces concepts needed in Video 2",
                "impact": {
                    "narrative_flow": "improved",
                    "learning_curve": "smoother"
                }
            }
        ]
    }
    """
    try:
        from services.v1.autoedit.project import get_project
        from services.v1.autoedit.narrative_analyzer import get_narrative_analyzer

        project = get_project(project_id)
        if not project:
            return jsonify({"error": "Project not found"}), 404

        workflow_ids = project.get("workflow_ids", [])
        if len(workflow_ids) < 2:
            return jsonify({
                "project_id": project_id,
                "message": "Single video project, no reordering needed",
                "current_order": workflow_ids,
                "suggestions": []
            })

        # Check for cached analysis
        analysis = project.get("narrative_analysis")
        if analysis and "reorder_suggestions" in analysis:
            suggestions = analysis.get("reorder_suggestions", [])
        else:
            # Run reorder analysis
            from services.v1.autoedit.workflow import get_workflow
            from config import CREATOR_GLOBAL_PROFILE

            videos = []
            for wf_id in workflow_ids:
                wf = get_workflow(wf_id)
                if wf:
                    videos.append({
                        "workflow_id": wf_id,
                        "sequence_index": wf.get("sequence_index", 0),
                        "title": wf.get("title", wf_id),
                        "summary": wf.get("summary", ""),
                        "topics": wf.get("analysis", {}).get("main_topics", []),
                        "key_points": wf.get("analysis", {}).get("key_points", [])
                    })

            project_data = {
                "project_id": project_id,
                "videos": videos,
                "creator_context": project.get("project_context", {
                    "name": CREATOR_GLOBAL_PROFILE.get("name"),
                    "style": CREATOR_GLOBAL_PROFILE.get("style")
                })
            }

            analyzer = get_narrative_analyzer()
            if not analyzer.is_available():
                return jsonify({
                    "error": "Analyzer not available",
                    "current_order": workflow_ids,
                    "suggestions": []
                }), 503

            result = analyzer.suggest_reordering(project_data)
            suggestions = result.get("suggestions", [])

        # Filter by confidence
        min_confidence = float(request.args.get("min_confidence", 0.6))
        filtered = [s for s in suggestions if s.get("confidence", 0) >= min_confidence]

        return jsonify({
            "project_id": project_id,
            "current_order": workflow_ids,
            "video_count": len(workflow_ids),
            "suggestions": filtered,
            "total_suggestions": len(suggestions),
            "filtered_by_confidence": min_confidence
        })

    except Exception as e:
        logger.error(f"Get reorder suggestions failed for {project_id}: {e}")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# APPLY REORDER
# =============================================================================

@v1_autoedit_narrative_bp.route(
    '/v1/autoedit/project/<project_id>/narrative/apply-reorder',
    methods=['POST']
)
@authenticate
def apply_reorder(project_id: str):
    """
    Apply a video reordering to the project.

    This is a HITL point - user reviews suggestions and chooses order.

    Request Body:
    {
        "new_order": ["wf_001", "wf_003", "wf_002"],  // Required
        "suggestion_index": 0,                         // Optional: which suggestion was used
        "reason": "user_choice" | "suggestion_0"      // For tracking
    }

    Returns:
    {
        "project_id": "...",
        "applied": true,
        "previous_order": ["wf_001", "wf_002", "wf_003"],
        "new_order": ["wf_001", "wf_003", "wf_002"],
        "changes": [
            {"workflow_id": "wf_003", "from_index": 2, "to_index": 1}
        ]
    }
    """
    try:
        from services.v1.autoedit.project import get_project, update_project
        from services.v1.autoedit.workflow import get_workflow, save_workflow
        from datetime import datetime

        project = get_project(project_id)
        if not project:
            return jsonify({"error": "Project not found"}), 404

        data = request.get_json()
        if not data or "new_order" not in data:
            return jsonify({"error": "new_order is required"}), 400

        new_order = data["new_order"]
        current_order = project.get("workflow_ids", [])

        # Validate new_order
        if set(new_order) != set(current_order):
            return jsonify({
                "error": "new_order must contain exactly the same workflow IDs",
                "expected": current_order,
                "received": new_order
            }), 400

        if new_order == current_order:
            return jsonify({
                "project_id": project_id,
                "applied": False,
                "message": "Order unchanged"
            })

        # Calculate changes
        changes = []
        for new_idx, wf_id in enumerate(new_order):
            old_idx = current_order.index(wf_id)
            if old_idx != new_idx:
                changes.append({
                    "workflow_id": wf_id,
                    "from_index": old_idx,
                    "to_index": new_idx
                })

                # Update workflow sequence_index
                wf = get_workflow(wf_id)
                if wf:
                    wf["sequence_index"] = new_idx
                    save_workflow(wf_id, wf)

        # Update project
        update_project(project_id, {
            "workflow_ids": new_order,
            "reorder_history": [
                *(project.get("reorder_history", [])),
                {
                    "applied_at": datetime.utcnow().isoformat(),
                    "previous_order": current_order,
                    "new_order": new_order,
                    "reason": data.get("reason", "manual"),
                    "suggestion_index": data.get("suggestion_index")
                }
            ]
        })

        return jsonify({
            "project_id": project_id,
            "applied": True,
            "previous_order": current_order,
            "new_order": new_order,
            "changes": changes
        })

    except Exception as e:
        logger.error(f"Apply reorder failed for {project_id}: {e}")
        return jsonify({"error": str(e)}), 500
