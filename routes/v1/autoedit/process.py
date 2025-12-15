# Copyright (c) 2025
# AutoEdit Process Endpoint
# Full pipeline for automatic video editing (Ruta A)

from flask import Blueprint
from app_utils import validate_payload, queue_task_wrapper
from services.authentication import authenticate
from services.v1.autoedit.pipeline import run_autoedit_pipeline, DEFAULT_CONFIG
import logging
import os
import subprocess

v1_autoedit_process_bp = Blueprint('v1_autoedit_process', __name__)
logger = logging.getLogger(__name__)

# Schema for the endpoint
PROCESS_SCHEMA = {
    "type": "object",
    "properties": {
        "video_url": {
            "type": "string",
            "description": "URL to source video (gs:// or https://)"
        },
        "config": {
            "type": "object",
            "properties": {
                "padding_before_ms": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 500,
                    "default": 90,
                    "description": "Milliseconds of padding before each cut (default: 90)"
                },
                "padding_after_ms": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 500,
                    "default": 90,
                    "description": "Milliseconds of padding after each cut (default: 90)"
                },
                "max_block_duration_ms": {
                    "type": "integer",
                    "minimum": 10000,
                    "maximum": 300000,
                    "default": 60000,
                    "description": "Maximum duration per block for Gemini analysis (default: 60000ms)"
                },
                "gemini_model": {
                    "type": "string",
                    "enum": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash-exp", "gemini-1.5-flash", "gemini-1.5-pro"],
                    "default": "gemini-2.5-pro",
                    "description": "Gemini model to use for analysis"
                },
                "gemini_temperature": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.0,
                    "description": "Temperature for Gemini (0 = deterministic)"
                },
                "filter_audio_tags": {
                    "type": "boolean",
                    "default": True,
                    "description": "Filter out audio event tags like (voces de fondo), (risas), etc."
                }
            },
            "additionalProperties": False
        },
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["video_url"],
    "additionalProperties": False
}


def get_gcp_access_token() -> str:
    """Get GCP access token via gcloud CLI or ADC."""
    # Try gcloud CLI first
    try:
        # Check if running in Cloud Run (has metadata server)
        if os.environ.get("K_SERVICE"):
            # Running in Cloud Run - use metadata server
            import requests
            response = requests.get(
                "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
                headers={"Metadata-Flavor": "Google"},
                timeout=5
            )
            if response.status_code == 200:
                return response.json()["access_token"]

        # Try ADC
        from google.auth import default
        from google.auth.transport.requests import Request
        credentials, project = default()
        credentials.refresh(Request())
        return credentials.token

    except Exception as e:
        logger.error(f"Failed to get GCP access token: {e}")
        raise Exception(f"Could not obtain GCP access token: {e}")


def get_elevenlabs_api_key() -> str:
    """Get ElevenLabs API key from environment or Secret Manager."""
    # First check environment
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if api_key:
        return api_key.strip()  # Remove any trailing newlines

    # Try Secret Manager
    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        project_id = os.environ.get("GCP_PROJECT_ID", "autoedit-at")
        name = f"projects/{project_id}/secrets/ELEVENLABS_API_KEY/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8").strip()
    except Exception as e:
        logger.error(f"Failed to get ElevenLabs API key: {e}")
        raise Exception("ELEVENLABS_API_KEY not configured")


@v1_autoedit_process_bp.route('/v1/autoedit/process', methods=['POST'])
@authenticate
@validate_payload(PROCESS_SCHEMA)
@queue_task_wrapper(bypass_queue=False)
def autoedit_process(job_id, data):
    """
    Process video with AutoEdit pipeline (Ruta A - Automatic).

    This endpoint orchestrates the complete AutoEdit workflow:
    1. Transcription with ElevenLabs (word-level timestamps)
    2. Transform to internal format
    3. Prepare blocks for Gemini
    4. Analyze with Gemini (keep/remove decisions)
    5. XML Processing to find timestamps
    6. Apply padding and generate cuts
    7. Video cutting and concatenation

    Request body:
    {
        "video_url": "gs://bucket/video.mp4 or https://...",
        "config": {
            "padding_before_ms": 90,      // 0-500, default 90
            "padding_after_ms": 90,       // 0-500, default 90
            "max_block_duration_ms": 60000, // 10000-300000, default 60000
            "gemini_model": "gemini-2.0-flash-exp",
            "gemini_temperature": 0.0,    // 0.0-1.0, default 0.0
            "filter_audio_tags": true     // Filter (voces de fondo), etc.
        },
        "webhook_url": "https://...",     // Optional: for async processing
        "id": "custom-id"                 // Optional: custom job ID
    }

    Returns:
    {
        "status": "success",
        "input_video": "...",
        "output_video": "https://storage.../edited.mp4",
        "config": {...},
        "steps": {...},
        "cuts": [...]
    }
    """
    logger.info(f"Job {job_id}: Starting AutoEdit process")

    video_url = data["video_url"]
    config = data.get("config", {})

    # Merge with defaults
    full_config = {**DEFAULT_CONFIG, **config}

    try:
        # Get credentials
        elevenlabs_api_key = get_elevenlabs_api_key()
        gcp_access_token = get_gcp_access_token()

        # Get NCA Toolkit URL and API key (self-referential)
        nca_toolkit_url = os.environ.get("NCA_TOOLKIT_URL", "https://nca-toolkit-djwypu7xmq-uc.a.run.app")
        nca_api_key = os.environ.get("API_KEY", "")

        logger.info(f"Job {job_id}: Running pipeline with config: {full_config}")

        # Run the pipeline
        result = run_autoedit_pipeline(
            video_url=video_url,
            elevenlabs_api_key=elevenlabs_api_key,
            gcp_access_token=gcp_access_token,
            nca_toolkit_url=nca_toolkit_url,
            nca_api_key=nca_api_key,
            config=full_config
        )

        if result.get("status") == "success":
            logger.info(f"Job {job_id}: Pipeline completed successfully")
            return result, "/v1/autoedit/process", 200
        else:
            logger.error(f"Job {job_id}: Pipeline failed: {result.get('error')}")
            return result, "/v1/autoedit/process", 500

    except Exception as e:
        logger.error(f"Job {job_id}: Error in AutoEdit process: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "status": "error",
            "error": str(e),
            "input_video": video_url,
            "config": full_config
        }, "/v1/autoedit/process", 500
