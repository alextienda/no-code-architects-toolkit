# Copyright (c) 2025
#
# Redundancy Detector for AutoEdit Multi-Video Projects
#
# Detects similar/redundant content between videos in a project
# using TwelveLabs video embeddings and semantic analysis.

"""
Redundancy Detection Service

Uses TwelveLabs Marengo 3.0 embeddings to detect:
- Visually similar segments across videos
- Semantically redundant content
- Repeated explanations or topics

Generates recommendations for content removal to reduce redundancy.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from services.v1.autoedit.twelvelabs_embeddings import (
    load_embeddings_from_gcs,
    compare_video_embeddings,
    cosine_similarity,
    calculate_video_similarity
)

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_SIMILARITY_THRESHOLD = 0.85  # Segments with similarity >= this are redundant
HIGH_SIMILARITY_THRESHOLD = 0.95     # Require human review
MIN_SEGMENT_DURATION_SEC = 2.0       # Ignore very short segments


def detect_cross_video_redundancies(
    project_id: str,
    workflow_ids: List[str],
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    bucket_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Detect redundant content across all videos in a project.

    Args:
        project_id: The project ID
        workflow_ids: List of workflow IDs in sequence order
        threshold: Minimum similarity to consider as redundancy
        bucket_name: GCS bucket for embeddings

    Returns:
        Redundancy analysis with matches and recommendations
    """
    logger.info(f"Detecting redundancies in project {project_id} with {len(workflow_ids)} videos")

    # Load embeddings for all videos
    embeddings_by_workflow = {}
    missing_embeddings = []

    for wf_id in workflow_ids:
        embeddings = load_embeddings_from_gcs(wf_id, bucket_name)
        if embeddings:
            embeddings_by_workflow[wf_id] = embeddings
        else:
            missing_embeddings.append(wf_id)

    if missing_embeddings:
        logger.warning(f"Missing embeddings for workflows: {missing_embeddings}")

    if len(embeddings_by_workflow) < 2:
        return {
            "project_id": project_id,
            "status": "insufficient_data",
            "message": "Need at least 2 videos with embeddings",
            "redundancies": [],
            "recommendations": []
        }

    # Compare all pairs
    all_redundancies = []
    workflow_list = list(embeddings_by_workflow.keys())

    for i, wf_a in enumerate(workflow_list):
        for wf_b in workflow_list[i + 1:]:
            matches = compare_video_embeddings(
                embeddings_by_workflow[wf_a],
                embeddings_by_workflow[wf_b],
                threshold=threshold
            )

            for match in matches:
                # Calculate which video comes first in sequence
                seq_a = workflow_ids.index(wf_a) if wf_a in workflow_ids else 0
                seq_b = workflow_ids.index(wf_b) if wf_b in workflow_ids else 0

                redundancy = {
                    "id": f"red_{wf_a[:8]}_{wf_b[:8]}_{match['segment_a']['index']}",
                    "video_a": {
                        "workflow_id": wf_a,
                        "sequence_index": seq_a,
                        "segment": match["segment_a"]
                    },
                    "video_b": {
                        "workflow_id": wf_b,
                        "sequence_index": seq_b,
                        "segment": match["segment_b"]
                    },
                    "similarity": match["similarity"],
                    "severity": _classify_severity(match["similarity"]),
                    "detected_at": datetime.utcnow().isoformat()
                }

                all_redundancies.append(redundancy)

    # Sort by similarity (most redundant first)
    all_redundancies.sort(key=lambda x: x["similarity"], reverse=True)

    # Generate recommendations
    recommendations = generate_removal_recommendations(all_redundancies, workflow_ids)

    # Calculate stats
    total_redundant_duration = sum(
        _estimate_segment_duration(r["video_b"]["segment"])
        for r in all_redundancies
    )

    return {
        "project_id": project_id,
        "status": "success",
        "analyzed_videos": len(embeddings_by_workflow),
        "missing_embeddings": missing_embeddings,
        "threshold_used": threshold,
        "redundancies": all_redundancies,
        "redundancy_count": len(all_redundancies),
        "total_redundant_duration_sec": total_redundant_duration,
        "recommendations": recommendations,
        "analyzed_at": datetime.utcnow().isoformat()
    }


