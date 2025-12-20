# Copyright (c) 2025
#
# TwelveLabs Embeddings Service for AutoEdit
#
# Uses Marengo 3.0 to generate video embeddings for:
# - Cross-video redundancy detection
# - Semantic similarity search
# - Context-aware analysis

"""
TwelveLabs Video Embeddings Service

Generates embeddings using Marengo 3.0 model for video content understanding.
Supports both synchronous (< 10 min) and asynchronous (up to 4 hours) processing.

Environment Variables:
    TWELVELABS_API_KEY: API key for TwelveLabs
"""

import os
import json
import time
import logging
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# Configuration
TWELVELABS_API_KEY = os.environ.get("TWELVELABS_API_KEY", "")
MARENGO_MODEL = "marengo3.0"
MAX_SYNC_DURATION_SEC = 600  # 10 minutes
MAX_ASYNC_DURATION_SEC = 14400  # 4 hours
POLL_INTERVAL_SEC = 5
MAX_POLL_ATTEMPTS = 120  # 10 minutes max wait


def get_twelvelabs_client():
    """
    Get TwelveLabs client with API key.

    Returns:
        TwelveLabs client instance

    Raises:
        ValueError: If API key is not configured
    """
    if not TWELVELABS_API_KEY:
        raise ValueError("TWELVELABS_API_KEY environment variable is required")

    try:
        from twelvelabs import TwelveLabs
        return TwelveLabs(api_key=TWELVELABS_API_KEY)
    except ImportError:
        raise ImportError("twelvelabs package not installed. Run: pip install twelvelabs")


