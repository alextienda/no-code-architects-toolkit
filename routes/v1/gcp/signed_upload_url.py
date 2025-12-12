# Copyright (c) 2025 Stephen G. Pope
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

import sys
print(f"DEBUG: signed_upload_url.py being imported", file=sys.stderr)

from flask import Blueprint
from services.authentication import authenticate
from app_utils import validate_payload, queue_task_wrapper
from services.v1.gcp.signed_url import generate_signed_upload_url
import logging

logger = logging.getLogger(__name__)
v1_gcp_signed_upload_url_bp = Blueprint('v1_gcp_signed_upload_url', __name__)


@v1_gcp_signed_upload_url_bp.route('/v1/gcp/signed-upload-url', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "filename": {"type": "string"},
        "content_type": {"type": "string"},
        "expiration_minutes": {"type": "integer", "minimum": 1, "maximum": 60},
        "folder": {"type": "string"}
    },
    "required": ["filename"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=True)
def gcp_signed_upload_url_endpoint(job_id, data):
    """Generate a signed URL for uploading a file directly to GCS."""
    try:
        filename = data.get('filename')
        content_type = data.get('content_type', 'video/mp4')
        expiration_minutes = data.get('expiration_minutes', 15)
        folder = data.get('folder')

        result = generate_signed_upload_url(
            filename=filename,
            content_type=content_type,
            expiration_minutes=expiration_minutes,
            folder=folder
        )

        logger.info(f"Job {job_id}: Generated signed upload URL for {filename}")
        return result, "/v1/gcp/signed-upload-url", 200

    except ValueError as e:
        logger.error(f"Job {job_id}: Validation error - {str(e)}")
        return {"error": str(e)}, "/v1/gcp/signed-upload-url", 400
    except Exception as e:
        logger.error(f"Job {job_id}: Error generating signed upload URL - {str(e)}")
        return {"error": str(e)}, "/v1/gcp/signed-upload-url", 500