def _classify_severity(similarity: float) -> str:
    """Classify redundancy severity based on similarity score."""
    if similarity >= HIGH_SIMILARITY_THRESHOLD:
        return "high"  # Very similar, strong candidate for removal
    elif similarity >= 0.90:
        return "medium"  # Similar, should review
    else:
        return "low"  # Somewhat similar, optional removal


def _estimate_segment_duration(segment: Dict[str, Any]) -> float:
    """Estimate segment duration in seconds."""
    start = segment.get("start_sec", 0)
    end = segment.get("end_sec", start + 5)  # Default 5 sec if unknown
    return max(0, end - start)


def generate_removal_recommendations(
    redundancies: List[Dict[str, Any]],
    workflow_ids: List[str]
) -> List[Dict[str, Any]]:
    """
    Generate recommendations for which segments to remove.
    Generally recommends removing from the later video.

    Args:
        redundancies: List of detected redundancies
        workflow_ids: Workflow IDs in sequence order

    Returns:
        List of removal recommendations
    """
    recommendations = []
    processed_segments = set()  # Track to avoid duplicate recommendations

    for redundancy in redundancies:
        video_a = redundancy["video_a"]
        video_b = redundancy["video_b"]

        # Determine which video comes later
        seq_a = video_a.get("sequence_index", 0)
        seq_b = video_b.get("sequence_index", 0)

        # Remove from later video (keeps first mention)
        if seq_a < seq_b:
            to_remove = video_b
            to_keep = video_a
        elif seq_b < seq_a:
            to_remove = video_a
            to_keep = video_b
        else:
            # Same sequence index (shouldn't happen), skip
            continue

        # Create unique key to avoid duplicates
        segment_key = (
            to_remove["workflow_id"],
            to_remove["segment"].get("start_sec"),
            to_remove["segment"].get("end_sec")
        )

        if segment_key in processed_segments:
            continue
        processed_segments.add(segment_key)

        recommendation = {
            "id": f"rec_{redundancy['id']}",
            "type": "remove_redundant_segment",
            "priority": redundancy["severity"],
            "action": {
                "workflow_id": to_remove["workflow_id"],
                "segment": {
                    "start_sec": to_remove["segment"].get("start_sec"),
                    "end_sec": to_remove["segment"].get("end_sec"),
                    "index": to_remove["segment"].get("index")
                }
            },
            "reason": f"Similar content ({redundancy['similarity']:.0%}) already in video {to_keep.get('sequence_index', 0) + 1}",
            "similarity": redundancy["similarity"],
            "estimated_savings_sec": _estimate_segment_duration(to_remove["segment"]),
            "keep_reference": {
                "workflow_id": to_keep["workflow_id"],
                "segment": to_keep["segment"]
            }
        }

        recommendations.append(recommendation)

    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    recommendations.sort(key=lambda x: priority_order.get(x["priority"], 3))

    return recommendations


def detect_text_redundancies(
    project_id: str,
    transcripts: Dict[str, str],
    threshold: float = 0.80
) -> List[Dict[str, Any]]:
    """
    Detect text-based redundancies using transcript comparison.
    Complementary to video embedding comparison.

    Args:
        project_id: The project ID
        transcripts: Dict of workflow_id -> transcript text
        threshold: Similarity threshold for text

    Returns:
        List of text-based redundancies
    """
    # This is a simpler text-based comparison
    # Can be enhanced with sentence embeddings if needed

    redundancies = []
    workflow_ids = list(transcripts.keys())

    for i, wf_a in enumerate(workflow_ids):
        for wf_b in workflow_ids[i + 1:]:
            text_a = transcripts[wf_a]
            text_b = transcripts[wf_b]

            # Find common phrases (simplified)
            common_phrases = _find_common_phrases(text_a, text_b, min_length=20)

            for phrase in common_phrases:
                redundancy = {
                    "type": "text_redundancy",
                    "video_a": wf_a,
                    "video_b": wf_b,
                    "phrase": phrase,
                    "length": len(phrase)
                }
                redundancies.append(redundancy)

    return redundancies


