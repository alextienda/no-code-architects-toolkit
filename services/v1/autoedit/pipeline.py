# Copyright (c) 2025
# AutoEdit Pipeline Service
# Orchestrates the complete AutoEdit workflow (Ruta A - Automatic)

import os
import re
import json
import logging
import requests
from typing import List, Dict, Any, Optional, Tuple
from datetime import timedelta

from services.v1.autoedit.analyze_edit import validate_xml_tags, repair_xml_tags

logger = logging.getLogger(__name__)

# =============================================================================
# DEFAULT CONFIGURATION
# =============================================================================
DEFAULT_CONFIG = {
    "padding_before_ms": 90,
    "padding_after_ms": 90,
    "max_block_duration_ms": 60000,
    "gemini_model": "gemini-2.5-pro",
    "gemini_temperature": 0.0,
    "filter_audio_tags": True,
    "gcp_project_id": "autoedit-at",
    "gcp_location": "us-central1"
}

# Audio tags that ElevenLabs adds but aren't real words
AUDIO_TAGS_PATTERN = re.compile(r'\([^)]*(?:fondo|ruido|voz|voces|música|risas|aplausos|silencio|pausa|grita|ríe|llora|suspira|tose)[^)]*\)', re.IGNORECASE)


# =============================================================================
# STEP 1: Transcription with ElevenLabs
# =============================================================================
def transcribe_with_elevenlabs(audio_url: str, api_key: str) -> Dict[str, Any]:
    """
    Transcribe audio using ElevenLabs API with word-level timestamps.

    Args:
        audio_url: URL or local path to audio/video file
        api_key: ElevenLabs API key

    Returns:
        ElevenLabs response with words and timestamps
    """
    logger.info(f"Transcribing with ElevenLabs: {audio_url[:100]}...")

    import tempfile
    import urllib.parse

    # Determine local path based on URL type
    if audio_url.startswith("gs://"):
        # GCS URL - download using GCS client
        from google.cloud import storage

        parts = audio_url.replace("gs://", "").split("/", 1)
        bucket_name = parts[0]
        object_name = parts[1]

        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)

        local_path = f"/tmp/{object_name.split('/')[-1]}"
        blob.download_to_filename(local_path)
        logger.info(f"Downloaded from GCS to: {local_path}")

    elif audio_url.startswith("http://") or audio_url.startswith("https://"):
        # HTTP(S) URL - download using requests
        logger.info("Downloading video from HTTP URL...")

        # Extract filename from URL (remove query params)
        parsed = urllib.parse.urlparse(audio_url)
        filename = parsed.path.split('/')[-1] or "video.mp4"

        local_path = f"/tmp/{filename}"

        response = requests.get(audio_url, stream=True, timeout=300)
        response.raise_for_status()

        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"Downloaded from HTTP to: {local_path}")
    else:
        # Assume local path
        local_path = audio_url

    # Call ElevenLabs API
    url = "https://api.elevenlabs.io/v1/speech-to-text"
    headers = {"xi-api-key": api_key}

    with open(local_path, "rb") as f:
        files = {"file": f}
        data = {
            "model_id": "scribe_v1",
            "timestamps_granularity": "word",
            "tag_audio_events": "true",
            "diarize": "true"
        }

        response = requests.post(url, headers=headers, files=files, data=data, timeout=300)

    if response.status_code != 200:
        raise Exception(f"ElevenLabs error: {response.status_code} - {response.text}")

    result = response.json()
    word_count = len(result.get("words", []))
    logger.info(f"Transcription successful: {word_count} words")

    return result


# =============================================================================
# STEP 2: Transform to internal format
# =============================================================================
def transform_to_internal_format(elevenlabs_result: Dict[str, Any], filter_audio_tags: bool = True) -> List[Dict[str, Any]]:
    """
    Transform ElevenLabs output to internal transcript format.

    Args:
        elevenlabs_result: Raw ElevenLabs response
        filter_audio_tags: Whether to filter out audio event tags

    Returns:
        List of transcript items with NumID, text, inMs, outMs
    """
    transcript = []
    num_id = 0

    words = elevenlabs_result.get("words", [])

    for word in words:
        text = word.get("text", "").strip()

        # Skip empty
        if not text:
            continue

        # Optionally filter audio tags like (voces de fondo), (risas), etc.
        if filter_audio_tags and AUDIO_TAGS_PATTERN.match(text):
            logger.debug(f"Filtering audio tag: {text}")
            continue

        transcript.append({
            "NumID": num_id,
            "text": text,
            "inMs": int(word["start"] * 1000),
            "outMs": int(word["end"] * 1000),
            "speaker_id": word.get("speaker_id")
        })
        num_id += 1

    logger.info(f"Transformed {len(transcript)} words to internal format")
    return transcript


