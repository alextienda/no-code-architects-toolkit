# Copyright (c) 2025
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

"""
B-Roll Analysis Service with Gemini Vision

Analyzes video frames to identify B-Roll segments using Gemini 2.5 Pro Vision
via Vertex AI. Extracts frames, sends to Gemini for visual analysis, and
returns structured segment data.
"""

import os
import json
import re
import logging
import requests
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

from services.v1.autoedit.frame_extractor import (
    FrameExtractor,
    extract_frames_for_analysis,
    get_video_info
)

logger = logging.getLogger(__name__)

# Gemini Vision Configuration
BROLL_CONFIG = {
    "model": "gemini-2.5-pro",
    "temperature": 0.0,
    "max_tokens": 65536,
    "project_id": os.environ.get("GCP_PROJECT_ID", "autoedit-at"),
    "location": os.environ.get("GCP_LOCATION", "us-central1")
}

# Frame extraction settings for B-Roll analysis
BROLL_FRAME_CONFIG = {
    "frame_interval_sec": 2.0,   # 1 frame every 2 seconds
    "max_frames": 30,            # Maximum frames per analysis
    "output_width": 1280         # Resize width for frames
}

# Path to B-Roll prompt
BROLL_PROMPT_PATH = Path(__file__).parent.parent.parent.parent / "infrastructure" / "prompts" / "autoedit_broll_prompt.txt"


def load_broll_prompt() -> str:
    """Load the B-Roll analysis system prompt from file."""
    try:
        if BROLL_PROMPT_PATH.exists():
            with open(BROLL_PROMPT_PATH, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            logger.warning(f"B-Roll prompt not found at {BROLL_PROMPT_PATH}, using default")
            return get_default_broll_prompt()
    except Exception as e:
        logger.error(f"Error loading B-Roll prompt: {e}")
        return get_default_broll_prompt()


def get_default_broll_prompt() -> str:
    """Return a minimal default B-Roll prompt."""
    return """You are a B-Roll analysis agent. Analyze the provided video frames and identify segments that are B-Roll (supporting footage without dialogue).

Return a JSON object with:
{
  "analysis_summary": {
    "total_broll_segments": number,
    "total_broll_duration_ms": number,
    "broll_percentage": number,
    "dominant_category": string
  },
  "segments": [
    {
      "segment_id": "broll_001",
      "inMs": number,
      "outMs": number,
      "duration_ms": number,
      "type": "B-Roll",
      "category": "establishing_shot|detail_shot|transition_shot|ambient_shot|action_shot",
      "description": string,
      "scores": {
        "technical_quality": 1-5,
        "visual_appeal": 1-5,
        "usefulness": 1-5,
        "overall": 1-5
      },
      "confidence": 0.0-1.0
    }
  ]
}

Only include segments with confidence >= 0.5 and duration >= 2000ms.
Return ONLY the JSON, no additional text."""


def get_gcp_access_token() -> str:
    """Get GCP access token for Vertex AI API calls."""
    # Check for Cloud Run environment
    if os.environ.get("K_SERVICE"):
        try:
            response = requests.get(
                "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
                headers={"Metadata-Flavor": "Google"},
                timeout=5
            )
            if response.status_code == 200:
                return response.json()["access_token"]
        except Exception as e:
            logger.warning(f"Metadata server failed: {e}")

    # Try Application Default Credentials
    try:
        from google.auth import default
        from google.auth.transport.requests import Request
        credentials, project = default()
        credentials.refresh(Request())
        return credentials.token
    except Exception as e:
        logger.error(f"Failed to get GCP access token: {e}")
        raise


def build_gemini_vision_request(
    frames: List[Dict[str, Any]],
    video_metadata: Dict[str, Any],
    system_prompt: str
) -> Dict[str, Any]:
    """Build the Gemini Vision API request payload.

    Args:
        frames: List of frame dicts with base64 data
        video_metadata: Video info (duration, etc.)
        system_prompt: System prompt for analysis

    Returns:
        Request payload dict for Vertex AI
    """
    # Build user content with frames
    user_parts = []

    # Add metadata header
    metadata_text = f"""VIDEO_METADATA:
- filename: {video_metadata.get('video_path', 'unknown').split('/')[-1]}
- duration_ms: {video_metadata.get('duration_ms', 0)}
- duration_sec: {video_metadata.get('duration_sec', 0)}
- frames_extracted: {len(frames)}
- frame_interval_sec: {video_metadata.get('frame_interval_sec', 2.0)}

FRAMES:
"""
    user_parts.append({"text": metadata_text})

    # Add each frame with timestamp
    for frame in frames:
        # Add frame label
        user_parts.append({
            "text": f"\nFrame {frame['frame_number']} ({frame['timestamp_ms']}ms):"
        })

        # Add frame image
        user_parts.append({
            "inline_data": {
                "mime_type": frame.get("mime_type", "image/jpeg"),
                "data": frame["base64"]
            }
        })

    # Build full request
    request_payload = {
        "contents": [
            {
                "role": "user",
                "parts": user_parts
            }
        ],
        "systemInstruction": {
            "parts": [{"text": system_prompt}]
        },
        "generationConfig": {
            "temperature": BROLL_CONFIG["temperature"],
            "maxOutputTokens": BROLL_CONFIG["max_tokens"],
            "responseMimeType": "application/json"
        }
    }

    return request_payload


def call_gemini_vision(
    request_payload: Dict[str, Any],
    access_token: str
) -> Dict[str, Any]:
    """Call Gemini Vision API via Vertex AI.

    Args:
        request_payload: API request payload
        access_token: GCP access token

    Returns:
        Parsed JSON response from Gemini
    """
    project_id = BROLL_CONFIG["project_id"]
    location = BROLL_CONFIG["location"]
    model = BROLL_CONFIG["model"]

    url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}/publishers/google/models/{model}:generateContent"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    logger.info(f"Calling Gemini Vision API: {model}")

    try:
        response = requests.post(
            url,
            headers=headers,
            json=request_payload,
            timeout=120  # 2 minute timeout for vision analysis
        )

        if response.status_code != 200:
            logger.error(f"Gemini API error {response.status_code}: {response.text[:500]}")
            return {"error": f"API error: {response.status_code}", "details": response.text}

        result = response.json()

        # Extract text from response
        candidates = result.get("candidates", [])
        if not candidates:
            return {"error": "No candidates in response"}

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])

        if not parts:
            return {"error": "No parts in response"}

        text_response = parts[0].get("text", "")

        # Parse JSON from response
        return parse_broll_response(text_response)

    except requests.exceptions.Timeout:
        logger.error("Gemini Vision API timeout")
        return {"error": "API timeout"}
    except Exception as e:
        logger.error(f"Error calling Gemini Vision: {e}")
        return {"error": str(e)}