def _find_common_phrases(
    text_a: str,
    text_b: str,
    min_length: int = 20
) -> List[str]:
    """Find common phrases between two texts (simplified LCS-based approach)."""
    words_a = text_a.lower().split()
    words_b = set(text_b.lower().split())

    # Find sequences of consecutive matching words
    common = []
    current_phrase = []

    for word in words_a:
        if word in words_b:
            current_phrase.append(word)
        else:
            if len(current_phrase) >= 5:  # Minimum 5 words
                phrase = " ".join(current_phrase)
                if len(phrase) >= min_length:
                    common.append(phrase)
            current_phrase = []

    # Check last phrase
    if len(current_phrase) >= 5:
        phrase = " ".join(current_phrase)
        if len(phrase) >= min_length:
            common.append(phrase)

    return common


def calculate_project_redundancy_score(
    project_id: str,
    redundancy_analysis: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Calculate an overall redundancy score for the project.

    Args:
        project_id: The project ID
        redundancy_analysis: Result from detect_cross_video_redundancies

    Returns:
        Score and summary statistics
    """
    redundancies = redundancy_analysis.get("redundancies", [])
    recommendations = redundancy_analysis.get("recommendations", [])

    if not redundancies:
        return {
            "project_id": project_id,
            "redundancy_score": 0.0,
            "interpretation": "No redundancies detected",
            "removable_duration_sec": 0,
            "high_priority_count": 0,
            "medium_priority_count": 0,
            "low_priority_count": 0
        }

    # Calculate average similarity of redundancies
    avg_similarity = sum(r["similarity"] for r in redundancies) / len(redundancies)

    # Count by priority
    high_count = sum(1 for r in redundancies if r["severity"] == "high")
    medium_count = sum(1 for r in redundancies if r["severity"] == "medium")
    low_count = sum(1 for r in redundancies if r["severity"] == "low")

    # Calculate removable duration
    removable_sec = sum(r.get("estimated_savings_sec", 0) for r in recommendations)

    # Score from 0-100 (higher = more redundant)
    score = min(100, (
        (high_count * 30) +
        (medium_count * 15) +
        (low_count * 5) +
        (avg_similarity * 20)
    ))

    # Interpretation
    if score >= 70:
        interpretation = "High redundancy - significant content overlap between videos"
    elif score >= 40:
        interpretation = "Moderate redundancy - some repeated content detected"
    elif score >= 10:
        interpretation = "Low redundancy - minimal content overlap"
    else:
        interpretation = "Minimal redundancy - videos have distinct content"

    return {
        "project_id": project_id,
        "redundancy_score": round(score, 1),
        "interpretation": interpretation,
        "removable_duration_sec": round(removable_sec, 1),
        "total_redundancies": len(redundancies),
        "high_priority_count": high_count,
        "medium_priority_count": medium_count,
        "low_priority_count": low_count,
        "avg_similarity": round(avg_similarity, 3)
    }


# ============================================================================
# Storage Functions
# ============================================================================

def save_redundancy_analysis(
    project_id: str,
    analysis: Dict[str, Any],
    bucket_name: Optional[str] = None
) -> str:
    """
    Save redundancy analysis to GCS.

    Args:
        project_id: The project ID
        analysis: The analysis results
        bucket_name: GCS bucket name

    Returns:
        GCS path where analysis was saved
    """
    from google.cloud import storage

    bucket_name = bucket_name or os.environ.get("GCP_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("GCP_BUCKET_NAME required")

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    path = f"projects/{project_id}/context/redundancy_analysis.json"
    blob = bucket.blob(path)

    blob.upload_from_string(
        json.dumps(analysis, ensure_ascii=False),
        content_type="application/json"
    )

    logger.info(f"Saved redundancy analysis to gs://{bucket_name}/{path}")
    return f"gs://{bucket_name}/{path}"


def load_redundancy_analysis(
    project_id: str,
    bucket_name: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Load redundancy analysis from GCS.

    Args:
        project_id: The project ID
        bucket_name: GCS bucket name

    Returns:
        Analysis data or None if not found
    """
    from google.cloud import storage

    bucket_name = bucket_name or os.environ.get("GCP_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("GCP_BUCKET_NAME required")

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    path = f"projects/{project_id}/context/redundancy_analysis.json"
    blob = bucket.blob(path)

    if not blob.exists():
        return None

    content = blob.download_as_string()
    return json.loads(content)
