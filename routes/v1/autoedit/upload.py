# Copyright (c) 2025 Stephen G. Pope
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

"""
AutoEdit Upload Endpoint
Receives a video URL, uploads it to the dedicated AutoEdit bucket,
and returns a job_id for tracking.
"""

from flask import Blueprint
from app_utils import validate_payload, queue_task_wrapper
from services.authentication import authenticate
from services.file_management import download_file
from google.cloud import storage
from google.oauth2 import service_account
import logging
import os
import uuid
import json

v1_autoedit_upload_bp = Blueprint('v1_autoedit_upload', __name__)
logger = logging.getLogger(__name__)

# AutoEdit configuration
AUTOEDIT_INPUT_BUCKET = "autoedit-input-autoedit-at"
AUTOEDIT_OUTPUT_BUCKET = "nca-toolkit-autoedit"
GCP_PROJECT = "autoedit-at"
WORKFLOW_NAME = "autoedit-aroll-flow"
WORKFLOW_LOCATION = "us-central1"


def get_gcs_client():
    """Get authenticated GCS client."""
    gcp_sa_credentials = os.environ.get('GCP_SA_CREDENTIALS')
    if gcp_sa_credentials:
        try:
            creds_dict = json.loads(gcp_sa_credentials)
            credentials = service_account.Credentials.from_service_account_info(creds_dict)
            return storage.Client(credentials=credentials, project=GCP_PROJECT)
        except Exception as e:
            logger.warning(f"Failed to use GCP_SA_CREDENTIALS: {e}, trying default credentials")
    return storage.Client(project=GCP_PROJECT)


def upload_to_autoedit_bucket(local_path, destination_name):
    """Upload a file to the AutoEdit input bucket."""
    client = get_gcs_client()
    bucket = client.bucket(AUTOEDIT_INPUT_BUCKET)
    blob = bucket.blob(destination_name)
    blob.upload_from_filename(local_path)
    return f"gs://{AUTOEDIT_INPUT_BUCKET}/{destination_name}"


@v1_autoedit_upload_bp.route('/v1/autoedit/upload', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "video_url": {
            "type": "string",
            "format": "uri",
            "description": "URL of the video to process"
        },
        "filename": {
            "type": "string",
            "description": "Optional custom filename (without extension)"
        },
        "language": {
            "type": "string",
            "default": "es",
            "description": "Language for transcription (default: es)"
        },
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["video_url"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=True)
def autoedit_upload(job_id, data):
    """
    Upload a video to the AutoEdit processing bucket.

    The video will automatically trigger the AutoEdit workflow via Eventarc.
    Use /v1/autoedit/status/{job_id} to check processing status.

    Args:
        job_id: Job ID assigned by queue_task_wrapper
        data: Request data containing:
            - video_url: URL of video to process
            - filename: Optional custom filename
            - language: Language for transcription (default: es)

    Returns:
        Tuple of (response_data, endpoint_string, status_code)
    """
    logger.info(f"Job {job_id}: AutoEdit upload request received")

    try:
        video_url = data['video_url']
        custom_filename = data.get('filename')
        language = data.get('language', 'es')

        # Generate unique filename
        unique_id = str(uuid.uuid4())[:8]

        if custom_filename:
            # Sanitize custom filename
            safe_name = "".join(c for c in custom_filename if c.isalnum() or c in "-_")
            destination_name = f"{unique_id}_{safe_name}.mp4"
        else:
            destination_name = f"{unique_id}_autoedit.mp4"

        logger.info(f"Job {job_id}: Downloading video from {video_url}")

        # Download the video
        from config import LOCAL_STORAGE_PATH
        local_path = download_file(video_url, os.path.join(LOCAL_STORAGE_PATH, f"{job_id}_input"))

        # Ensure it has .mp4 extension for the workflow filter
        if not local_path.endswith('.mp4'):
            new_path = local_path + '.mp4'
            os.rename(local_path, new_path)
            local_path = new_path

        logger.info(f"Job {job_id}: Uploading to AutoEdit bucket as {destination_name}")

        # Upload to AutoEdit input bucket
        gs_uri = upload_to_autoedit_bucket(local_path, destination_name)

        # Clean up local file
        os.remove(local_path)

        # The Eventarc trigger will automatically start the workflow
        result = {
            "job_id": destination_name.replace('.mp4', ''),
            "filename": destination_name,
            "input_uri": gs_uri,
            "status": "uploaded",
            "message": "Video uploaded successfully. Workflow will start automatically.",
            "status_endpoint": f"/v1/autoedit/status/{destination_name.replace('.mp4', '')}",
            "estimated_time": "2-10 minutes depending on video length"
        }

        logger.info(f"Job {job_id}: Upload complete. AutoEdit job_id: {destination_name}")
        return result, "/v1/autoedit/upload", 200

    except Exception as e:
        error_msg = f"Error uploading video: {str(e)}"
        logger.error(f"Job {job_id}: {error_msg}")
        import traceback
        logger.error(traceback.format_exc())
        return {"error": error_msg}, "/v1/autoedit/upload", 500