def parse_broll_response(text: str) -> Dict[str, Any]:
    """Parse and validate B-Roll analysis response.

    Args:
        text: Raw text response from Gemini

    Returns:
        Parsed and validated JSON dict
    """
    # Try direct JSON parse
    try:
        data = json.loads(text)
        return validate_broll_response(data)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from markdown code blocks
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            return validate_broll_response(data)
        except json.JSONDecodeError:
            pass

    # Try to find JSON object in text
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            return validate_broll_response(data)
        except json.JSONDecodeError:
            pass

    logger.error(f"Could not parse B-Roll response: {text[:500]}")
    return {
        "error": "Failed to parse response",
        "raw_text": text[:1000],
        "analysis_summary": {
            "total_broll_segments": 0,
            "total_broll_duration_ms": 0,
            "broll_percentage": 0,
            "dominant_category": "unknown"
        },
        "segments": []
    }


def validate_broll_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize B-Roll response structure.

    Args:
        data: Parsed JSON data

    Returns:
        Validated and normalized data
    """
    # Ensure required fields exist
    if "analysis_summary" not in data:
        data["analysis_summary"] = {
            "total_broll_segments": 0,
            "total_broll_duration_ms": 0,
            "broll_percentage": 0,
            "dominant_category": "unknown"
        }

    if "segments" not in data:
        data["segments"] = []

    # Validate each segment
    valid_segments = []
    for i, segment in enumerate(data.get("segments", [])):
        # Ensure required fields
        if "inMs" not in segment or "outMs" not in segment:
            continue

        # Calculate duration if missing
        if "duration_ms" not in segment:
            segment["duration_ms"] = segment["outMs"] - segment["inMs"]

        # Skip too short segments
        if segment["duration_ms"] < 2000:
            continue

        # Skip low confidence
        if segment.get("confidence", 0) < 0.5:
            continue

        # Ensure segment_id
        if "segment_id" not in segment:
            segment["segment_id"] = f"broll_{i+1:03d}"

        # Ensure type
        if "type" not in segment:
            segment["type"] = "B-Roll"

        # Ensure scores
        if "scores" not in segment:
            segment["scores"] = {
                "technical_quality": 3,
                "visual_appeal": 3,
                "usefulness": 3,
                "overall": 3
            }

        valid_segments.append(segment)

    data["segments"] = valid_segments

    # Update summary
    data["analysis_summary"]["total_broll_segments"] = len(valid_segments)
    data["analysis_summary"]["total_broll_duration_ms"] = sum(
        s.get("duration_ms", 0) for s in valid_segments
    )

    return data


def analyze_video_broll(
    video_path: str,
    frame_interval: float = BROLL_FRAME_CONFIG["frame_interval_sec"],
    max_frames: int = BROLL_FRAME_CONFIG["max_frames"]
) -> Dict[str, Any]:
    """Main function to analyze a video for B-Roll segments.

    Args:
        video_path: Path to video file (local or URL)
        frame_interval: Seconds between frame extractions
        max_frames: Maximum frames to extract

    Returns:
        Dict with B-Roll analysis results
    """
    logger.info(f"Starting B-Roll analysis for: {video_path}")

    try:
        # Step 1: Extract frames
        logger.info("Extracting frames for analysis...")
        frames, metadata = extract_frames_for_analysis(
            video_path,
            frame_interval=frame_interval,
            max_frames=max_frames
        )

        if not frames:
            return {
                "error": "No frames extracted",
                "video_path": video_path,
                "analysis_summary": {
                    "total_broll_segments": 0,
                    "total_broll_duration_ms": 0,
                    "broll_percentage": 0
                },
                "segments": []
            }

        logger.info(f"Extracted {len(frames)} frames")

        # Step 2: Load system prompt
        system_prompt = load_broll_prompt()

        # Step 3: Build API request
        request_payload = build_gemini_vision_request(
            frames=frames,
            video_metadata=metadata,
            system_prompt=system_prompt
        )

        # Step 4: Get access token
        access_token = get_gcp_access_token()

        # Step 5: Call Gemini Vision API
        logger.info("Calling Gemini Vision for B-Roll analysis...")
        result = call_gemini_vision(request_payload, access_token)

        # Step 6: Calculate percentages
        if "error" not in result:
            video_duration = metadata.get("duration_ms", 0)
            broll_duration = result.get("analysis_summary", {}).get("total_broll_duration_ms", 0)
            if video_duration > 0:
                result["analysis_summary"]["broll_percentage"] = round(
                    (broll_duration / video_duration) * 100, 1
                )

            result["metadata"] = metadata

        logger.info(f"B-Roll analysis complete: {result.get('analysis_summary', {}).get('total_broll_segments', 0)} segments found")

        return result

    except Exception as e:
        logger.error(f"Error in B-Roll analysis: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "error": str(e),
            "video_path": video_path,
            "analysis_summary": {
                "total_broll_segments": 0,
                "total_broll_duration_ms": 0,
                "broll_percentage": 0
            },
            "segments": []
        }


# =============================================================================
# WORKFLOW INTEGRATION
# =============================================================================

def analyze_workflow_broll(workflow_id: str) -> Dict[str, Any]:
    """Analyze B-Roll for a workflow and update its state.

    Args:
        workflow_id: The workflow ID to analyze

    Returns:
        Analysis result dict
    """
    from services.v1.autoedit.workflow import get_workflow, update_workflow

    logger.info(f"Analyzing B-Roll for workflow {workflow_id}")

    # Get workflow
    workflow = get_workflow(workflow_id)
    if not workflow:
        return {"error": "Workflow not found", "workflow_id": workflow_id}

    video_url = workflow.get("video_url")
    if not video_url:
        return {"error": "No video URL in workflow", "workflow_id": workflow_id}

    # Run analysis
    result = analyze_video_broll(video_url)

    # Update workflow with results
    if "error" not in result:
        update_workflow(workflow_id, {
            "broll_segments": result.get("segments", []),
            "broll_analysis_complete": True
        })

        logger.info(f"Updated workflow {workflow_id} with {len(result.get('segments', []))} B-Roll segments")
    else:
        logger.error(f"B-Roll analysis failed for workflow {workflow_id}: {result.get('error')}")

    return result
