# Copyright (c) 2025 Stephen G. Pope
# Licensed under GPL-2.0

"""
Intelligence API for AutoEdit Phase 5

Endpoints for intelligent redundancy analysis using LLM.
Instead of simple "first occurrence wins", these endpoints provide
quality-based selection recommendations with detailed analysis.

Endpoints:
- POST /v1/autoedit/project/{id}/intelligence/analyze-redundancy-quality
- GET  /v1/autoedit/project/{id}/intelligence/redundancy-recommendations
- POST /v1/autoedit/project/{id}/intelligence/apply-smart-recommendations
"""

import logging
from flask import Blueprint, request, jsonify

from services.authentication import authenticate

logger = logging.getLogger(__name__)

v1_autoedit_intelligence_bp = Blueprint(
    'v1_autoedit_intelligence',
    __name__
)


# =============================================================================
# ANALYZE REDUNDANCY QUALITY
# =============================================================================

@v1_autoedit_intelligence_bp.route(
    '/v1/autoedit/project/<project_id>/intelligence/analyze-redundancy-quality',
    methods=['POST']
)
@authenticate
def analyze_redundancy_quality(project_id: str):
    """
    Trigger LLM analysis of redundant segments.

    Uses FAISS to find similar segments, then applies Gemini LLM
    to evaluate quality and recommend which version to keep.

    Request Body (optional):
    {
        "similarity_threshold": 0.85,  // Minimum similarity for redundancy
        "max_groups": 20,              // Max redundancy groups to analyze
        "force_reanalyze": false       // Reanalyze even if cached
    }

    Returns:
    {
        "project_id": "...",
        "status": "analyzing" | "completed",
        "groups_found": 5,
        "task_id": "..." (if async)
    }
    """
    try:
        from services.v1.autoedit.project import get_project, update_project
        from services.v1.autoedit.intelligence_analyzer import get_intelligence_analyzer
        from services.v1.autoedit.task_queue import enqueue_task
        from config import PHASE5_AGENTS_ENABLED

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
        threshold = data.get("similarity_threshold", 0.85)
        max_groups = data.get("max_groups", 20)
        force = data.get("force_reanalyze", False)

        # Check for cached analysis
        if not force:
            existing = project.get("intelligence_analysis")
            if existing and existing.get("status") == "completed":
                return jsonify({
                    "project_id": project_id,
                    "status": "cached",
                    "message": "Analysis already exists. Use force_reanalyze=true to refresh.",
                    "analyzed_at": existing.get("analyzed_at"),
                    "groups_analyzed": existing.get("groups_analyzed", 0)
                })

        # Check if analyzer is available
        analyzer = get_intelligence_analyzer()
        if not analyzer.is_available():
            return jsonify({
                "error": "Intelligence analyzer not available",
                "hint": "Set GEMINI_API_KEY environment variable"
            }), 503

        # For small projects, analyze synchronously
        workflow_count = len(project.get("workflow_ids", []))
        if workflow_count <= 3:
            # Synchronous analysis
            result = analyzer.find_and_analyze_redundancies(
                project_id,
                similarity_threshold=threshold,
                max_groups=max_groups
            )

            # Save to project
            update_project(project_id, {
                "intelligence_analysis": {
                    "status": "completed",
                    **result
                }
            })

            return jsonify({
                "project_id": project_id,
                "status": "completed",
                "groups_analyzed": len(result.get("groups", [])),
                "total_pairs": result.get("total_pairs", 0),
                "analyzed_at": result.get("analyzed_at")
            })

        else:
            # Async via Cloud Tasks
            task_result = enqueue_task(
                task_type="analyze_redundancy_quality",
                workflow_id=f"project_{project_id}",
                payload={
                    "project_id": project_id,
                    "threshold": threshold,
                    "max_groups": max_groups
                }
            )

            # Update project state
            update_project(project_id, {
                "intelligence_analysis": {
                    "status": "analyzing",
                    "task_name": task_result.get("task_name")
                }
            })

            return jsonify({
                "project_id": project_id,
                "status": "analyzing",
                "message": "Analysis started asynchronously",
                "task_name": task_result.get("task_name")
            }), 202

    except Exception as e:
        logger.error(f"Redundancy analysis failed for {project_id}: {e}")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# GET REDUNDANCY RECOMMENDATIONS
