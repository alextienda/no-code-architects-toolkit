# Copyright (c) 2025 Stephen G. Pope
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

"""
Prepare Blocks Endpoint for AutoEdit pipeline.

Transforms transcription with speakers into text blocks for Gemini analysis.
Output contains ONLY TEXT (no timestamps) to reduce cognitive load on AI.
"""

from flask import Blueprint
from app_utils import validate_payload, queue_task_wrapper
from services.authentication import authenticate
from services.v1.autoedit.prepare_blocks import prepare_blocks_for_analysis
import logging

v1_autoedit_prepare_blocks_bp = Blueprint('v1_autoedit_prepare_blocks', __name__)
logger = logging.getLogger(__name__)


@v1_autoedit_prepare_blocks_bp.route('/v1/autoedit/prepare-blocks', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "transcription": {
            "type": "object",
            "description": "Full transcription object with segments array",
            "required": ["segments"],
            "properties": {
                "segments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "start": {"type": "number"},
                            "end": {"type": "number"},
                            "text": {"type": "string"},
                            "speaker": {"type": "string"}
                        }
                    }
                }
            }
        },
        "merge_same_speaker": {
            "type": "boolean",
            "default": True,
            "description": "Merge consecutive segments from same speaker"
        },
        "max_block_duration": {
            "type": "number",
            "default": 60.0,
            "minimum": 10.0,
            "maximum": 300.0,
            "description": "Maximum duration for merged blocks (seconds)"
        },
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["transcription"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=True)
def prepare_blocks(job_id, data):
    """
    Prepare transcription segments into text blocks for Gemini.

    This endpoint transforms the speaker-diarized transcription into
    a format suitable for Gemini analysis. The output contains ONLY TEXT
    without timestamps, following the original Make.com architecture.

    Args:
        job_id: Job ID assigned by queue_task_wrapper
        data: Request data containing:
            - transcription: Object with segments array
            - merge_same_speaker: Whether to merge consecutive same-speaker segments
            - max_block_duration: Maximum block duration in seconds

    Returns:
        Tuple of (response_data, endpoint_string, status_code)
    """
    logger.info(f"Job {job_id}: Preparing blocks for Gemini analysis")

    try:
        transcription = data['transcription']
        merge_same_speaker = data.get('merge_same_speaker', True)
        max_block_duration = data.get('max_block_duration', 60.0)

        segments = transcription.get('segments', [])

        if not segments:
            logger.warning(f"Job {job_id}: No segments provided")
            return {
                "error": "No segments found in transcription",
                "blocks": [],
                "formatted_text": ""
            }, "/v1/autoedit/prepare-blocks", 400

        # Prepare blocks
        result = prepare_blocks_for_analysis(
            transcription=transcription,
            merge_same_speaker=merge_same_speaker,
            max_block_duration=max_block_duration
        )

        logger.info(f"Job {job_id}: Prepared {result['total_blocks']} blocks from {result['total_original_segments']} segments")

        return result, "/v1/autoedit/prepare-blocks", 200

    except Exception as e:
        error_msg = f"Failed to prepare blocks: {str(e)}"
        logger.error(f"Job {job_id}: {error_msg}")
        import traceback
        logger.error(traceback.format_exc())
        return {"error": error_msg}, "/v1/autoedit/prepare-blocks", 500