def create_video_embeddings_sync(
    video_url: str,
    start_sec: float = 0.0,
    end_sec: Optional[float] = None,
    embedding_options: List[str] = None
) -> Dict[str, Any]:
    """
    Create embeddings synchronously for videos < 10 minutes.

    Args:
        video_url: URL of the video file (GCS, S3, or HTTP)
        start_sec: Start time in seconds (default: 0)
        end_sec: End time in seconds (default: full video)
        embedding_options: What to embed: ["visual", "audio", "transcription"]

    Returns:
        Dict with embeddings and metadata:
        {
            "success": True,
            "embeddings": [...],  # List of embedding vectors
            "segments": [...],    # Segments with timestamps
            "model": "marengo3.0",
            "created_at": "..."
        }
    """
    if embedding_options is None:
        embedding_options = ["visual", "audio"]

    try:
        from twelvelabs import MediaSource, VideoInputRequest

        client = get_twelvelabs_client()

        video_request = VideoInputRequest(
            media_source=MediaSource(url=video_url),
            start_sec=start_sec,
            embedding_option=embedding_options
        )

        if end_sec is not None:
            video_request.end_sec = end_sec

        logger.info(f"Creating sync embeddings for video: {video_url[:100]}...")

        response = client.embed.v_2.create(
            input_type="video",
            model_name=MARENGO_MODEL,
            video=video_request
        )

        # Parse response
        embeddings = []
        segments = []

        if hasattr(response, 'data') and response.data:
            for item in response.data:
                if hasattr(item, 'embedding'):
                    embeddings.append(item.embedding)
                if hasattr(item, 'start_sec') and hasattr(item, 'end_sec'):
                    segments.append({
                        "start_sec": item.start_sec,
                        "end_sec": item.end_sec,
                        "embedding_index": len(embeddings) - 1
                    })

        logger.info(f"Created {len(embeddings)} embeddings for video")

        return {
            "success": True,
            "embeddings": embeddings,
            "segments": segments,
            "model": MARENGO_MODEL,
            "video_url": video_url,
            "created_at": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Error creating sync embeddings: {e}")
        return {
            "success": False,
            "error": str(e),
            "video_url": video_url
        }


def create_video_embeddings_async(
    video_url: str,
    start_sec: float = 0.0,
    end_sec: Optional[float] = None,
    embedding_options: List[str] = None,
    embedding_scope: List[str] = None,
    min_segment_duration: float = 4.0
) -> Dict[str, Any]:
    """
    Create embeddings asynchronously for videos up to 4 hours.
    Returns task_id for polling.

    Args:
        video_url: URL of the video file
        start_sec: Start time in seconds
        end_sec: End time in seconds
        embedding_options: What to embed: ["visual", "audio", "transcription"]
        embedding_scope: Granularity: ["clip", "asset"]
        min_segment_duration: Minimum segment duration for dynamic segmentation

    Returns:
        Dict with task_id for polling:
        {
            "success": True,
            "task_id": "...",
            "status": "processing"
        }
    """
    if embedding_options is None:
        embedding_options = ["visual", "audio"]

    if embedding_scope is None:
        embedding_scope = ["clip", "asset"]

    try:
        from twelvelabs import (
            MediaSource,
            VideoInputRequest,
            VideoSegmentation_Dynamic,
            VideoSegmentationDynamicDynamic
        )

        client = get_twelvelabs_client()

        video_request = VideoInputRequest(
            media_source=MediaSource(url=video_url),
            start_sec=start_sec,
            segmentation=VideoSegmentation_Dynamic(
                dynamic=VideoSegmentationDynamicDynamic(
                    min_duration_sec=min_segment_duration
                )
            ),
            embedding_option=embedding_options,
            embedding_scope=embedding_scope
        )

        if end_sec is not None:
            video_request.end_sec = end_sec

        logger.info(f"Creating async embeddings task for video: {video_url[:100]}...")

        response = client.embed.v_2.tasks.create(
            input_type="video",
            model_name=MARENGO_MODEL,
            video=video_request
        )

        task_id = response.id if hasattr(response, 'id') else str(response)

        logger.info(f"Created async embeddings task: {task_id}")

        return {
            "success": True,
            "task_id": task_id,
            "status": "processing",
            "video_url": video_url,
            "created_at": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Error creating async embeddings task: {e}")
        return {
            "success": False,
            "error": str(e),
            "video_url": video_url
        }


def get_embeddings_task_status(task_id: str) -> Dict[str, Any]:
    """
    Get status and results of an async embeddings task.

    Args:
        task_id: The task ID from create_video_embeddings_async

    Returns:
        Dict with status and embeddings (if ready):
        {
            "status": "processing" | "ready" | "failed",
            "embeddings": [...],  # Only if status == "ready"
            "segments": [...]     # Only if status == "ready"
        }
    """
    try:
        client = get_twelvelabs_client()

        response = client.embed.v_2.tasks.retrieve(task_id=task_id)

        status = response.status if hasattr(response, 'status') else "unknown"

        result = {
            "task_id": task_id,
            "status": status
        }

        if status == "ready":
            embeddings = []
            segments = []

            if hasattr(response, 'data') and response.data:
                for item in response.data:
                    if hasattr(item, 'embedding'):
                        embeddings.append(item.embedding)
                    if hasattr(item, 'start_sec') and hasattr(item, 'end_sec'):
                        segments.append({
                            "start_sec": item.start_sec,
                            "end_sec": item.end_sec,
                            "embedding_index": len(embeddings) - 1
                        })

            result["embeddings"] = embeddings
            result["segments"] = segments
            result["model"] = MARENGO_MODEL

        elif status == "failed":
            result["error"] = getattr(response, 'error', 'Unknown error')

        return result

    except Exception as e:
        logger.error(f"Error getting embeddings task status: {e}")
        return {
            "task_id": task_id,
            "status": "error",
            "error": str(e)
        }


def wait_for_embeddings(
    task_id: str,
    poll_interval: int = POLL_INTERVAL_SEC,
    max_attempts: int = MAX_POLL_ATTEMPTS
) -> Dict[str, Any]:
    """
    Wait for async embeddings task to complete.

    Args:
        task_id: The task ID to wait for
        poll_interval: Seconds between polls
        max_attempts: Maximum number of poll attempts

    Returns:
        Final status with embeddings or error
    """
    logger.info(f"Waiting for embeddings task {task_id}...")

    for attempt in range(max_attempts):
        result = get_embeddings_task_status(task_id)
        status = result.get("status")

        if status == "ready":
            logger.info(f"Embeddings task {task_id} completed")
            return result

        if status == "failed" or status == "error":
            logger.error(f"Embeddings task {task_id} failed: {result.get('error')}")
            return result

        logger.debug(f"Task {task_id} still processing, attempt {attempt + 1}/{max_attempts}")
        time.sleep(poll_interval)

    logger.error(f"Embeddings task {task_id} timed out after {max_attempts} attempts")
    return {
        "task_id": task_id,
        "status": "timeout",
        "error": f"Task did not complete after {max_attempts * poll_interval} seconds"
    }


def create_video_embeddings(
    video_url: str,
    video_duration_sec: Optional[float] = None,
    start_sec: float = 0.0,
    end_sec: Optional[float] = None,
    wait_for_result: bool = True
) -> Dict[str, Any]:
    """
    Smart wrapper that chooses sync or async based on video duration.

    Args:
        video_url: URL of the video file
        video_duration_sec: Known duration (if available, avoids probing)
        start_sec: Start time in seconds
        end_sec: End time in seconds
        wait_for_result: If async, wait for completion

    Returns:
        Embeddings result or task info
    """
    # Calculate effective duration
    effective_duration = end_sec - start_sec if end_sec else video_duration_sec

    # Use sync for short videos, async for long ones
    if effective_duration and effective_duration <= MAX_SYNC_DURATION_SEC:
        logger.info(f"Using sync embeddings for {effective_duration}s video")
        return create_video_embeddings_sync(video_url, start_sec, end_sec)
    else:
        logger.info(f"Using async embeddings for video")
        result = create_video_embeddings_async(video_url, start_sec, end_sec)

        if result.get("success") and wait_for_result:
            return wait_for_embeddings(result["task_id"])

        return result


# ============================================================================
# Similarity Functions
# ============================================================================

def cosine_similarity(embedding_a: List[float], embedding_b: List[float]) -> float:
    """
    Calculate cosine similarity between two embedding vectors.

    Args:
        embedding_a: First embedding vector
        embedding_b: Second embedding vector

    Returns:
        Similarity score between -1 and 1 (1 = identical)
    """
    a = np.array(embedding_a)
    b = np.array(embedding_b)

    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(np.dot(a, b) / (norm_a * norm_b))


def find_similar_segments(
    query_embedding: List[float],
    embeddings_data: Dict[str, Any],
    threshold: float = 0.85,
    max_results: int = 10
) -> List[Dict[str, Any]]:
    """
    Find segments similar to a query embedding.

    Args:
        query_embedding: The embedding to search for
        embeddings_data: Dict with embeddings and segments
        threshold: Minimum similarity threshold
        max_results: Maximum results to return

    Returns:
        List of similar segments with scores
    """
    results = []

    embeddings = embeddings_data.get("embeddings", [])
    segments = embeddings_data.get("segments", [])

    for i, emb in enumerate(embeddings):
        similarity = cosine_similarity(query_embedding, emb)

        if similarity >= threshold:
            segment_info = segments[i] if i < len(segments) else {}
            results.append({
                "embedding_index": i,
                "similarity": similarity,
                "start_sec": segment_info.get("start_sec"),
                "end_sec": segment_info.get("end_sec")
            })

    # Sort by similarity descending
    results.sort(key=lambda x: x["similarity"], reverse=True)

    return results[:max_results]


def compare_video_embeddings(
    embeddings_a: Dict[str, Any],
    embeddings_b: Dict[str, Any],
    threshold: float = 0.85
) -> List[Dict[str, Any]]:
    """
    Compare embeddings between two videos to find similar segments.

    Args:
        embeddings_a: Embeddings from first video
        embeddings_b: Embeddings from second video
        threshold: Minimum similarity to consider as match

    Returns:
        List of matching segment pairs with similarity scores
    """
    matches = []

    emb_list_a = embeddings_a.get("embeddings", [])
    emb_list_b = embeddings_b.get("embeddings", [])
    segments_a = embeddings_a.get("segments", [])
    segments_b = embeddings_b.get("segments", [])

    for i, emb_a in enumerate(emb_list_a):
        for j, emb_b in enumerate(emb_list_b):
            similarity = cosine_similarity(emb_a, emb_b)

            if similarity >= threshold:
                seg_a = segments_a[i] if i < len(segments_a) else {}
                seg_b = segments_b[j] if j < len(segments_b) else {}

                matches.append({
                    "segment_a": {
                        "index": i,
                        "start_sec": seg_a.get("start_sec"),
                        "end_sec": seg_a.get("end_sec")
                    },
                    "segment_b": {
                        "index": j,
                        "start_sec": seg_b.get("start_sec"),
                        "end_sec": seg_b.get("end_sec")
                    },
                    "similarity": similarity
                })

    # Sort by similarity descending
    matches.sort(key=lambda x: x["similarity"], reverse=True)

    return matches


def calculate_video_similarity(
    embeddings_a: Dict[str, Any],
    embeddings_b: Dict[str, Any]
) -> float:
    """
    Calculate overall similarity between two videos.
    Uses average of top-k segment similarities.

    Args:
        embeddings_a: Embeddings from first video
        embeddings_b: Embeddings from second video

    Returns:
        Overall similarity score (0-1)
    """
    matches = compare_video_embeddings(embeddings_a, embeddings_b, threshold=0.0)

    if not matches:
        return 0.0

    # Use average of top-k similarities
    k = min(5, len(matches))
    top_similarities = [m["similarity"] for m in matches[:k]]

    return sum(top_similarities) / len(top_similarities)


# ============================================================================
# Storage Functions
# ============================================================================

def save_embeddings_to_gcs(
    workflow_id: str,
    embeddings_data: Dict[str, Any],
    bucket_name: Optional[str] = None
) -> str:
    """
    Save embeddings to GCS for later retrieval.

    Args:
        workflow_id: The workflow ID
        embeddings_data: The embeddings data to save
        bucket_name: GCS bucket (defaults to GCP_BUCKET_NAME)

    Returns:
        GCS path where embeddings were saved
    """
    from google.cloud import storage
    import json

    bucket_name = bucket_name or os.environ.get("GCP_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("GCP_BUCKET_NAME environment variable required")

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    path = f"embeddings/{workflow_id}.json"
    blob = bucket.blob(path)

    blob.upload_from_string(
        json.dumps(embeddings_data),
        content_type="application/json"
    )

    logger.info(f"Saved embeddings to gs://{bucket_name}/{path}")

    return f"gs://{bucket_name}/{path}"


def load_embeddings_from_gcs(
    workflow_id: str,
    bucket_name: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Load embeddings from GCS.

    Args:
        workflow_id: The workflow ID
        bucket_name: GCS bucket

    Returns:
        Embeddings data or None if not found
    """
    from google.cloud import storage
    import json

    bucket_name = bucket_name or os.environ.get("GCP_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("GCP_BUCKET_NAME environment variable required")

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    path = f"embeddings/{workflow_id}.json"
    blob = bucket.blob(path)

    if not blob.exists():
        logger.warning(f"Embeddings not found: gs://{bucket_name}/{path}")
        return None

    content = blob.download_as_string()
    return json.loads(content)
