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

from flask import Blueprint, request
from services.authentication import authenticate
from app_utils import validate_payload, queue_task_wrapper
from services.v1.gcp.signed_url import generate_signed_upload_url, generate_signed_download_url
import logging

logger = logging.getLogger(__name__)
v1_gcp_signed_url_bp = Blueprint('v1_gcp_signed_url', __name__)


@v1_gcp_signed_url_bp.route('/v1/gcp/signed-upload-url', methods=['POST'])
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
    """
    Generate a signed URL for uploading a file directly to GCS.
    """
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


@v1_gcp_signed_url_bp.route('/v1/gcp/signed-download-url', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "blob_path": {"type": "string"},
        "expiration_minutes": {"type": "integer", "minimum": 1, "maximum": 1440}
    },
    "required": ["blob_path"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=True)
def gcp_signed_download_url_endpoint(job_id, data):
    """
    Generate a signed URL for downloading a file from GCS.
    """
    try:
        blob_path = data.get('blob_path')
        expiration_minutes = data.get('expiration_minutes', 60)

        result = generate_signed_download_url(
            blob_path=blob_path,
            expiration_minutes=expiration_minutes
        )

        logger.info(f"Job {job_id}: Generated signed download URL for {blob_path}")
        return result, "/v1/gcp/signed-download-url", 200

    except ValueError as e:
        logger.error(f"Job {job_id}: Validation error - {str(e)}")
        return {"error": str(e)}, "/v1/gcp/signed-download-url", 400
    except Exception as e:
        logger.error(f"Job {job_id}: Error generating signed download URL - {str(e)}")
        return {"error": str(e)}, "/v1/gcp/signed-download-url", 500