# =============================================================================

@v1_autoedit_intelligence_bp.route(
    '/v1/autoedit/project/<project_id>/intelligence/redundancy-recommendations',
    methods=['GET']
)
@authenticate
def get_redundancy_recommendations(project_id: str):
    """
    Get intelligent redundancy recommendations for a project.

    Returns LLM-analyzed recommendations for which segments to keep
    when redundancies are detected.

    Query Parameters:
        min_confidence: Minimum confidence score (default: 0.5)
        include_analysis: Include detailed scoring (default: false)

    Returns:
    {
        "project_id": "...",
        "status": "completed" | "analyzing" | "not_analyzed",
        "recommendations": [
            {
                "group_id": "group_0",
                "keep_segment_id": "seg_123",
                "remove_segment_ids": ["seg_456"],
                "confidence": 0.85,
                "primary_reason": "Better delivery quality"
            }
        ],
        "summary": {
            "total_groups": 5,
            "high_confidence": 3,
            "segments_to_remove": 7
        }
    }
    """
    try:
        from services.v1.autoedit.project import get_project

        project = get_project(project_id)
        if not project:
            return jsonify({"error": "Project not found"}), 404

        # Get analysis
        analysis = project.get("intelligence_analysis")
        if not analysis:
            return jsonify({
                "project_id": project_id,
                "status": "not_analyzed",
                "message": "Run analyze-redundancy-quality first",
                "recommendations": []
            })

        if analysis.get("status") == "analyzing":
            return jsonify({
                "project_id": project_id,
                "status": "analyzing",
                "message": "Analysis in progress",
                "recommendations": []
            })

        # Parse options
        min_confidence = float(request.args.get("min_confidence", 0.5))
        include_analysis = request.args.get("include_analysis", "false").lower() == "true"

        # Extract recommendations
        groups = analysis.get("groups", [])
        recommendations = []
        segments_to_remove = 0

        for group in groups:
            rec = group.get("analysis", {}).get("recommendation", {})
            confidence = rec.get("confidence", 0)

            if confidence < min_confidence:
                continue

            item = {
                "group_id": group.get("group_id"),
                "keep_segment_id": rec.get("keep_segment_id"),
                "remove_segment_ids": rec.get("remove_segment_ids", []),
                "confidence": confidence,
                "primary_reason": rec.get("primary_reason", "")
            }

            if include_analysis:
                item["detailed_analysis"] = rec.get("detailed_analysis")

            recommendations.append(item)
            segments_to_remove += len(rec.get("remove_segment_ids", []))

        # Summary
        high_confidence = sum(1 for r in recommendations if r["confidence"] >= 0.8)

        return jsonify({
            "project_id": project_id,
            "status": "completed",
            "recommendations": recommendations,
            "summary": {
                "total_groups": len(groups),
                "filtered_groups": len(recommendations),
                "high_confidence": high_confidence,
                "segments_to_remove": segments_to_remove
            },
            "analyzed_at": analysis.get("analyzed_at")
        })

    except Exception as e:
        logger.error(f"Get recommendations failed for {project_id}: {e}")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# APPLY SMART RECOMMENDATIONS
# =============================================================================

