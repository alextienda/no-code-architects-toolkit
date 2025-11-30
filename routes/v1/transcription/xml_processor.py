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
XML Processor Route
Migrated from Media Processing Gateway - POST /mcp/v2/xml_processor_ms
"""

from flask import Blueprint, request
from app_utils import validate_payload, queue_task_wrapper
from services.authentication import authenticate
from services.transcription_mcp.xml_processor import extract_sections_from_xml
import logging
from datetime import datetime
import json
import re

v1_transcription_xml_bp = Blueprint('v1_transcription_xml', __name__)
logger = logging.getLogger(__name__)

@v1_transcription_xml_bp.route('/v1/transcription/xml-processor', methods=['POST'])
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
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["xml_string", "transcript"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def xml_processor_endpoint(job_id, data):
    """
    Process XML and find segments in transcript with timestamps.
    
    Migrated from Media Processing Gateway POST /mcp/v2/xml_processor_ms
    
    Args:
        job_id: Job ID assigned by queue_task_wrapper
        data: Request data containing:
            - xml_string: XML string with <mantener> tags
            - transcript: Array of transcript items with inMs, outMs, text
    
    Returns:
        Tuple of (response_data, endpoint_string, status_code)
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[{timestamp}] Job {job_id}: Processing XML request")
    
    try:
        # Extract data
        xml_string = data.get('xml_string')
        transcript = data.get('transcript')
        
        # Handle transcript in different formats
        if isinstance(transcript, str):
            # Try to parse as JSON string
            try:
                transcript = json.loads(transcript)
            except json.JSONDecodeError:
                logger.error(f"[{timestamp}] Job {job_id}: Invalid JSON in transcript string")
                return {"error": "Invalid JSON format in transcript", "cortes": [], "status": "error"}, "/v1/transcription/xml-processor", 400
        
        if isinstance(transcript, dict):
            # If it's a dict, try to extract array from common keys
            if "json" in transcript:
                try:
                    transcript = json.loads(transcript["json"])
                except (json.JSONDecodeError, TypeError):
                    logger.error(f"[{timestamp}] Job {job_id}: Invalid JSON in transcript['json']")
                    return {"error": "Invalid JSON format in transcript['json']", "cortes": [], "status": "error"}, "/v1/transcription/xml-processor", 400
            elif "transcript" in transcript:
                transcript = transcript["transcript"]
            elif "data" in transcript:
                transcript = transcript["data"]
            else:
                logger.error(f"[{timestamp}] Job {job_id}: Transcript dict format not recognized")
                return {"error": "Transcript dict format not recognized", "cortes": [], "status": "error"}, "/v1/transcription/xml-processor", 400
        
        if not isinstance(transcript, list):
            logger.error(f"[{timestamp}] Job {job_id}: Transcript must be an array")
            return {"error": "Transcript must be an array", "cortes": [], "status": "error"}, "/v1/transcription/xml-processor", 400
        
        # Validate transcript items
        validated_transcript = []
        for item in transcript:
            if not isinstance(item, dict):
                logger.warning(f"[{timestamp}] Job {job_id}: Skipping invalid transcript item: {item}")
                continue
            
            # Ensure required fields
            if "text" not in item:
                logger.warning(f"[{timestamp}] Job {job_id}: Skipping transcript item without 'text': {item}")
                continue
            
            validated_item = {
                "text": str(item.get("text", "")),
                "inMs": int(item.get("inMs", 0)),
                "outMs": int(item.get("outMs", item.get("inMs", 0) + 100))
            }
            
            # Add optional fields
            if "NumID" in item:
                validated_item["NumID"] = int(item["NumID"])
            
            validated_transcript.append(validated_item)
        
        if not validated_transcript:
            logger.error(f"[{timestamp}] Job {job_id}: No valid transcript items found")
            return {"error": "No valid transcript items found", "cortes": [], "status": "error"}, "/v1/transcription/xml-processor", 400
        
        logger.info(f"[{timestamp}] Job {job_id}: XML length: {len(xml_string)} chars, Transcript items: {len(validated_transcript)}")
        
        # Process XML
        result = extract_sections_from_xml(xml_string, validated_transcript)
        
        logger.info(f"[{timestamp}] Job {job_id}: XML processing completed. Cuts found: {len(result.get('cortes', []))}")
        
        return result, "/v1/transcription/xml-processor", 200
        
    except Exception as e:
        error_msg = f"Error processing XML: {str(e)}"
        logger.error(f"[{timestamp}] Job {job_id}: {error_msg}")
        import traceback
        logger.error(traceback.format_exc())
        return {"error": error_msg, "cortes": [], "status": "error"}, "/v1/transcription/xml-processor", 500

