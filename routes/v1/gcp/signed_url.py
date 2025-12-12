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

from flask import Blueprint, request, jsonify
from services.authentication import authenticate
from app_utils import validate_payload
from services.v1.gcp.signed_url import generate_signed_upload_url, generate_signed_download_url
import logging

logger = logging.getLogger(__name__)
v1_gcp_signed_url_bp = Blueprint('v1_gcp_signed_url', __name__)


@v1_gcp_signed_url_bp.route('/v1/gcp/signed-upload-url', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "filename": {
            "type": "string",
            "description": "Name of the file to upload"
        },
        "content_type": {
            "type": "string",
            "description": "MIME type of the file",
            "default": "video/mp4"
        },
        "expiration_minutes": {
            "type": "integer",
            "minimum": 1,
            "maximum": 60,
            "description": "URL expiration time in minutes (1-60)",
            "default": 15
        },
        "folder": {
            "type": "string",
            "description": "Optional folder/prefix for the file path"
        }
    },
    "required": ["filename"],
    "additionalProperties": False
})
def gcp_signed_upload_url_endpoint():
    """
    Generate a signed URL for uploading a file directly to GCS.

    This allows frontend clients to upload files directly to Google Cloud Storage
    without routing through the backend, improving performance and reducing server load.

    Request:
        {
            "filename": "video.mp4",
            "content_type": "video/mp4",  // optional, default: video/mp4
            "expiration_minutes": 15,     // optional, default: 15, max: 60
            "folder": "uploads/user123"   // optional
        }

    Response:
        {
            "upload_url": "https://storage.googleapis.com/...",  // Use PUT to upload
            "public_url": "https://storage.googleapis.com/bucket/path/file",
            "filename": "video.mp4",
            "blob_path": "uploads/user123/video.mp4",
            "bucket": "bucket-name",
            "content_type": "video/mp4",
            "expires_in_minutes": 15,
            "method": "PUT",
            "headers_required": {
                "Content-Type": "video/mp4"
            }
        }

    Frontend Usage:
        1. Call this endpoint to get a signed URL
        2. Use fetch/XMLHttpRequest to PUT the file directly to upload_url
        3. Include Content-Type header matching content_type from response
        4. After upload completes, use public_url to reference the file
    """
    try:
        data = request.get_json()

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

        logger.info(f"Generated signed upload URL for {filename}")
        return jsonify(result), 200

    except ValueError as e:
        logger.error(f"Validation error generating signed URL: {str(e)}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Error generating signed upload URL: {str(e)}")
        return jsonify({"error": str(e)}), 500


@v1_gcp_signed_url_bp.route('/v1/gcp/signed-download-url', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "blob_path": {
            "type": "string",
            "description": "Path to the blob in the bucket"
        },
        "expiration_minutes": {
            "type": "integer",
            "minimum": 1,
            "maximum": 1440,
            "description": "URL expiration time in minutes (1-1440)",
            "default": 60
        }
    },
    "required": ["blob_path"],
    "additionalProperties": False
})
def gcp_signed_download_url_endpoint():
    """
    Generate a signed URL for downloading a file from GCS.

    Request:
        {
            "blob_path": "uploads/user123/video.mp4",
            "expiration_minutes": 60  // optional, default: 60, max: 1440 (24h)
        }

    Response:
        {
            "download_url": "https://storage.googleapis.com/...",
            "blob_path": "uploads/user123/video.mp4",
            "bucket": "bucket-name",
            "expires_in_minutes": 60
        }
    """
    try:
        data = request.get_json()

        blob_path = data.get('blob_path')
        expiration_minutes = data.get('expiration_minutes', 60)

        result = generate_signed_download_url(
            blob_path=blob_path,
            expiration_minutes=expiration_minutes
        )

        logger.info(f"Generated signed download URL for {blob_path}")
        return jsonify(result), 200

    except ValueError as e:
        logger.error(f"Validation error generating signed URL: {str(e)}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Error generating signed download URL: {str(e)}")
        return jsonify({"error": str(e)}), 500