# =============================================================================
# STEP 3: Prepare blocks for Gemini
# =============================================================================
def prepare_blocks_for_gemini(transcript: List[Dict], max_block_duration_ms: int = 60000) -> Dict[str, Any]:
    """
    Prepare numbered text blocks for Gemini analysis.

    Args:
        transcript: Internal transcript format
        max_block_duration_ms: Maximum duration per block in milliseconds

    Returns:
        Dict with blocks list and formatted_text for Gemini
    """
    if not transcript:
        return {"blocks": [], "formatted_text": ""}

    blocks = []
    current_block_id = 0
    current_text = []
    current_start_ms = transcript[0]["inMs"]

    for word in transcript:
        # Start new block if exceeds max duration
        if word["outMs"] - current_start_ms > max_block_duration_ms and current_text:
            blocks.append({
                "blockID": str(current_block_id),
                "text": " ".join(current_text)
            })
            current_block_id += 1
            current_text = []
            current_start_ms = word["inMs"]

        current_text.append(word["text"])

    # Last block
    if current_text:
        blocks.append({
            "blockID": str(current_block_id),
            "text": " ".join(current_text)
        })

    # Format for Gemini
    formatted_text = "\n".join([f"{b['blockID']}: {b['text']}" for b in blocks])

    logger.info(f"Prepared {len(blocks)} blocks for Gemini")
    return {"blocks": blocks, "formatted_text": formatted_text}


