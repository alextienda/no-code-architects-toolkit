# Copyright (c) 2025 Stephen G. Pope
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

"""
Analyze Edit Endpoint for AutoEdit pipeline.

Calls Gemini with the full cleaning/editing prompt to analyze text blocks
and decide what to keep (<mantener>) or remove (<eliminar>).
"""

from flask import Blueprint
from app_utils import validate_payload, queue_task_wrapper
from services.authentication import authenticate
from services.v1.autoedit.analyze_edit import analyze_blocks_with_gemini
import logging

v1_autoedit_analyze_edit_bp = Blueprint('v1_autoedit_analyze_edit', __name__)
logger = logging.getLogger(__name__)


@v1_autoedit_analyze_edit_bp.route('/v1/autoedit/analyze-edit', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "text_blocks": {
            "type": "array",
            "description": "Array of text blocks to analyze",
            "items": {
                "type": "object",
                "properties": {
                    "blockID": {"type": "string"},
                    "speaker": {"type": "string"},
                    "text": {"type": "string"}
                },
                "required": ["blockID", "text"]
            }
        },
        "formatted_text": {
            "type": "string",
            "description": "Pre-formatted text (0: text..., 1: text...) - alternative to text_blocks"
        },
        "config": {
            "type": "object",
            "description": "Configuration options",
            "properties": {
                "language": {
                    "type": "string",
                    "default": "es",
                    "description": "Language code"
                },
                "style": {
                    "type": "string",
                    "enum": ["dynamic", "conservative", "aggressive"],
                    "default": "dynamic",
                    "description": "Editing style"
                },
                "model": {
                    "type": "string",
                    "default": "gemini-2.0-flash-exp",
                    "description": "Gemini model to use"
                },
                "temperature": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.0,
                    "description": "Generation temperature"
                }
            }
        },
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def analyze_edit(job_id, data):
    """
    Analyze text blocks with Gemini to decide keep/remove.

    This endpoint sends the text blocks to Gemini with the full ~4000 word
    cleaning prompt based on storytelling and audience psychology.
    Output is XML format with <mantener> and <eliminar> tags.

    Args:
        job_id: Job ID assigned by queue_task_wrapper
        data: Request data containing:
            - text_blocks: Array of block dicts with blockID, speaker, text
            - formatted_text: Alternative pre-formatted string
            - config: Configuration options (language, style, model, temperature)

    Returns:
        Tuple of (response_data, endpoint_string, status_code)
    """
    logger.info(f"Job {job_id}: Starting Gemini analysis for editing")

    try:
        text_blocks = data.get('text_blocks', [])
        formatted_text = data.get('formatted_text', '')
        config = data.get('config', {})

        # Extract config options
        language = config.get('language', 'es')
        style = config.get('style', 'dynamic')
        model = config.get('model', 'gemini-2.0-flash-exp')
        temperature = config.get('temperature', 0.0)

        # Build formatted text if not provided
        if not formatted_text and text_blocks:
            lines = []
            for block in text_blocks:
                block_id = block['blockID']
                text = block['text']
                lines.append(f"{block_id}: {text}")
            formatted_text = '\n'.join(lines)

        if not formatted_text:
            return {
                "error": "Either text_blocks or formatted_text must be provided",
                "blocks": []
            }, "/v1/autoedit/analyze-edit", 400

        # Count blocks for logging
        num_blocks = len(text_blocks) if text_blocks else formatted_text.count('\n') + 1

        logger.info(f"Job {job_id}: Analyzing {num_blocks} blocks with style '{style}'")

        # Call Gemini
        result = analyze_blocks_with_gemini(
            formatted_text=formatted_text,
            blocks=text_blocks,
            style=style,
            language=language,
            model=model,
            temperature=temperature
        )

        logger.info(f"Job {job_id}: Gemini analysis complete - {result['total_blocks']} blocks processed")

        return result, "/v1/autoedit/analyze-edit", 200

    except Exception as e:
        error_msg = f"Gemini analysis failed: {str(e)}"
        logger.error(f"Job {job_id}: {error_msg}")
        import traceback
        logger.error(traceback.format_exc())
        return {"error": error_msg, "blocks": []}, "/v1/autoedit/analyze-edit", 500
