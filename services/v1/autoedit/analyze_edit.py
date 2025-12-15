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
import re
import requests
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


# =============================================================================
# XML Validation and Repair Functions
# =============================================================================

def validate_xml_tags(xml: str) -> Tuple[bool, List[str]]:
    """
    Validate that all XML tags are properly closed.

    Args:
        xml: XML string to validate

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    # Pattern to find opening tags and their content up to the next tag
    # This catches cases like <eliminar>text</mantener>
    pattern = r'<(mantener|eliminar)>(.*?)</(mantener|eliminar)>'

    for match in re.finditer(pattern, xml, re.DOTALL):
        open_tag = match.group(1)
        close_tag = match.group(3)
        content = match.group(2)[:50]  # First 50 chars for logging

        if open_tag != close_tag:
            errors.append(f"Tag mismatch: <{open_tag}> closed with </{close_tag}> (content: '{content}...')")

    # Also check for unclosed tags
    open_mantener = len(re.findall(r'<mantener>', xml))
    close_mantener = len(re.findall(r'</mantener>', xml))
    open_eliminar = len(re.findall(r'<eliminar>', xml))
    close_eliminar = len(re.findall(r'</eliminar>', xml))

    if open_mantener != close_mantener:
        errors.append(f"Unbalanced <mantener> tags: {open_mantener} open, {close_mantener} close")
    if open_eliminar != close_eliminar:
        errors.append(f"Unbalanced <eliminar> tags: {open_eliminar} open, {close_eliminar} close")

    return len(errors) == 0, errors


def repair_xml_tags(xml: str) -> Tuple[str, int]:
    """
    Repair XML with mismatched tags by ensuring each opening tag
    has a matching closing tag.

    Args:
        xml: XML string with potential tag mismatches

    Returns:
        Tuple of (repaired_xml, number_of_repairs)
    """
    repairs = 0

    # Strategy: Find all tags in order, track state, fix mismatches
    # We'll process character by character to handle this properly

    result = []
    i = 0
    current_tag = None  # Track which tag is currently open

    while i < len(xml):
        # Check for opening tag
        mantener_match = xml[i:].startswith('<mantener>')
        eliminar_match = xml[i:].startswith('<eliminar>')

        if mantener_match:
            if current_tag is not None:
                # Previous tag wasn't closed, close it first
                result.append(f'</{current_tag}>')
                repairs += 1
                logger.warning(f"XML repair: Auto-closed unclosed <{current_tag}> tag")
            current_tag = 'mantener'
            result.append('<mantener>')
            i += len('<mantener>')
            continue

        if eliminar_match:
            if current_tag is not None:
                # Previous tag wasn't closed, close it first
                result.append(f'</{current_tag}>')
                repairs += 1
                logger.warning(f"XML repair: Auto-closed unclosed <{current_tag}> tag")
            current_tag = 'eliminar'
            result.append('<eliminar>')
            i += len('<eliminar>')
            continue

        # Check for closing tags
        close_mantener = xml[i:].startswith('</mantener>')
        close_eliminar = xml[i:].startswith('</eliminar>')

        if close_mantener or close_eliminar:
            expected_close = '</mantener>' if close_mantener else '</eliminar>'
            actual_tag = 'mantener' if close_mantener else 'eliminar'

            if current_tag is None:
                # Closing tag without opening - skip it
                repairs += 1
                logger.warning(f"XML repair: Removed orphan </{actual_tag}> tag")
                i += len(expected_close)
                continue

            if current_tag != actual_tag:
                # Mismatched closing tag - use the correct one
                repairs += 1
                logger.warning(f"XML repair: Changed </{actual_tag}> to </{current_tag}> (was <{current_tag}>...)")
                result.append(f'</{current_tag}>')
            else:
                result.append(expected_close)

            current_tag = None
            i += len(expected_close)
            continue

        # Regular character
        result.append(xml[i])
        i += 1

    # Close any unclosed tag at the end
    if current_tag is not None:
        result.append(f'</{current_tag}>')
        repairs += 1
        logger.warning(f"XML repair: Closed unclosed <{current_tag}> at end of XML")

    return ''.join(result), repairs


def validate_and_repair_block_xml(block: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and repair the outputXML in a block.

    Args:
        block: Block dict with blockID and outputXML

    Returns:
        Block with repaired outputXML and validation metadata
    """
    block_id = block.get('blockID', 'unknown')
    output_xml = block.get('outputXML', '')

    # First validate
    is_valid, errors = validate_xml_tags(output_xml)

    if not is_valid:
        logger.warning(f"Block {block_id} has malformed XML: {errors}")

        # Attempt repair
        repaired_xml, repair_count = repair_xml_tags(output_xml)

        # Validate again
        is_valid_after, remaining_errors = validate_xml_tags(repaired_xml)

        if is_valid_after:
            logger.info(f"Block {block_id}: Successfully repaired {repair_count} XML issues")
            block['outputXML'] = repaired_xml
            block['_xml_repaired'] = True
            block['_xml_repairs'] = repair_count
        else:
            logger.error(f"Block {block_id}: Could not fully repair XML. Remaining errors: {remaining_errors}")
            block['outputXML'] = repaired_xml  # Use partially repaired version
            block['_xml_repaired'] = True
            block['_xml_repairs'] = repair_count
            block['_xml_errors'] = remaining_errors
    else:
        block['_xml_repaired'] = False

    return block

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
    model: str = "gemini-2.5-pro",
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

    # Validate and repair XML tags in each block
    repaired_count = 0
    for i, block in enumerate(blocks):
        blocks[i] = validate_and_repair_block_xml(block)
        if blocks[i].get('_xml_repaired'):
            repaired_count += 1

    if repaired_count > 0:
        logger.info(f"XML validation: Repaired {repaired_count}/{len(blocks)} blocks with malformed XML")

    return blocks


def analyze_blocks_with_gemini(
    formatted_text: str,
    blocks: List[Dict[str, Any]],
    style: str = "dynamic",
    language: str = "es",
    model: str = "gemini-2.5-pro",
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
