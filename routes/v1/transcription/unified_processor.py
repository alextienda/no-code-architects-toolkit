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
Unified Processor Route
Migrated from Media Processing Gateway - POST /mcp/v2/unified_processor
Combines transcription processing and XML processing in a single call
"""

from flask import Blueprint, request
from app_utils import validate_payload, queue_task_wrapper
from services.authentication import authenticate
from services.transcription_mcp.mcp_processor import process_transcription, SILENCE_THRESHOLD, PADDING_BEFORE, PADDING_AFTER, MERGE_THRESHOLD
from services.transcription_mcp.xml_processor import extract_sections_from_xml
import logging
from datetime import datetime
import json

v1_transcription_unified_bp = Blueprint('v1_transcription_unified', __name__)
logger = logging.getLogger(__name__)

@v1_transcription_unified_bp.route('/v1/transcription/unified-processor', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "xml_string": {"type": "string"},
        "transcript": {
            "oneOf": [
                {"type": "array"},
                {"type": "object"},
                {"type": "string"}
            ]
        },
        "input_transcription": {"type": "string"},
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
    "required": ["xml_string", "transcript"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def unified_processor_endpoint(job_id, data):
    """
    Unified processor that combines XML processing and transcription processing.
    
    Migrated from Media Processing Gateway POST /mcp/v2/unified_processor
    
    Args:
        job_id: Job ID assigned by queue_task_wrapper
        data: Request data containing:
            - xml_string: XML string with <mantener> tags
            - transcript: Array of transcript items with inMs, outMs, text
            - input_transcription: Optional transcription text in XML format
            - config: Optional configuration
    
    Returns:
        Tuple of (response_data, endpoint_string, status_code)
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[{timestamp}] Job {job_id}: Processing unified request")
    
    try:
        # Extract data
        xml_string = data.get('xml_string')
        transcript = data.get('transcript')
        input_transcription = data.get('input_transcription')
        config = data.get('config', {})
        
        # Handle transcript in different formats (same as xml_processor)
        if isinstance(transcript, str):
            try:
                transcript = json.loads(transcript)
            except json.JSONDecodeError:
                logger.error(f"[{timestamp}] Job {job_id}: Invalid JSON in transcript string")
                return {"error": "Invalid JSON format in transcript", "cortes": [], "status": "error"}, "/v1/transcription/unified-processor", 400
        
        if isinstance(transcript, dict):
            if "json" in transcript:
                try:
                    transcript = json.loads(transcript["json"])
                except (json.JSONDecodeError, TypeError):
                    logger.error(f"[{timestamp}] Job {job_id}: Invalid JSON in transcript['json']")
                    return {"error": "Invalid JSON format in transcript['json']", "cortes": [], "status": "error"}, "/v1/transcription/unified-processor", 400
            elif "transcript" in transcript:
                transcript = transcript["transcript"]
            elif "data" in transcript:
                transcript = transcript["data"]
            else:
                logger.error(f"[{timestamp}] Job {job_id}: Transcript dict format not recognized")
                return {"error": "Transcript dict format not recognized", "cortes": [], "status": "error"}, "/v1/transcription/unified-processor", 400
        
        if not isinstance(transcript, list):
            logger.error(f"[{timestamp}] Job {job_id}: Transcript must be an array")
            return {"error": "Transcript must be an array", "cortes": [], "status": "error"}, "/v1/transcription/unified-processor", 400
        
        # Validate transcript items
        validated_transcript = []
        for item in transcript:
            if not isinstance(item, dict):
                continue
            
            if "text" not in item:
                continue
            
            validated_item = {
                "text": str(item.get("text", "")),
                "inMs": int(item.get("inMs", 0)),
                "outMs": int(item.get("outMs", item.get("inMs", 0) + 100))
            }
            
            if "NumID" in item:
                validated_item["NumID"] = int(item["NumID"])
            
            validated_transcript.append(validated_item)
        
        if not validated_transcript:
            logger.error(f"[{timestamp}] Job {job_id}: No valid transcript items found")
            return {"error": "No valid transcript items found", "cortes": [], "status": "error"}, "/v1/transcription/unified-processor", 400
        
        # Step 1: Process XML to get cuts
        logger.info(f"[{timestamp}] Job {job_id}: Step 1 - Processing XML")
        xml_result = extract_sections_from_xml(xml_string, validated_transcript)
        
        if xml_result.get("status") == "error":
            logger.error(f"[{timestamp}] Job {job_id}: XML processing failed: {xml_result.get('error')}")
            return xml_result, "/v1/transcription/unified-processor", 400
        
        cuts = xml_result.get("cortes", [])
        logger.info(f"[{timestamp}] Job {job_id}: XML processing completed. Cuts found: {len(cuts)}")
        
        # Step 2: If input_transcription is provided, process it with the cuts
        if input_transcription:
            logger.info(f"[{timestamp}] Job {job_id}: Step 2 - Processing transcription with cuts")
            
            # Get configuration
            silence_threshold = config.get('silence_threshold', SILENCE_THRESHOLD)
            padding_before = config.get('padding_before', PADDING_BEFORE)
            padding_after = config.get('padding_after', PADDING_AFTER)
            merge_threshold = config.get('merge_threshold', MERGE_THRESHOLD)
            
            # Convert cuts to agent_data format
            agent_data = {"cortes": cuts}
            
            # Process transcription
            final_blocks, token_count = process_transcription(
                transcription_text=input_transcription,
                agent_data=agent_data,
                silence_threshold=silence_threshold,
                padding_before=padding_before,
                padding_after=padding_after,
                merge_threshold=merge_threshold
            )
            
            logger.info(f"[{timestamp}] Job {job_id}: Transcription processing completed. Blocks generated: {len(final_blocks)}")
            
            # Return combined result
            response_data = {
                "success": True,
                "xml_result": xml_result,
                "blocks": final_blocks,
                "processed_tokens": token_count,
                "config_used": {
                    "silence_threshold": silence_threshold,
                    "padding_before": padding_before,
                    "padding_after": padding_after,
                    "merge_threshold": merge_threshold
                }
            }
            
            return response_data, "/v1/transcription/unified-processor", 200
        else:
            # Only XML processing, return XML result
            logger.info(f"[{timestamp}] Job {job_id}: No input_transcription provided, returning XML result only")
            return xml_result, "/v1/transcription/unified-processor", 200
        
    except Exception as e:
        error_msg = f"Error in unified processing: {str(e)}"
        logger.error(f"[{timestamp}] Job {job_id}: {error_msg}")
        import traceback
        logger.error(traceback.format_exc())
        return {"error": error_msg, "cortes": [], "status": "error"}, "/v1/transcription/unified-processor", 500

