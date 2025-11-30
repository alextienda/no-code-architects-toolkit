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
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

"""
Transcription Processing Route
Migrated from Media Processing Gateway - POST /procesar
"""

from flask import Blueprint, request
from app_utils import validate_payload, queue_task_wrapper
from services.authentication import authenticate
from services.transcription_mcp.mcp_processor import (
    process_transcription,
    clean_agent_data,
    SILENCE_THRESHOLD,
    PADDING_BEFORE,
    PADDING_AFTER,
    MERGE_THRESHOLD
)
import logging
from datetime import datetime

v1_transcription_process_bp = Blueprint('v1_transcription_process', __name__)
logger = logging.getLogger(__name__)

@v1_transcription_process_bp.route('/v1/transcription/process', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "input_transcription": {"type": "string"},
        "input_agent_data": {
            "oneOf": [
                {"type": "object"},
                {"type": "array"}
            ]
        },
        "config": {
            "type": "object",
            "properties": {
                "silence_threshold": {"type": "integer", "minimum": 0},
                "padding_before": {"type": "integer", "minimum": 0},
                "padding_after": {"type": "integer", "minimum": 0},
                "merge_threshold": {"type": "integer", "minimum": 0}
            }
        },
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["input_transcription", "input_agent_data"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def process_transcription_endpoint(job_id, data):
    """
    Process transcription with timestamps and cuts.
    
    Migrated from Media Processing Gateway POST /procesar
    
    Args:
        job_id: Job ID assigned by queue_task_wrapper
        data: Request data containing:
            - input_transcription: Transcription text in XML format
            - input_agent_data: Agent data with cuts (can be array or dict with "cortes" key)
            - config: Optional configuration (silence_threshold, padding_before, padding_after, merge_threshold)
    
    Returns:
        Tuple of (response_data, endpoint_string, status_code)
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[{timestamp}] Job {job_id}: Processing transcription request")
    
    try:
        # Extract data
        input_transcription = data.get('input_transcription')
        input_agent_data = data.get('input_agent_data')
        config = data.get('config', {})
        
        # Get configuration values
        silence_threshold = config.get('silence_threshold', SILENCE_THRESHOLD)
        padding_before = config.get('padding_before', PADDING_BEFORE)
        padding_after = config.get('padding_after', PADDING_AFTER)
        merge_threshold = config.get('merge_threshold', MERGE_THRESHOLD)
        
        logger.info(f"[{timestamp}] Job {job_id}: Configuration - silence_threshold={silence_threshold}, "
                   f"padding_before={padding_before}, padding_after={padding_after}, merge_threshold={merge_threshold}")
        
        # Normalize input_agent_data (accept both array and dict)
        if isinstance(input_agent_data, list):
            logger.info(f"[{timestamp}] Job {job_id}: input_agent_data is an array, converting to dict format")
            input_agent_data = {"cortes": input_agent_data}
        elif isinstance(input_agent_data, dict):
            if "cortes" not in input_agent_data:
                # If it has cut fields directly, wrap it
                if any(key in input_agent_data for key in ["inMs", "outMs", "text"]):
                    logger.info(f"[{timestamp}] Job {job_id}: input_agent_data is a single cut dict, wrapping in array")
                    input_agent_data = {"cortes": [input_agent_data]}
                else:
                    logger.warning(f"[{timestamp}] Job {job_id}: input_agent_data dict without 'cortes' key, using empty array")
                    input_agent_data = {"cortes": []}
        
        # Clean agent data if it's a string
        if isinstance(input_agent_data, str):
            cleaned = clean_agent_data(input_agent_data)
            if "error" in cleaned:
                logger.error(f"[{timestamp}] Job {job_id}: Error cleaning agent data: {cleaned['error']}")
                return {"error": cleaned["error"]}, "/v1/transcription/process", 400
            input_agent_data = cleaned
        
        # Process transcription
        logger.info(f"[{timestamp}] Job {job_id}: Starting transcription processing")
        final_blocks, token_count = process_transcription(
            transcription_text=input_transcription,
            agent_data=input_agent_data,
            silence_threshold=silence_threshold,
            padding_before=padding_before,
            padding_after=padding_after,
            merge_threshold=merge_threshold
        )
        
        # Return results
        response_data = {
            "success": True,
            "blocks": final_blocks,
            "processed_tokens": token_count,
            "config_used": {
                "silence_threshold": silence_threshold,
                "padding_before": padding_before,
                "padding_after": padding_after,
                "merge_threshold": merge_threshold
            }
        }
        
        logger.info(f"[{timestamp}] Job {job_id}: Processing completed. Blocks generated: {len(final_blocks)}")
        return response_data, "/v1/transcription/process", 200
        
    except Exception as e:
        error_msg = f"Error processing transcription: {str(e)}"
        logger.error(f"[{timestamp}] Job {job_id}: {error_msg}")
        import traceback
        logger.error(traceback.format_exc())
        return {"error": error_msg, "success": False}, "/v1/transcription/process", 500

