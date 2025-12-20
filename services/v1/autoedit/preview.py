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
Preview Renderer Service for AutoEdit Pipeline

Generates low-resolution preview videos for HITL 2 (Human-in-the-Loop).
Uses FFmpeg compose with preview render profiles for fast generation.
"""

import os
import time
import logging
import requests
from typing import Dict, Any, List, Optional, Tuple

from config import LOCAL_STORAGE_PATH
from services.cloud_storage import upload_file
from services.v1.autoedit.ffmpeg_builder import (
    build_preview_payload,
    build_final_render_payload,
    blocks_to_cuts,
    estimate_render_time,
    get_video_dimensions_from_url
)
from services.v1.autoedit.blocks import (
    calculate_gaps,
    calculate_stats,
    ensure_block_ids,
    add_preview_positions
)

logger = logging.getLogger(__name__)

# NCA Toolkit endpoint (internal or external)
NCA_TOOLKIT_URL = os.environ.get("NCA_TOOLKIT_URL", "http://localhost:8080")
NCA_API_KEY = os.environ.get("NCA_API_KEY", os.environ.get("API_KEY", ""))


def generate_preview(
    workflow_id: str,
    video_url: str,
    blocks: List[Dict[str, Any]],
    video_duration_ms: int,
    transcript_words: Optional[List[Dict[str, Any]]] = None,
    quality: str = "480p",
    fade_duration: float = 0.025,
    video_width: Optional[int] = None,
    video_height: Optional[int] = None
) -> Dict[str, Any]:
    """Generate a low-resolution preview video.

    Args:
        workflow_id: Workflow identifier (used for naming)
        video_url: Source video URL
        blocks: List of blocks with inMs/outMs timestamps
        video_duration_ms: Total video duration in milliseconds
        transcript_words: Optional transcript for gap text extraction
        quality: Preview quality ('480p' or '720p')
        fade_duration: Crossfade duration in seconds
        video_width: Original video width (for aspect ratio preservation)
        video_height: Original video height (for aspect ratio preservation)

    Returns:
        Dict with preview_url, blocks, gaps, and stats
    """
    start_time = time.time()

    # Get video dimensions if not provided (for aspect ratio preservation)
    if video_width is None or video_height is None:
        logger.info(f"Getting video dimensions for aspect ratio preservation...")
        video_width, video_height = get_video_dimensions_from_url(video_url)
        logger.info(f"Video dimensions: {video_width}x{video_height}")

    # Ensure blocks have IDs
    blocks = ensure_block_ids(blocks)

    # Convert blocks to cuts
    cuts = blocks_to_cuts(blocks)

    if not cuts:
        raise ValueError("No valid cuts to preview")

    # Build FFmpeg payload for preview (with aspect ratio preservation)
    payload = build_preview_payload(
        video_url=video_url,
        cuts=cuts,
        quality=quality,
        fade_duration=fade_duration,
        video_width=video_width,
        video_height=video_height
    )

    logger.info(f"Generating preview for workflow {workflow_id} with {len(cuts)} cuts")

    # Call FFmpeg compose endpoint
    preview_url = _call_ffmpeg_compose(payload, f"preview_{workflow_id}")

    # Calculate gaps and stats
    gaps = calculate_gaps(blocks, video_duration_ms, transcript_words)
    stats = calculate_stats(blocks, video_duration_ms)

    # Add preview positions to blocks
    blocks_with_preview = add_preview_positions(blocks, fade_duration * 1000)

    render_time = time.time() - start_time
    stats["render_time_sec"] = round(render_time, 2)

    logger.info(f"Preview generated in {render_time:.2f}s: {preview_url}")

    return {
        "preview_url": preview_url,
        "preview_duration_ms": stats["result_duration_ms"],
        "blocks": blocks_with_preview,
        "gaps": gaps,
        "video_duration_ms": video_duration_ms,
        "stats": stats
    }


def generate_final_render(
    workflow_id: str,
    video_url: str,
    blocks: List[Dict[str, Any]],
    video_duration_ms: int,
    quality: str = "high",
    fade_duration: float = 0.025,
    video_width: Optional[int] = None,
    video_height: Optional[int] = None
) -> Dict[str, Any]:
    """Generate the final high-quality render.

    Args:
        workflow_id: Workflow identifier
        video_url: Source video URL
        blocks: List of blocks with inMs/outMs timestamps
        video_duration_ms: Total video duration in milliseconds
        quality: Output quality ('standard', 'high', '4k')
        fade_duration: Crossfade duration in seconds
        video_width: Original video width (for aspect ratio preservation)
        video_height: Original video height (for aspect ratio preservation)

    Returns:
        Dict with output_url and stats
    """
    start_time = time.time()

    # Get video dimensions if not provided (for aspect ratio preservation)
    if video_width is None or video_height is None:
        logger.info(f"Getting video dimensions for aspect ratio preservation...")
        video_width, video_height = get_video_dimensions_from_url(video_url)
        logger.info(f"Video dimensions: {video_width}x{video_height}")

    # Convert blocks to cuts
    cuts = blocks_to_cuts(blocks)

    if not cuts:
        raise ValueError("No valid cuts to render")

    # Build FFmpeg payload for final render (with aspect ratio preservation)
    payload = build_final_render_payload(
        video_url=video_url,
        cuts=cuts,
        quality=quality,
        fade_duration=fade_duration,
        video_width=video_width,
        video_height=video_height
    )

    logger.info(f"Starting final render for workflow {workflow_id} with {len(cuts)} cuts at {quality} quality")

    # Call FFmpeg compose endpoint
    output_url = _call_ffmpeg_compose(payload, f"final_{workflow_id}")

    # Calculate stats
    stats = calculate_stats(blocks, video_duration_ms)
    render_time = time.time() - start_time
    stats["render_time_sec"] = round(render_time, 2)
    stats["output_quality"] = quality

    logger.info(f"Final render completed in {render_time:.2f}s: {output_url}")

    return {
        "output_url": output_url,
        "output_duration_ms": stats["result_duration_ms"],
        "stats": stats
    }


def _call_ffmpeg_compose(payload: Dict[str, Any], job_id: str) -> str:
    """Call the FFmpeg compose endpoint.

    Args:
        payload: FFmpeg compose payload
        job_id: Job identifier for naming

    Returns:
        URL of the output file

    Raises:
        Exception: If the compose fails
    """
    endpoint = f"{NCA_TOOLKIT_URL}/v1/ffmpeg/compose"

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": NCA_API_KEY
    }

    # Add job_id to payload
    payload["id"] = job_id

    logger.debug(f"Calling FFmpeg compose: {endpoint}")
    logger.debug(f"Payload: {payload}")

    try:
        response = requests.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=600  # 10 minute timeout for long renders
        )

        if response.status_code != 200:
            error_msg = f"FFmpeg compose failed with status {response.status_code}: {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)

        result = response.json()
        logger.debug(f"FFmpeg compose raw response type: {type(result)}, content: {str(result)[:500]}")

        # Handle case where result is not a dict
        if isinstance(result, list):
            logger.error(f"FFmpeg compose returned a list instead of dict: {result}")
            raise Exception(f"Unexpected response format from FFmpeg compose: {result}")

        # Extract output URL from response - handle multiple response formats
        response_data = result.get("response", {})

        # Handle case where response is a list (shouldn't happen but defensive)
        if isinstance(response_data, list):
            logger.warning(f"FFmpeg compose response.response is a list: {response_data}")
            if len(response_data) > 0 and isinstance(response_data[0], dict):
                response_data = response_data[0]
            else:
                response_data = {}

        output_url = None
        if isinstance(response_data, dict):
            # Try multiple possible field names
            output_url = (
                response_data.get("output_url") or
                response_data.get("file_url") or
                response_data.get("url")
            )

        if not output_url:
            # Try alternative response formats at root level
            output_url = result.get("output_url") or result.get("file_url") or result.get("url")

        if not output_url:
            raise Exception(f"No output URL in response: {result}")

        return output_url

    except requests.exceptions.Timeout:
        raise Exception("FFmpeg compose timed out after 10 minutes")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Failed to call FFmpeg compose: {e}")


def cleanup_old_previews(workflow_id: str, keep_latest: int = 2) -> int:
    """Clean up old preview files for a workflow.

    Args:
        workflow_id: Workflow identifier
        keep_latest: Number of recent previews to keep

    Returns:
        Number of files deleted
    """
    # Note: This is a placeholder. In production, you'd want to:
    # 1. Track preview URLs in the workflow state
    # 2. Delete from cloud storage when generating new previews
    # For now, we rely on cloud storage lifecycle policies
    logger.info(f"Cleanup requested for workflow {workflow_id}, keeping {keep_latest} latest")
    return 0


def estimate_preview_time(blocks: List[Dict[str, Any]]) -> float:
    """Estimate time to generate a preview.

    Args:
        blocks: List of blocks

    Returns:
        Estimated time in seconds
    """
    if not blocks:
        return 0

    total_duration_ms = sum(b["outMs"] - b["inMs"] for b in blocks)
    return estimate_render_time(
        video_duration_sec=total_duration_ms / 1000,
        n_cuts=len(blocks),
        profile="preview"
    )


def estimate_render_time_for_blocks(
    blocks: List[Dict[str, Any]],
    quality: str = "high"
) -> float:
    """Estimate time to render final video.

    Args:
        blocks: List of blocks
        quality: Render quality

    Returns:
        Estimated time in seconds
    """
    if not blocks:
        return 0

    total_duration_ms = sum(b["outMs"] - b["inMs"] for b in blocks)
    return estimate_render_time(
        video_duration_sec=total_duration_ms / 1000,
        n_cuts=len(blocks),
        profile=quality
    )
