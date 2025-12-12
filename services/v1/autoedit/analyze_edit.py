# Copyright (c) 2025 Stephen G. Pope
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

"""
Analyze Edit Service for AutoEdit pipeline.

Calls Gemini with the full cleaning/editing prompt to analyze text blocks
and decide what to keep or remove. Output is XML format (<mantener>/<eliminar>).
"""

import os
import json
import logging
import requests
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Path to the prompt file
PROMPT_FILE_PATH = os.path.join(
    os.path.dirname(__file__),
    '..', '..', '..', 'infrastructure', 'prompts', 'autoedit_cleaner_prompt.txt'
)

# Cache the prompt
_cached_prompt = None


def load_cleaner_prompt() -> str:
    """
    Load the cleaner prompt from file.

    Returns:
        The full system prompt string
    """
    global _cached_prompt

    if _cached_prompt is not None:
        return _cached_prompt

    prompt_path = Path(PROMPT_FILE_PATH).resolve()

    if not prompt_path.exists():
        # Try alternative path
        alt_path = Path('/app/infrastructure/prompts/autoedit_cleaner_prompt.txt')
        if alt_path.exists():
            prompt_path = alt_path
        else:
            raise FileNotFoundError(f"Prompt file not found at {prompt_path} or {alt_path}")

    with open(prompt_path, 'r', encoding='utf-8') as f:
        _cached_prompt = f.read()

    logger.info(f"Loaded cleaner prompt ({len(_cached_prompt)} chars)")

    return _cached_prompt


def call_gemini_api(
    prompt: str,
    user_content: str,
    model: str = "gemini-2.0-flash-exp",
    temperature: float = 0.0,
    max_tokens: int = 65536,
    project_id: Optional[str] = None,
    location: str = "us-central1"
) -> Dict[str, Any]:
    """
    Call Gemini API via Vertex AI.

    Args:
        prompt: System prompt (the cleaner instructions)
        user_content: User content (the text blocks to analyze)
        model: Gemini model to use
        temperature: Generation temperature
        max_tokens: Maximum output tokens
        project_id: GCP project ID (uses default if not provided)
        location: GCP region

    Returns:
        Dict with response text and metadata
    """
    import google.auth
    import google.auth.transport.requests

    # Get default project if not specified
    if not project_id:
        project_id = os.environ.get('GCP_PROJECT_ID', 'autoedit-at')

    # Get OAuth2 token
    credentials, _ = google.auth.default()
    auth_req = google.auth.transport.requests.Request()
    credentials.refresh(auth_req)
    access_token = credentials.token

    # Build API URL
    api_url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}/publishers/google/models/{model}:generateContent"

    # Build request body
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt + "\n\n---\n\n" + user_content}
                ]
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json"
        }
    }

    # Make request
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    logger.info(f"Calling Gemini API: {model} at {location}")

    response = requests.post(api_url, headers=headers, json=body, timeout=300)

    if response.status_code != 200:
        logger.error(f"Gemini API error: {response.status_code} - {response.text}")
        raise Exception(f"Gemini API error: {response.status_code}")

    result = response.json()

    # Extract text from response
    try:
        response_text = result['candidates'][0]['content']['parts'][0]['text']
    except (KeyError, IndexError) as e:
        logger.error(f"Failed to extract response text: {str(e)}")
        raise Exception(f"Invalid Gemini response format: {str(e)}")

    return {
        "text": response_text,
        "model": model,
        "finish_reason": result.get('candidates', [{}])[0].get('finishReason', 'unknown'),
        "usage": result.get('usageMetadata', {})
    }


def parse_gemini_xml_response(response_text: str) -> List[Dict[str, Any]]:
    """
    Parse Gemini's JSON response containing XML blocks.

    Args:
        response_text: Raw text from Gemini (should be JSON array)

    Returns:
        List of block dicts with blockID and outputXML
    """
    # Clean potential markdown formatting
    cleaned = response_text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        blocks = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini JSON response: {str(e)}")
        logger.error(f"Response text: {response_text[:500]}...")
        raise

    if not isinstance(blocks, list):
        raise ValueError(f"Expected JSON array, got {type(blocks)}")

    # Validate structure
    for block in blocks:
        if not isinstance(block, dict):
            raise ValueError(f"Expected block dict, got {type(block)}")
        if 'blockID' not in block:
            raise ValueError("Block missing 'blockID'")
        if 'outputXML' not in block:
            raise ValueError("Block missing 'outputXML'")

    return blocks


def analyze_blocks_with_gemini(
    formatted_text: str,
    blocks: List[Dict[str, Any]],
    style: str = "dynamic",
    language: str = "es",
    model: str = "gemini-2.0-flash-exp",
    temperature: float = 0.0
) -> Dict[str, Any]:
    """
    Main function: analyze text blocks with Gemini.

    Args:
        formatted_text: The formatted text (0: text..., 1: text..., etc.)
        blocks: The original block list (for metadata)
        style: Editing style (dynamic, conservative, aggressive)
        language: Language code
        model: Gemini model to use
        temperature: Generation temperature

    Returns:
        Dict with analyzed blocks and metadata
    """
    # Load the system prompt
    system_prompt = load_cleaner_prompt()

    # Optionally adjust prompt based on style
    if style == "conservative":
        system_prompt += "\n\n**NOTA ADICIONAL**: Sé conservador. Solo elimina relleno muy obvio."
    elif style == "aggressive":
        system_prompt += "\n\n**NOTA ADICIONAL**: Sé agresivo. Elimina todo lo que no sea absolutamente esencial."

    logger.info(f"Analyzing {len(blocks)} blocks with Gemini (style: {style})")

    # Call Gemini
    gemini_response = call_gemini_api(
        prompt=system_prompt,
        user_content=formatted_text,
        model=model,
        temperature=temperature
    )

    # Parse response
    analyzed_blocks = parse_gemini_xml_response(gemini_response['text'])

    # Add speaker info from original blocks
    for analyzed in analyzed_blocks:
        block_id = analyzed['blockID']
        # Find matching original block
        original = next((b for b in blocks if b['blockID'] == block_id), None)
        if original:
            analyzed['speaker'] = original.get('speaker', 'UNKNOWN')

    return {
        "blocks": analyzed_blocks,
        "total_blocks": len(analyzed_blocks),
        "model_used": gemini_response['model'],
        "finish_reason": gemini_response['finish_reason'],
        "usage": gemini_response['usage']
    }
