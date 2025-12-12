# Copyright (c) 2025 Stephen G. Pope
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

"""
Map Timestamps Endpoint for AutoEdit pipeline.

Maps Gemini's XML output back to actual timestamps using word-level
alignment from the original Whisper transcription.
"""

from flask import Blueprint
from app_utils import validate_payload, queue_task_wrapper
from services.authentication import authenticate
from services.v1.autoedit.map_timestamps import (
    map_gemini_output_to_timestamps,
    generate_cuts_from_mapped_segments
)
import logging

v1_autoedit_map_timestamps_bp = Blueprint('v1_autoedit_map_timestamps', __name__)
logger = logging.getLogger(__name__)


@v1_autoedit_map_timestamps_bp.route('/v1/autoedit/map-timestamps', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "gemini_output": {
            "type": "array",
            "description": "Gemini blocks with blockID and outputXML",
            "items": {
                "type": "object",
                "properties": {
                    "blockID": {"type": "string"},
                    "outputXML": {"type": "string"},
                    "speaker": {"type": "string"}
                },
                "required": ["blockID", "outputXML"]
            }
        },
        "original_transcription": {
            "type": "object",
            "description": "Original transcription with segments array",
            "required": ["segments"]
        },
        "block_to_segment_map": {
            "type": "object",
            "description": "Optional pre-computed mapping from prepare-blocks"
        },
        "config": {
            "type": "object",
            "description": "Configuration options",
            "properties": {
                "padding_before_ms": {
                    "type": "integer",
                    "default": 90,
                    "minimum": 0,
                    "maximum": 500,
                    "description": "Padding before each cut in milliseconds"
                },
                "padding_after_ms": {
                    "type": "integer",
                    "default": 90,
                    "minimum": 0,
                    "maximum": 500,
                    "description": "Padding after each cut in milliseconds"
                },
                "merge_threshold_ms": {
                    "type": "integer",
                    "default": 100,
                    "minimum": 0,
                    "maximum": 1000,
                    "description": "Merge cuts closer than this threshold"
                },
                "video_duration": {
                    "type": "number",
                    "description": "Optional video duration for final cut"
                },
                "generate_cuts": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to generate FFmpeg cuts"
                }
            }
        },
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["gemini_output", "original_transcription"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=True)
def map_timestamps(job_id, data):
    """
    Map Gemini XML output to actual timestamps.

    This endpoint takes the XML-based decisions from Gemini and maps them
    to actual video timestamps using word-level alignment from the original
    Whisper transcription.

    Args:
        job_id: Job ID assigned by queue_task_wrapper
        data: Request data containing:
            - gemini_output: Array of blocks with blockID and outputXML
            - original_transcription: Original transcription with segments
            - block_to_segment_map: Optional pre-computed mapping
            - config: Configuration options

    Returns:
        Tuple of (response_data, endpoint_string, status_code)
    """
    logger.info(f"Job {job_id}: Mapping Gemini output to timestamps")

    try:
        gemini_output = data['gemini_output']
        original_transcription = data['original_transcription']
        block_to_segment_map = data.get('block_to_segment_map')
        config = data.get('config', {})

        if not gemini_output:
            return {
                "error": "Empty gemini_output",
                "segments": [],
                "cuts": []
            }, "/v1/autoedit/map-timestamps", 400

        if not original_transcription.get('segments'):
            return {
                "error": "No segments in original_transcription",
                "segments": [],
                "cuts": []
            }, "/v1/autoedit/map-timestamps", 400

        # Map to timestamps
        mapping_result = map_gemini_output_to_timestamps(
            gemini_blocks=gemini_output,
            original_transcription=original_transcription,
            block_to_segment_map=block_to_segment_map
        )

        logger.info(f"Job {job_id}: Mapped {len(mapping_result['segments'])} segments")

        # Generate cuts if requested
        cuts = []
        if config.get('generate_cuts', True):
            padding_before = config.get('padding_before_ms', 90)
            padding_after = config.get('padding_after_ms', 90)
            merge_threshold = config.get('merge_threshold_ms', 100)
            video_duration = config.get('video_duration')

            cuts = generate_cuts_from_mapped_segments(
                mapped_segments=mapping_result['segments'],
                video_duration=video_duration,
                padding_before_ms=padding_before,
                padding_after_ms=padding_after,
                merge_threshold_ms=merge_threshold
            )

            logger.info(f"Job {job_id}: Generated {len(cuts)} cuts")

        result = {
            "segments": mapping_result['segments'],
            "summary": mapping_result['summary'],
            "cuts": cuts
        }

        return result, "/v1/autoedit/map-timestamps", 200

    except Exception as e:
        error_msg = f"Timestamp mapping failed: {str(e)}"
        logger.error(f"Job {job_id}: {error_msg}")
        import traceback
        logger.error(traceback.format_exc())
        return {"error": error_msg, "segments": [], "cuts": []}, "/v1/autoedit/map-timestamps", 500