# =============================================================================
# STEP 4: Analyze with Gemini
# =============================================================================
def analyze_with_gemini(
    formatted_text: str,
    access_token: str,
    config: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Call Gemini via Vertex AI to analyze content and mark keep/remove.

    Args:
        formatted_text: Formatted blocks text
        access_token: GCP access token
        config: Configuration with model, temperature, etc.

    Returns:
        List of Gemini analysis results per block
    """
    project_id = config.get("gcp_project_id", DEFAULT_CONFIG["gcp_project_id"])
    location = config.get("gcp_location", DEFAULT_CONFIG["gcp_location"])
    model = config.get("gemini_model", DEFAULT_CONFIG["gemini_model"])
    temperature = config.get("gemini_temperature", DEFAULT_CONFIG["gemini_temperature"])

    # Load system prompt
    prompt_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "infrastructure/prompts/autoedit_cleaner_prompt.txt"
    )

    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read()
    else:
        logger.warning(f"System prompt not found at {prompt_path}, using default")
        system_prompt = "Analiza el texto y marca con <mantener> lo que se debe conservar y <eliminar> lo que se debe quitar."

    # Build request
    url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}/publishers/google/models/{model}:generateContent"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": formatted_text}]
            }
        ],
        "systemInstruction": {
            "parts": [{"text": system_prompt}]
        },
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json"
        }
    }

    logger.info(f"Calling Gemini model: {model}")
    response = requests.post(url, headers=headers, json=body, timeout=120)

    if response.status_code != 200:
        raise Exception(f"Gemini error: {response.status_code} - {response.text}")

    result = response.json()

    # Parse response
    gemini_text = result["candidates"][0]["content"]["parts"][0]["text"]
    gemini_blocks = json.loads(gemini_text)

    logger.info(f"Gemini analyzed {len(gemini_blocks)} blocks")
    return gemini_blocks


# =============================================================================
# STEP 5: Combine Gemini outputs
# =============================================================================
def combine_gemini_outputs(gemini_blocks: List[Dict]) -> str:
    """
    Combine all Gemini outputXML into a single XML string.

    Args:
        gemini_blocks: List of Gemini analysis results

    Returns:
        Combined XML string with single <resultado> root (validated and repaired)
    """
    all_content = []

    for block in gemini_blocks:
        xml = block.get("outputXML", "")
        # Extract content from <resultado> tags
        match = re.search(r'<resultado>(.*?)</resultado>', xml, re.DOTALL)
        if match:
            all_content.append(match.group(1))
        else:
            all_content.append(xml)

    combined = "<resultado>" + "".join(all_content) + "</resultado>"
    logger.info(f"Combined XML length: {len(combined)} chars")

    # Validate and repair the combined XML
    is_valid, errors = validate_xml_tags(combined)
    if not is_valid:
        logger.warning(f"Combined XML has issues: {errors}")
        repaired, repair_count = repair_xml_tags(combined)
        if repair_count > 0:
            logger.info(f"Repaired {repair_count} issues in combined XML")
            combined = repaired

            # Validate again
            is_valid_after, remaining_errors = validate_xml_tags(combined)
            if not is_valid_after:
                logger.error(f"Combined XML still has issues after repair: {remaining_errors}")

    return combined


# =============================================================================
# STEP 6: Process with XML Processor
# =============================================================================
def call_xml_processor(xml_string: str, transcript: List[Dict], nca_url: str, api_key: str) -> Dict[str, Any]:
    """
    Call NCA Toolkit xml-processor endpoint.

    Args:
        xml_string: Combined XML with mantener/eliminar tags
        transcript: Internal transcript format
        nca_url: NCA Toolkit base URL
        api_key: NCA API key

    Returns:
        XML processor result with cortes
    """
    url = f"{nca_url}/v1/transcription/xml-processor"
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    body = {
        "xml_string": xml_string,
        "transcript": transcript
    }

    logger.info(f"Calling xml-processor...")
    response = requests.post(url, headers=headers, json=body, timeout=120)

    if response.status_code != 200:
        raise Exception(f"XML Processor error: {response.status_code} - {response.text}")

    result = response.json().get("response", {})
    cortes = result.get("cortes", [])
    valid_cortes = [c for c in cortes if c.get("inMs") is not None]

    logger.info(f"XML Processor found {len(valid_cortes)} valid cortes out of {len(cortes)}")
    return result


# =============================================================================
# STEP 7: Convert cortes to cuts with padding
# =============================================================================
def cortes_to_cuts(cortes: List[Dict], padding_before_ms: int = 90, padding_after_ms: int = 90) -> List[Dict[str, str]]:
    """
    Convert cortes (inMs/outMs) to cuts (start/end in seconds) with padding.

    Args:
        cortes: List of cortes from xml-processor
        padding_before_ms: Padding to add before each cut
        padding_after_ms: Padding to add after each cut

    Returns:
        List of cuts with start/end as strings
    """
    cuts = []

    for corte in cortes:
        # Skip invalid cortes
        if corte.get("inMs") is None or corte.get("outMs") is None:
            continue

        in_ms = max(0, corte["inMs"] - padding_before_ms)
        out_ms = corte["outMs"] + padding_after_ms

        cuts.append({
            "start": str(in_ms / 1000),
            "end": str(out_ms / 1000)
        })

    logger.info(f"Generated {len(cuts)} cuts with padding -{padding_before_ms}ms / +{padding_after_ms}ms")
    return cuts


# =============================================================================
# STEP 8: Call Video Cut
# =============================================================================
def call_video_cut(video_url: str, cuts: List[Dict], nca_url: str, api_key: str) -> str:
    """
    Call NCA Toolkit video/cut endpoint.

    Args:
        video_url: URL to source video (will be converted to signed URL if gs://)
        cuts: List of cuts with start/end
        nca_url: NCA Toolkit base URL
        api_key: NCA API key

    Returns:
        URL to edited video
    """
    # Convert gs:// to signed URL
    if video_url.startswith("gs://"):
        from google.cloud import storage

        parts = video_url.replace("gs://", "").split("/", 1)
        bucket_name = parts[0]
        object_name = parts[1]

        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)

        video_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(hours=1),
            method="GET"
        )
        logger.info(f"Generated signed URL for video")

    url = f"{nca_url}/v1/video/cut"
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    body = {
        "video_url": video_url,
        "cuts": cuts
    }

    logger.info(f"Calling video/cut with {len(cuts)} cuts...")
    response = requests.post(url, headers=headers, json=body, timeout=600)

    if response.status_code != 200:
        raise Exception(f"Video Cut error: {response.status_code} - {response.text}")

    result = response.json()
    edited_url = result.get("response")

    logger.info(f"Video edited successfully: {edited_url}")
    return edited_url


# =============================================================================
# MAIN PIPELINE FUNCTION
# =============================================================================
def run_autoedit_pipeline(
    video_url: str,
    elevenlabs_api_key: str,
    gcp_access_token: str,
    nca_toolkit_url: str,
    nca_api_key: str,
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Run the complete AutoEdit pipeline (Ruta A - Automatic).

    Args:
        video_url: URL to source video (gs:// or https://)
        elevenlabs_api_key: ElevenLabs API key for transcription
        gcp_access_token: GCP access token for Gemini
        nca_toolkit_url: NCA Toolkit base URL
        nca_api_key: NCA Toolkit API key
        config: Optional configuration overrides

    Returns:
        Dict with pipeline results
    """
    # Merge config with defaults
    cfg = {**DEFAULT_CONFIG, **(config or {})}

    logger.info("=" * 60)
    logger.info("AUTOEDIT PIPELINE - RUTA A (AUTOMATIC)")
    logger.info("=" * 60)
    logger.info(f"Video: {video_url}")
    logger.info(f"Config: {cfg}")

    results = {
        "input_video": video_url,
        "config": cfg,
        "steps": {}
    }

    try:
        # Step 1: Transcription
        elevenlabs_result = transcribe_with_elevenlabs(video_url, elevenlabs_api_key)
        results["steps"]["transcription"] = {
            "status": "success",
            "word_count": len(elevenlabs_result.get("words", []))
        }

        # Step 2: Transform to internal format
        transcript = transform_to_internal_format(
            elevenlabs_result,
            filter_audio_tags=cfg.get("filter_audio_tags", True)
        )
        results["steps"]["transform"] = {
            "status": "success",
            "transcript_items": len(transcript)
        }

        # Step 3: Prepare blocks for Gemini
        gemini_input = prepare_blocks_for_gemini(
            transcript,
            max_block_duration_ms=cfg.get("max_block_duration_ms", 60000)
        )
        results["steps"]["prepare_blocks"] = {
            "status": "success",
            "block_count": len(gemini_input["blocks"])
        }

        # Step 4: Analyze with Gemini
        gemini_blocks = analyze_with_gemini(
            gemini_input["formatted_text"],
            gcp_access_token,
            cfg
        )
        results["steps"]["gemini_analysis"] = {
            "status": "success",
            "blocks_analyzed": len(gemini_blocks)
        }

        # Step 5: Combine XMLs
        xml_string = combine_gemini_outputs(gemini_blocks)
        results["steps"]["combine_xml"] = {
            "status": "success",
            "xml_length": len(xml_string)
        }

        # Step 6: XML Processor
        xml_result = call_xml_processor(xml_string, transcript, nca_toolkit_url, nca_api_key)
        cortes = xml_result.get("cortes", [])
        valid_cortes = [c for c in cortes if c.get("inMs") is not None]
        results["steps"]["xml_processor"] = {
            "status": "success",
            "total_cortes": len(cortes),
            "valid_cortes": len(valid_cortes),
            "skipped_cortes": len(cortes) - len(valid_cortes)
        }

        # Step 7: Convert to cuts with padding
        cuts = cortes_to_cuts(
            cortes,
            padding_before_ms=cfg.get("padding_before_ms", 90),
            padding_after_ms=cfg.get("padding_after_ms", 90)
        )
        results["steps"]["convert_cuts"] = {
            "status": "success",
            "cuts_count": len(cuts)
        }

        if not cuts:
            raise Exception("No valid cuts generated - cannot create edited video")

        # Step 8: Video Cut
        edited_url = call_video_cut(video_url, cuts, nca_toolkit_url, nca_api_key)
        results["steps"]["video_cut"] = {
            "status": "success",
            "output_url": edited_url
        }

        results["status"] = "success"
        results["output_video"] = edited_url
        results["cuts"] = cuts

    except Exception as e:
        logger.error(f"Pipeline error: {str(e)}")
        results["status"] = "error"
        results["error"] = str(e)

    return results
