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
AutoEdit Preview API Endpoints (HITL 2)

Provides REST API for preview generation and block modification:
- POST /v1/autoedit/workflow/{id}/preview - Generate low-res preview
- GET /v1/autoedit/workflow/{id}/preview - Get preview + blocks + gaps
- PATCH /v1/autoedit/workflow/{id}/blocks - Modify blocks
- POST /v1/autoedit/workflow/{id}/process - Run unified processor (XML → blocks)
"""

from flask import Blueprint, jsonify, request
from app_utils import validate_payload, queue_task_wrapper
from services.authentication import authenticate
from services.v1.autoedit.workflow import get_workflow_manager, WORKFLOW_STATES
from services.v1.autoedit.preview import (
    generate_preview,
    estimate_preview_time
)
from services.v1.autoedit.blocks import (
    apply_modifications,
    calculate_gaps,
    calculate_stats,
    ensure_block_ids,
    add_preview_positions
)
import logging

v1_autoedit_preview_api_bp = Blueprint('v1_autoedit_preview_api', __name__)
logger = logging.getLogger(__name__)


# =============================================================================
# PROCESSING: XML → BLOCKS
# =============================================================================

@v1_autoedit_preview_api_bp.route('/v1/autoedit/workflow/<workflow_id>/process', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "config": {
            "type": "object",
            "properties": {
                "padding_before_ms": {"type": "number", "minimum": 0, "maximum": 500},
                "padding_after_ms": {"type": "number", "minimum": 0, "maximum": 500},
                "silence_threshold_ms": {"type": "number", "minimum": 0, "maximum": 500},
                "merge_threshold_ms": {"type": "number", "minimum": 0, "maximum": 1000}
            }
        }
    },
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def process_to_blocks(job_id, data):
    """Process approved XML to blocks with timestamps.

    Uses the unified-processor to map XML decisions to timestamps
    via neighbor matching.

    Request body:
        {
            "config": {
                "padding_before_ms": 90,
                "padding_after_ms": 130,
                "silence_threshold_ms": 50,
                "merge_threshold_ms": 100
            }
        }

    Returns:
        blocks[] with timestamps and gaps[]
    """
    workflow_id = request.view_args.get('workflow_id')
    config = data.get('config', {})

    logger.info(f"Processing workflow {workflow_id} to blocks")

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return {"error": "Workflow not found", "workflow_id": workflow_id}, "/v1/autoedit/workflow/process", 404

        # Check workflow state
        if workflow["status"] not in ["xml_approved", "pending_review_1"]:
            return {
                "error": f"Cannot process. Workflow status is '{workflow['status']}'. Expected 'xml_approved'.",
                "workflow_id": workflow_id
            }, "/v1/autoedit/workflow/process", 400

        # Get the XML to process (user-modified or original)
        xml_string = workflow.get("user_xml") or workflow.get("gemini_xml")
        if not xml_string:
            return {"error": "No XML to process", "workflow_id": workflow_id}, "/v1/autoedit/workflow/process", 400

        # Get transcript
        transcript = workflow.get("transcript_internal")
        if not transcript:
            return {"error": "No transcript available", "workflow_id": workflow_id}, "/v1/autoedit/workflow/process", 400

        # Call unified processor (internal or via API)
        # For now, we'll call the internal endpoint
        import requests
        import os

        nca_url = os.environ.get("NCA_TOOLKIT_URL", "http://localhost:8080")
        api_key = os.environ.get("NCA_API_KEY", os.environ.get("API_KEY", ""))

        processor_payload = {
            "xml_string": xml_string,
            "transcript": transcript,
            "config": {
                "padding_before_ms": config.get("padding_before_ms", 90),
                "padding_after_ms": config.get("padding_after_ms", 130),
                "silence_threshold_ms": config.get("silence_threshold_ms", 50),
                "merge_threshold_ms": config.get("merge_threshold_ms", 100)
            }
        }

        # If we have the original ElevenLabs transcription XML, include it
        if workflow.get("transcript"):
            # Convert ElevenLabs format to input_transcription if needed
            processor_payload["input_transcription"] = _build_input_transcription_xml(workflow.get("transcript"))

        response = requests.post(
            f"{nca_url}/v1/transcription/unified-processor",
            json=processor_payload,
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            timeout=120
        )

        if response.status_code != 200:
            logger.error(f"Unified processor failed: {response.text}")
            return {
                "error": f"Processing failed: {response.text}",
                "workflow_id": workflow_id
            }, "/v1/autoedit/workflow/process", 500

        result = response.json()
        blocks = result.get("response", {}).get("blocks", result.get("blocks", []))

        if not blocks:
            return {
                "error": "No blocks returned from processor",
                "workflow_id": workflow_id
            }, "/v1/autoedit/workflow/process", 500

        # Ensure blocks have IDs
        blocks = ensure_block_ids(blocks)

        # Get video duration from transcript or estimate
        video_duration_ms = _estimate_video_duration(transcript)

        # Calculate gaps
        gaps = calculate_gaps(blocks, video_duration_ms, transcript)

        # Calculate stats
        stats = calculate_stats(blocks, video_duration_ms)

        # Store in workflow
        manager.set_blocks(workflow_id, blocks, gaps, stats)

        logger.info(f"Processed workflow {workflow_id}: {len(blocks)} blocks, {len(gaps)} gaps")

        return {
            "workflow_id": workflow_id,
            "status": "generating_preview",
            "blocks": blocks,
            "gaps": gaps,
            "stats": stats,
            "message": "Blocks ready. Generate preview to continue."
        }, "/v1/autoedit/workflow/process", 200

    except Exception as e:
        logger.error(f"Error processing workflow {workflow_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {"error": str(e), "workflow_id": workflow_id}, "/v1/autoedit/workflow/process", 500


def _build_input_transcription_xml(elevenlabs_transcript):
    """Build input transcription XML from ElevenLabs format."""
    # This is a simplified version - the actual implementation
    # should match the expected format of the unified processor
    parts = []
    for word in elevenlabs_transcript:
        text = word.get("text", "")
        start = int(word.get("start", 0) * 1000)
        end = int(word.get("end", 0) * 1000)
        parts.append(f'<pt in="{start}" out="{end}">{text}</pt>')
    return f'<transcription>{"".join(parts)}</transcription>'


def _estimate_video_duration(transcript):
    """Estimate video duration from transcript."""
    if not transcript:
        return 0
    max_out = 0
    for word in transcript:
        out_ms = word.get("outMs", word.get("end", 0) * 1000)
        if out_ms > max_out:
            max_out = out_ms
    return int(max_out)


# =============================================================================
# HITL 2: PREVIEW GENERATION
# =============================================================================

@v1_autoedit_preview_api_bp.route('/v1/autoedit/workflow/<workflow_id>/preview', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "quality": {"type": "string", "enum": ["480p", "720p"]},
        "fade_duration": {"type": "number", "minimum": 0.01, "maximum": 0.5}
    },
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def generate_preview_endpoint(job_id, data):
    """Generate a low-res preview video.

    Request body:
        {
            "quality": "480p",
            "fade_duration": 0.025
        }

    Returns:
        {
            "preview_url": "https://...",
            "blocks": [...],
            "gaps": [...],
            "stats": {...}
        }
    """
    workflow_id = request.view_args.get('workflow_id')
    quality = data.get('quality', '480p')
    fade_duration = data.get('fade_duration', 0.025)

    logger.info(f"Generating preview for workflow {workflow_id}")

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return {"error": "Workflow not found", "workflow_id": workflow_id}, "/v1/autoedit/workflow/preview", 404

        # Check workflow state
        valid_states = ["generating_preview", "pending_review_2", "modifying_blocks", "regenerating_preview"]
        if workflow["status"] not in valid_states:
            return {
                "error": f"Cannot generate preview. Status is '{workflow['status']}'. Expected one of: {valid_states}",
                "workflow_id": workflow_id
            }, "/v1/autoedit/workflow/preview", 400

        # Get blocks
        blocks = workflow.get("blocks")
        if not blocks:
            return {"error": "No blocks available. Run /process first.", "workflow_id": workflow_id}, "/v1/autoedit/workflow/preview", 400

        # Update status to generating
        manager.set_status(workflow_id, "generating_preview")

        # Get video duration
        video_duration_ms = workflow.get("stats", {}).get("original_duration_ms")
        if not video_duration_ms:
            video_duration_ms = _estimate_video_duration(workflow.get("transcript_internal", []))

        # Generate preview
        result = generate_preview(
            workflow_id=workflow_id,
            video_url=workflow["video_url"],
            blocks=blocks,
            video_duration_ms=video_duration_ms,
            transcript_words=workflow.get("transcript_internal"),
            quality=quality,
            fade_duration=fade_duration
        )

        # Update workflow with preview
        manager.set_preview(workflow_id, result["preview_url"], result["preview_duration_ms"])
        manager.update(workflow_id, {
            "blocks": result["blocks"],  # Now with preview_inMs
            "gaps": result["gaps"]
        })

        logger.info(f"Preview generated for workflow {workflow_id}: {result['preview_url']}")

        return {
            "workflow_id": workflow_id,
            "status": "pending_review_2",
            **result,
            "message": "Preview ready. Review and approve or modify blocks."
        }, "/v1/autoedit/workflow/preview", 200

    except Exception as e:
        logger.error(f"Error generating preview for {workflow_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        manager.set_status(workflow_id, "error", error=str(e))
        return {"error": str(e), "workflow_id": workflow_id}, "/v1/autoedit/workflow/preview", 500


@v1_autoedit_preview_api_bp.route('/v1/autoedit/workflow/<workflow_id>/preview', methods=['GET'])
@authenticate
def get_preview(workflow_id):
    """Get the current preview and block data.

    Returns:
        {
            "preview_url": "https://...",
            "blocks": [...],
            "gaps": [...],
            "stats": {...}
        }
    """
    logger.info(f"Getting preview for workflow {workflow_id}")

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return jsonify({
                "error": "Workflow not found",
                "workflow_id": workflow_id
            }), 404

        # Check if preview is available
        if not workflow.get("preview_url"):
            return jsonify({
                "error": "No preview available. Generate preview first via POST.",
                "workflow_id": workflow_id,
                "status": workflow["status"]
            }), 400

        return jsonify({
            "workflow_id": workflow_id,
            "status": workflow["status"],
            "preview_url": workflow.get("preview_url"),
            "preview_duration_ms": workflow.get("preview_duration_ms"),
            "blocks": workflow.get("blocks", []),
            "gaps": workflow.get("gaps", []),
            "video_duration_ms": workflow.get("stats", {}).get("original_duration_ms"),
            "stats": workflow.get("stats", {})
        }), 200

    except Exception as e:
        logger.error(f"Error getting preview for {workflow_id}: {e}")
        return jsonify({"error": str(e), "workflow_id": workflow_id}), 500


# =============================================================================
# HITL 2: BLOCK MODIFICATION
# =============================================================================

@v1_autoedit_preview_api_bp.route('/v1/autoedit/workflow/<workflow_id>/blocks', methods=['PATCH'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "modifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["adjust", "split", "merge", "delete", "restore_gap"]
                    },
                    "block_id": {"type": "string"},
                    "block_ids": {"type": "array", "items": {"type": "string"}},
                    "gap_id": {"type": "string"},
                    "gap_index": {"type": "integer", "minimum": 0},
                    "new_inMs": {"type": "integer", "minimum": 0},
                    "new_outMs": {"type": "integer", "minimum": 0},
                    "split_at_ms": {"type": "integer", "minimum": 0}
                },
                "required": ["action"]
            },
            "minItems": 1
        }
    },
    "required": ["modifications"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=True)
def modify_blocks_endpoint(job_id, data):
    """Modify blocks (adjust, split, merge, delete, restore gap).

    Request body:
        {
            "modifications": [
                {"action": "adjust", "block_id": "b1", "new_inMs": 300, "new_outMs": 5800},
                {"action": "split", "block_id": "b2", "split_at_ms": 3000},
                {"action": "merge", "block_ids": ["b3", "b4"]},
                {"action": "delete", "block_id": "b5"},
                {"action": "restore_gap", "gap_index": 2}
            ]
        }

    Returns:
        Updated blocks and gaps, with needs_preview_regeneration flag
    """
    workflow_id = request.view_args.get('workflow_id')
    modifications = data.get('modifications', [])

    logger.info(f"Modifying blocks for workflow {workflow_id}: {len(modifications)} modifications")
    endpoint = f"/v1/autoedit/workflow/{workflow_id}/blocks"

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return {
                "error": "Workflow not found",
                "workflow_id": workflow_id
            }, endpoint, 404

        # Check workflow state
        valid_states = ["pending_review_2", "modifying_blocks", "regenerating_preview"]
        if workflow["status"] not in valid_states:
            return {
                "error": f"Cannot modify blocks. Status is '{workflow['status']}'. Expected one of: {valid_states}",
                "workflow_id": workflow_id
            }, endpoint, 400

        blocks = workflow.get("blocks", [])
        gaps = workflow.get("gaps", [])

        if not blocks:
            return {
                "error": "No blocks available",
                "workflow_id": workflow_id
            }, endpoint, 400

        # Apply modifications
        updated_blocks, updated_gaps, errors = apply_modifications(blocks, gaps, modifications)

        if errors:
            logger.warning(f"Modification errors for {workflow_id}: {errors}")

        # Recalculate gaps if any blocks were modified
        video_duration_ms = workflow.get("stats", {}).get("original_duration_ms", 0)
        if not updated_gaps or len(errors) < len(modifications):
            updated_gaps = calculate_gaps(
                updated_blocks,
                video_duration_ms,
                workflow.get("transcript_internal")
            )

        # Update workflow
        manager.update(workflow_id, {
            "blocks": updated_blocks,
            "gaps": updated_gaps,
            "status": "modifying_blocks"
        })

        # Recalculate stats
        stats = calculate_stats(updated_blocks, video_duration_ms)

        return {
            "workflow_id": workflow_id,
            "blocks": updated_blocks,
            "gaps": updated_gaps,
            "stats": stats,
            "needs_preview_regeneration": True,
            "errors": errors if errors else None,
            "message": "Blocks modified. Regenerate preview to see changes."
        }, endpoint, 200

    except Exception as e:
        logger.error(f"Error modifying blocks for {workflow_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {"error": str(e), "workflow_id": workflow_id}, endpoint, 500
