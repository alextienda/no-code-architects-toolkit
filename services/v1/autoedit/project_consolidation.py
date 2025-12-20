# Copyright (c) 2025
#
# Project Consolidation Service for AutoEdit
#
# Orchestrates cross-video analysis after individual video processing:
# - Generate embeddings for all videos
# - Detect redundancies
# - Analyze global narrative structure
# - Generate recommendations

"""
Project Consolidation Service

After all videos in a project have been individually analyzed,
this service performs cross-video consolidation:

1. Generate/verify embeddings for all videos
2. Build progressive context summaries
3. Detect redundant content across videos
4. Analyze global narrative arc
5. Generate removal recommendations
6. Optionally apply recommendations

The consolidation can be automatic or require human review (HITL 3).
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from services.v1.autoedit.project import get_project, update_project
from services.v1.autoedit.workflow import get_workflow_manager
from services.v1.autoedit.twelvelabs_embeddings import (
    create_video_embeddings,
    save_embeddings_to_gcs,
    load_embeddings_from_gcs
)
from services.v1.autoedit.context_builder import (
    generate_video_summary,
    save_video_summary,
    load_all_video_summaries,
    get_accumulated_context,
    save_project_context
)
from services.v1.autoedit.redundancy_detector import (
    detect_cross_video_redundancies,
    calculate_project_redundancy_score,
    save_redundancy_analysis
)

logger = logging.getLogger(__name__)

# Configuration
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "autoedit-at")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "us-central1")


class ProjectConsolidator:
    """
    Orchestrates the consolidation process for multi-video projects.
    """

    def __init__(self, project_id: str):
        """
        Initialize consolidator for a project.

        Args:
            project_id: The project ID to consolidate
        """
        self.project_id = project_id
        self.project = get_project(project_id)
        self.wf_manager = get_workflow_manager()

        if not self.project:
            raise ValueError(f"Project not found: {project_id}")

        self.workflow_ids = self.project.get("workflow_ids", [])

    def run_full_consolidation(
        self,
        force_regenerate: bool = False,
        redundancy_threshold: float = 0.85,
        auto_apply: bool = False
    ) -> Dict[str, Any]:
        """
        Run the complete consolidation pipeline.

        Args:
            force_regenerate: Force regeneration of embeddings/summaries
            redundancy_threshold: Similarity threshold for redundancy detection
            auto_apply: Automatically apply recommendations (no HITL 3)

        Returns:
            Consolidation results with all analyses
        """
        logger.info(f"Starting consolidation for project {self.project_id}")

        results = {
            "project_id": self.project_id,
            "started_at": datetime.utcnow().isoformat(),
            "workflow_count": len(self.workflow_ids),
            "steps": {},
            "errors": []
        }

        try:
            # Step 1: Generate embeddings for all videos
            results["steps"]["embeddings"] = self._ensure_embeddings(force_regenerate)

            # Step 2: Generate video summaries
            results["steps"]["summaries"] = self._ensure_summaries(force_regenerate)

            # Step 3: Build project context
            results["steps"]["context"] = self._build_project_context()

            # Step 4: Detect redundancies
            results["steps"]["redundancies"] = self._detect_redundancies(redundancy_threshold)

            # Step 5: Analyze narrative structure
            results["steps"]["narrative"] = self._analyze_narrative()

            # Step 6: Generate final recommendations
            results["recommendations"] = self._compile_recommendations(results)

            # Step 7: Apply if auto mode
            if auto_apply and results["recommendations"]:
                results["steps"]["applied"] = self._apply_recommendations(
                    results["recommendations"]
                )

            results["status"] = "success"
            results["completed_at"] = datetime.utcnow().isoformat()

            # Update project state
            self._update_project_state("consolidated" if not auto_apply else "completed")

        except Exception as e:
            logger.error(f"Consolidation error: {e}")
            results["status"] = "error"
            results["error"] = str(e)
            self._update_project_state("consolidation_failed")

        return results

    def _ensure_embeddings(self, force: bool) -> Dict[str, Any]:
        """Ensure all videos have embeddings."""
        logger.info("Step 1: Ensuring embeddings for all videos")

        generated = []
        existing = []
        failed = []

        for wf_id in self.workflow_ids:
            # Check if embeddings exist
            if not force:
                emb = load_embeddings_from_gcs(wf_id)
                if emb:
                    existing.append(wf_id)
                    continue

            # Get workflow for video URL
            workflow = self.wf_manager.get(wf_id)
            if not workflow:
                failed.append({"workflow_id": wf_id, "error": "Workflow not found"})
                continue

            video_url = workflow.get("video_url")
            if not video_url:
                failed.append({"workflow_id": wf_id, "error": "No video URL"})
                continue

            # Generate embeddings
            try:
                duration = workflow.get("stats", {}).get("original_duration_ms", 0) / 1000
                result = create_video_embeddings(
                    video_url,
                    video_duration_sec=duration,
                    wait_for_result=True
                )

                if result.get("success"):
                    save_embeddings_to_gcs(wf_id, result)
                    generated.append(wf_id)
                else:
                    failed.append({
                        "workflow_id": wf_id,
                        "error": result.get("error", "Unknown error")
                    })

            except Exception as e:
                failed.append({"workflow_id": wf_id, "error": str(e)})

        return {
            "status": "success" if not failed else "partial",
            "generated": generated,
            "existing": existing,
            "failed": failed,
            "total_with_embeddings": len(generated) + len(existing)
        }

    def _ensure_summaries(self, force: bool) -> Dict[str, Any]:
        """Ensure all analyzed videos have summaries."""
        logger.info("Step 2: Ensuring video summaries")

        generated = []
        existing = []
        skipped = []

        for i, wf_id in enumerate(self.workflow_ids):
            # Get workflow
            workflow = self.wf_manager.get(wf_id)
            if not workflow:
                skipped.append({"workflow_id": wf_id, "reason": "not_found"})
                continue

            # Only generate summaries for analyzed videos
            status = workflow.get("status", "")
            if status not in ["pending_review_1", "xml_approved", "processing",
                              "pending_review_2", "completed"]:
                skipped.append({"workflow_id": wf_id, "reason": f"status_{status}"})
                continue

            # Check existing summary
            if not force:
                from services.v1.autoedit.context_builder import load_video_summary
                existing_summary = load_video_summary(self.project_id, wf_id)
                if existing_summary:
                    existing.append(wf_id)
                    continue

            # Generate summary
            transcript_internal = workflow.get("transcript_internal", [])
            transcript_text = " ".join(w.get("text", "") for w in transcript_internal)

            if not transcript_text:
                skipped.append({"workflow_id": wf_id, "reason": "no_transcript"})
                continue

            summary = generate_video_summary(
                workflow_id=wf_id,
                transcript_text=transcript_text,
                gemini_xml=workflow.get("gemini_xml"),
                sequence_index=i
            )

            save_video_summary(self.project_id, wf_id, summary)
            generated.append(wf_id)

        return {
            "status": "success",
            "generated": generated,
            "existing": existing,
            "skipped": skipped,
            "total_with_summaries": len(generated) + len(existing)
        }

    def _build_project_context(self) -> Dict[str, Any]:
        """Build and save accumulated project context."""
        logger.info("Step 3: Building project context")

        summaries = load_all_video_summaries(self.project_id, self.workflow_ids)
        context = get_accumulated_context(summaries)

        context["project_id"] = self.project_id
        context["summaries_count"] = len(summaries)

        save_project_context(self.project_id, context)

        return {
            "status": "success",
            "topics_covered": len(context.get("covered_topics", [])),
            "entities_found": len(context.get("entities_introduced", [])),
            "total_videos_analyzed": context.get("total_videos", 0)
        }

    def _detect_redundancies(self, threshold: float) -> Dict[str, Any]:
        """Detect cross-video redundancies."""
        logger.info(f"Step 4: Detecting redundancies (threshold={threshold})")

        analysis = detect_cross_video_redundancies(
            project_id=self.project_id,
            workflow_ids=self.workflow_ids,
            threshold=threshold
        )

        save_redundancy_analysis(self.project_id, analysis)

        score = calculate_project_redundancy_score(self.project_id, analysis)

        return {
            "status": analysis.get("status", "unknown"),
            "redundancies_found": analysis.get("redundancy_count", 0),
            "recommendations_generated": len(analysis.get("recommendations", [])),
            "redundancy_score": score.get("redundancy_score", 0),
            "interpretation": score.get("interpretation", ""),
            "removable_duration_sec": score.get("removable_duration_sec", 0)
        }

    def _analyze_narrative(self) -> Dict[str, Any]:
        """Analyze global narrative structure."""
        logger.info("Step 5: Analyzing narrative structure")

        summaries = load_all_video_summaries(self.project_id, self.workflow_ids)

        if len(summaries) < 2:
            return {
                "status": "skipped",
                "reason": "need_at_least_2_videos"
            }

        # Analyze narrative functions
        narrative_functions = {}
        for summary in summaries:
            func = summary.get("narrative_function", "unknown")
            narrative_functions[func] = narrative_functions.get(func, 0) + 1

        # Determine overall arc type
        if "introduction" in narrative_functions and "resolution" in narrative_functions:
            arc_type = "complete"
        elif "introduction" in narrative_functions:
            arc_type = "open_ended"
        elif "resolution" in narrative_functions:
            arc_type = "in_medias_res"
        else:
            arc_type = "episodic"

        # Detect tone consistency
        tones = [s.get("emotional_tone", "unknown") for s in summaries]
        unique_tones = set(tones)
        tone_consistency = 1.0 if len(unique_tones) == 1 else 1.0 / len(unique_tones)

        narrative = {
            "arc_type": arc_type,
            "narrative_functions": narrative_functions,
            "tone_consistency": round(tone_consistency, 2),
            "unique_tones": list(unique_tones),
            "video_sequence": [
                {
                    "index": s.get("sequence_index", i),
                    "function": s.get("narrative_function", "unknown"),
                    "tone": s.get("emotional_tone", "unknown"),
                    "summary": s.get("summary", "")[:100]
                }
                for i, s in enumerate(summaries)
            ]
        }

        # Save narrative analysis
        self._save_narrative_analysis(narrative)

        return {
            "status": "success",
            "arc_type": arc_type,
            "tone_consistency": tone_consistency,
            "functions_detected": list(narrative_functions.keys())
        }

    def _save_narrative_analysis(self, narrative: Dict[str, Any]) -> None:
        """Save narrative analysis to GCS."""
        from google.cloud import storage

        bucket_name = os.environ.get("GCP_BUCKET_NAME")
        if not bucket_name:
            return

        client = storage.Client()
        bucket = client.bucket(bucket_name)

        path = f"projects/{self.project_id}/context/narrative_arc.json"
        blob = bucket.blob(path)

        narrative["analyzed_at"] = datetime.utcnow().isoformat()

        blob.upload_from_string(
            json.dumps(narrative, ensure_ascii=False),
            content_type="application/json"
        )

    def _compile_recommendations(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Compile all recommendations from analyses."""
        recommendations = []

        # Get redundancy recommendations
        from services.v1.autoedit.redundancy_detector import load_redundancy_analysis
        redundancy_analysis = load_redundancy_analysis(self.project_id)

        if redundancy_analysis:
            for rec in redundancy_analysis.get("recommendations", []):
                recommendations.append({
                    **rec,
                    "source": "redundancy_detection"
                })

        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(key=lambda x: priority_order.get(x.get("priority", "low"), 3))

        return recommendations

    def _apply_recommendations(
        self,
        recommendations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Apply recommendations to workflow blocks."""
        logger.info(f"Applying {len(recommendations)} recommendations")

        applied = []
        failed = []

        for rec in recommendations:
            try:
                if rec.get("type") == "remove_redundant_segment":
                    wf_id = rec["action"]["workflow_id"]
                    segment = rec["action"]["segment"]

                    # Mark segment for removal in workflow
                    workflow = self.wf_manager.get(wf_id)
                    if workflow:
                        # Add to consolidation_cuts
                        cuts = workflow.get("consolidation_cuts", [])
                        cuts.append({
                            "start_sec": segment.get("start_sec"),
                            "end_sec": segment.get("end_sec"),
                            "reason": rec.get("reason", "redundancy"),
                            "recommendation_id": rec.get("id")
                        })

                        self.wf_manager.update(wf_id, {
                            "consolidation_cuts": cuts
                        })

                        applied.append(rec["id"])
                    else:
                        failed.append({
                            "id": rec["id"],
                            "error": "Workflow not found"
                        })

            except Exception as e:
                failed.append({
                    "id": rec.get("id"),
                    "error": str(e)
                })

        return {
            "status": "success" if not failed else "partial",
            "applied_count": len(applied),
            "failed_count": len(failed),
            "applied": applied,
            "failed": failed
        }

    def _update_project_state(self, state: str) -> None:
        """Update project consolidation state."""
        try:
            update_project(self.project_id, {
                "consolidation_state": state,
                "consolidation_updated_at": datetime.utcnow().isoformat()
            })
        except Exception as e:
            logger.error(f"Failed to update project state: {e}")


def consolidate_project(
    project_id: str,
    force_regenerate: bool = False,
    redundancy_threshold: float = 0.85,
    auto_apply: bool = False
) -> Dict[str, Any]:
    """
    Convenience function to run project consolidation.

    Args:
        project_id: The project ID
        force_regenerate: Force regeneration of embeddings/summaries
        redundancy_threshold: Similarity threshold
        auto_apply: Auto-apply recommendations

    Returns:
        Consolidation results
    """
    consolidator = ProjectConsolidator(project_id)
    return consolidator.run_full_consolidation(
        force_regenerate=force_regenerate,
        redundancy_threshold=redundancy_threshold,
        auto_apply=auto_apply
    )


def get_consolidation_status(project_id: str) -> Dict[str, Any]:
    """
    Get current consolidation status for a project.

    Args:
        project_id: The project ID

    Returns:
        Status information
    """
    project = get_project(project_id)
    if not project:
        return {"status": "error", "error": "Project not found"}

    # Load analyses if they exist
    from services.v1.autoedit.redundancy_detector import load_redundancy_analysis
    from services.v1.autoedit.context_builder import load_project_context

    redundancy = load_redundancy_analysis(project_id)
    context = load_project_context(project_id)

    return {
        "project_id": project_id,
        "consolidation_state": project.get("consolidation_state", "not_started"),
        "consolidation_updated_at": project.get("consolidation_updated_at"),
        "has_redundancy_analysis": redundancy is not None,
        "has_project_context": context is not None,
        "redundancy_count": redundancy.get("redundancy_count", 0) if redundancy else 0,
        "topics_covered": len(context.get("covered_topics", [])) if context else 0
    }