@v1_autoedit_intelligence_bp.route(
    '/v1/autoedit/project/<project_id>/intelligence/apply-smart-recommendations',
    methods=['POST']
)
@authenticate
def apply_smart_recommendations(project_id: str):
    """
    Apply intelligent redundancy recommendations.

    Marks recommended segments for removal based on LLM analysis.
    This is a HITL point - user reviews and approves before applying.

    Request Body:
    {
        "group_ids": ["group_0", "group_1"],  // Optional: specific groups
        "min_confidence": 0.7,                 // Only apply high-confidence
        "dry_run": false                       // Preview changes without applying
    }

    Returns:
    {
        "project_id": "...",
        "applied": true | false,
        "changes": [
            {
                "workflow_id": "wf_123",
                "segments_removed": ["seg_456"],
                "reason": "Lower delivery quality"
            }
        ],
        "summary": {
            "segments_marked_remove": 5,
            "groups_applied": 3
        }
    }
    """
    try:
        from services.v1.autoedit.project import get_project, update_project
        from services.v1.autoedit.workflow import get_workflow, save_workflow

        project = get_project(project_id)
        if not project:
            return jsonify({"error": "Project not found"}), 404

        # Get analysis
        analysis = project.get("intelligence_analysis")
        if not analysis or analysis.get("status") != "completed":
            return jsonify({
                "error": "No completed analysis available",
                "hint": "Run analyze-redundancy-quality first"
            }), 400

        # Parse options
        data = request.get_json() or {}
        target_groups = data.get("group_ids")  # None = all groups
        min_confidence = data.get("min_confidence", 0.7)
        dry_run = data.get("dry_run", False)

        # Filter recommendations
        groups = analysis.get("groups", [])
        changes = []
        segments_removed = 0

        for group in groups:
            group_id = group.get("group_id")
            rec = group.get("analysis", {}).get("recommendation", {})

            # Filter by group_ids if specified
            if target_groups and group_id not in target_groups:
                continue

            # Filter by confidence
            if rec.get("confidence", 0) < min_confidence:
                continue

            remove_ids = rec.get("remove_segment_ids", [])
            if not remove_ids:
                continue

            # Group changes by workflow
            for segment in group.get("segments", []):
                seg_id = segment.get("segment_id")
                if seg_id not in remove_ids:
                    continue

                # Extract workflow_id from segment_id pattern
                # Assuming format: wf_xxx_timestamp or similar
                wf_id = segment.get("workflow_id")
                if not wf_id and "_" in seg_id:
                    parts = seg_id.split("_")
                    wf_id = f"{parts[0]}_{parts[1]}" if len(parts) >= 2 else None

                if wf_id and not dry_run:
                    # Load workflow and mark segment as cut
                    workflow = get_workflow(wf_id)
                    if workflow:
                        blocks = workflow.get("blocks", [])
                        for block in blocks:
                            if block.get("id") == seg_id:
                                block["action"] = "cut"
                                block["cut_reason"] = "intelligent_redundancy"
                                block["cut_analysis"] = {
                                    "group_id": group_id,
                                    "confidence": rec.get("confidence"),
                                    "reason": rec.get("primary_reason")
                                }
                        save_workflow(wf_id, workflow)

                changes.append({
                    "workflow_id": wf_id,
                    "segment_id": seg_id,
                    "reason": rec.get("primary_reason", "Intelligent selection")
                })
                segments_removed += 1

        # Update project state
        if not dry_run and changes:
            update_project(project_id, {
                "intelligence_applied": {
                    "applied_at": __import__('datetime').datetime.utcnow().isoformat(),
                    "groups_applied": len(set(c.get("group_id") for c in changes if c.get("group_id"))),
                    "segments_removed": segments_removed
                }
            })

        return jsonify({
            "project_id": project_id,
            "applied": not dry_run,
            "dry_run": dry_run,
            "changes": changes,
            "summary": {
                "segments_marked_remove": segments_removed,
                "workflows_affected": len(set(c.get("workflow_id") for c in changes))
            }
        })

    except Exception as e:
        logger.error(f"Apply recommendations failed for {project_id}: {e}")
        return jsonify({"error": str(e)}), 500
