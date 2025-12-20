# Copyright (c) 2025
#
# Context Builder for AutoEdit Multi-Video Projects
#
# Builds progressive context from analyzed videos to inform
# subsequent video analysis with awareness of previous content.

"""
Context Builder Service

Generates contextual summaries from analyzed videos to pass to
the analysis of subsequent videos in a project. This enables:
- Awareness of previously covered topics
- Detection of redundant explanations
- Maintaining narrative continuity
- Better storytelling decisions
- Creator profile personalization

Environment Variables:
    GCP_PROJECT_ID: GCP project for Gemini API
    GCP_LOCATION: GCP region (default: us-central1)
    CREATOR_NAME: Creator's name (default: Alex)
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from config import CREATOR_GLOBAL_PROFILE

logger = logging.getLogger(__name__)

# Configuration
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "autoedit-at")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "us-central1")
MAX_CONTEXT_TOKENS = 2000  # Leave room for current video analysis
MAX_SUMMARY_CHARS = 1500   # Per video summary
MAX_PREVIOUS_SUMMARIES = 10  # If more videos, compress older ones


def get_effective_creator_profile(project_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Get the effective creator profile by merging global profile with project overrides.

    The global profile defines the creator's brand, audience, style, etc.
    The project context can override specific fields for campaign/sponsor purposes.

    Args:
        project_context: Optional project-specific context with overrides

    Returns:
        Merged creator profile
    """
    # Start with global profile
    profile = CREATOR_GLOBAL_PROFILE.copy()

    if not project_context:
        return profile

    # Apply project-level overrides
    if project_context.get("creator_name"):
        profile["name"] = project_context["creator_name"]

    if project_context.get("specific_audience"):
        profile["audience"] = project_context["specific_audience"]

    if project_context.get("tone_override"):
        profile["tone"] = project_context["tone_override"]

    if project_context.get("style_override"):
        profile["style"] = project_context["style_override"]

    # Add project-specific fields
    if project_context.get("sponsor"):
        profile["sponsor"] = project_context["sponsor"]

    if project_context.get("campaign"):
        profile["campaign"] = project_context["campaign"]

    if project_context.get("focus"):
        profile["focus"] = project_context["focus"]

    if project_context.get("call_to_action"):
        profile["call_to_action"] = project_context["call_to_action"]

    if project_context.get("keywords_to_keep"):
        profile["keywords_to_keep"] = project_context["keywords_to_keep"]

    if project_context.get("keywords_to_avoid"):
        profile["keywords_to_avoid"] = project_context["keywords_to_avoid"]

    return profile


def generate_video_summary(
    workflow_id: str,
    transcript_text: str,
    gemini_xml: Optional[str] = None,
    sequence_index: int = 0,
    project_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate a semantic summary of a video after analysis.
    This summary will be used as context for subsequent videos.

    Args:
        workflow_id: The workflow ID
        transcript_text: Full transcript text
        gemini_xml: Optional analyzed XML (to understand what was kept)
        sequence_index: Position in the video sequence (0-based)
        project_context: Optional project-specific context with creator overrides

    Returns:
        Video summary with key points, entities, and narrative function
    """
    import google.auth
    import google.auth.transport.requests
    import requests

    # Get creator profile (global + project overrides)
    profile = get_effective_creator_profile(project_context)
    creator_name = profile.get("name", "Alex")

    # Build creator context section for prompt
    creator_context = f"""PERFIL DEL CREADOR:
- Nombre: {creator_name}
- Brand: {profile.get('brand', 'N/A')}
- Audiencia: {profile.get('audience', 'N/A')}
- Estilo: {profile.get('style', 'N/A')}
- Tono: {profile.get('tone', 'N/A')}"""

    # Add project-specific context if available
    if project_context:
        project_parts = []
        if project_context.get("sponsor"):
            project_parts.append(f"- Sponsor: {project_context['sponsor']}")
        if project_context.get("campaign"):
            project_parts.append(f"- Campaña: {project_context['campaign']}")
        if project_context.get("focus"):
            project_parts.append(f"- Enfoque especial: {project_context['focus']}")
        if project_parts:
            creator_context += "\n\nCONTEXTO DE ESTE PROYECTO:\n" + "\n".join(project_parts)

    # Prepare prompt for summary generation
    prompt = f"""Eres el asistente de edición de {creator_name}.

{creator_context}

Analiza este fragmento de video (parte {sequence_index + 1} de una serie) y genera un resumen estructurado.

IMPORTANTE: Refiere al creador siempre como "{creator_name}", NUNCA como "el orador" o "el hablante".

TRANSCRIPT:
{transcript_text[:4000]}

Responde SOLO con JSON válido, sin markdown ni explicaciones:
{{
    "summary": "Resumen de 1-2 oraciones del contenido principal (usar '{creator_name}' no 'el orador')",
    "key_points": ["punto1", "punto2", "punto3"],
    "entities_mentioned": ["lugar1", "persona1", "concepto1"],
    "topics_covered": ["tema1", "tema2"],
    "narrative_function": "introduction|rising_action|climax|falling_action|resolution|standalone",
    "connects_to_next": "Breve descripción de cómo podría conectar con lo siguiente",
    "emotional_tone": "informativo|entusiasta|reflexivo|humorístico|serio"
}}"""

    try:
        # Get credentials
        credentials, _ = google.auth.default()
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)

        # Call Gemini
        url = f"https://{GCP_LOCATION}-aiplatform.googleapis.com/v1/projects/{GCP_PROJECT_ID}/locations/{GCP_LOCATION}/publishers/google/models/gemini-2.5-flash:generateContent"

        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {credentials.token}",
                "Content-Type": "application/json"
            },
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 1024,
                    "responseMimeType": "application/json"
                }
            },
            timeout=60
        )

        if response.status_code != 200:
            logger.error(f"Gemini error: {response.status_code} - {response.text}")
            return _create_fallback_summary(workflow_id, transcript_text, sequence_index)

        result = response.json()
        summary_text = result["candidates"][0]["content"]["parts"][0]["text"]

        try:
            summary_data = json.loads(summary_text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse Gemini response as JSON")
            return _create_fallback_summary(workflow_id, transcript_text, sequence_index)

        return {
            "workflow_id": workflow_id,
            "sequence_index": sequence_index,
            "created_at": datetime.utcnow().isoformat(),
            **summary_data
        }

    except Exception as e:
        logger.error(f"Error generating video summary: {e}")
        return _create_fallback_summary(workflow_id, transcript_text, sequence_index)


def _create_fallback_summary(
    workflow_id: str,
    transcript_text: str,
    sequence_index: int
) -> Dict[str, Any]:
    """Create a basic fallback summary when Gemini fails."""
    return {
        "workflow_id": workflow_id,
        "sequence_index": sequence_index,
        "summary": transcript_text[:200] + "..." if len(transcript_text) > 200 else transcript_text,
        "key_points": [],
        "entities_mentioned": [],
        "topics_covered": [],
        "narrative_function": "unknown",
        "connects_to_next": "",
        "emotional_tone": "unknown",
        "created_at": datetime.utcnow().isoformat(),
        "_fallback": True
    }


def build_context_for_video(
    project_id: str,
    current_sequence_index: int,
    video_summaries: List[Dict[str, Any]],
    project_context: Optional[Dict[str, Any]] = None
) -> str:
    """
    Build context string from previous video summaries to include
    in the analysis prompt for the current video.

    Args:
        project_id: The project ID
        current_sequence_index: Index of current video (0-based)
        video_summaries: List of summaries from previous videos
        project_context: Optional project-specific context with creator overrides

    Returns:
        Context string to prepend to analysis prompt
    """
    if not video_summaries or current_sequence_index == 0:
        return ""

    # Get creator profile for personalization
    profile = get_effective_creator_profile(project_context)
    creator_name = profile.get("name", "Alex")

    # Filter only previous videos
    previous_summaries = [
        s for s in video_summaries
        if s.get("sequence_index", 0) < current_sequence_index
    ]

    if not previous_summaries:
        return ""

    # Sort by sequence index
    previous_summaries.sort(key=lambda x: x.get("sequence_index", 0))

    # Compress if too many
    if len(previous_summaries) > MAX_PREVIOUS_SUMMARIES:
        # Keep first 2, last 3, compress middle
        first = previous_summaries[:2]
        last = previous_summaries[-3:]
        middle = previous_summaries[2:-3]

        middle_summary = {
            "summary": f"[{len(middle)} videos intermedios cubriendo: " +
                       ", ".join(set(t for s in middle for t in s.get("topics_covered", [])))[:200] + "]",
            "sequence_index": "varios"
        }

        previous_summaries = first + [middle_summary] + last

    # Build context string
    context_parts = [
        "=== CONTEXTO DE VIDEOS ANTERIORES ===",
        f"Este es el video {current_sequence_index + 1} de una serie.",
        ""
    ]

    # Add summaries
    for summary in previous_summaries:
        idx = summary.get("sequence_index", "?")
        if isinstance(idx, int):
            idx += 1

        context_parts.append(f"VIDEO {idx}:")
        context_parts.append(f"  Resumen: {summary.get('summary', 'N/A')[:300]}")

        key_points = summary.get("key_points", [])
        if key_points:
            context_parts.append(f"  Puntos clave: {', '.join(key_points[:5])}")

        connects = summary.get("connects_to_next", "")
        if connects:
            context_parts.append(f"  Conexión: {connects[:150]}")

        context_parts.append("")

    # Add accumulated entities
    all_entities = set()
    for summary in previous_summaries:
        all_entities.update(summary.get("entities_mentioned", []))

    if all_entities:
        context_parts.append("ENTIDADES YA MENCIONADAS (evitar redundancia):")
        context_parts.append(f"  {', '.join(list(all_entities)[:20])}")
        context_parts.append("")

    # Add covered topics
    all_topics = set()
    for summary in previous_summaries:
        all_topics.update(summary.get("topics_covered", []))
        all_topics.update(summary.get("key_points", []))

    if all_topics:
        context_parts.append("TEMAS YA CUBIERTOS:")
        context_parts.append(f"  {', '.join(list(all_topics)[:15])}")
        context_parts.append("")

    # Add instructions with creator name
    context_parts.extend([
        "INSTRUCCIONES PARA ESTE VIDEO:",
        "1. El espectador ya vio los videos anteriores",
        "2. Evita mantener contenido que repita exactamente lo ya dicho",
        f"3. Si {creator_name} repite un concepto ya explicado, considéralo como candidato a eliminar",
        "4. Mantén transiciones que conecten naturalmente con lo anterior",
        f"5. IMPORTANTE: Refiere al creador siempre como '{creator_name}', nunca como 'el orador' o 'el hablante'",
        "=== FIN CONTEXTO ===",
        ""
    ])

    context = "\n".join(context_parts)

    # Truncate if too long
    max_chars = MAX_CONTEXT_TOKENS * 4  # ~4 chars per token
    if len(context) > max_chars:
        context = context[:max_chars] + "\n[...contexto truncado...]\n=== FIN CONTEXTO ===\n"

    return context


def get_accumulated_context(
    video_summaries: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Get accumulated context from all analyzed videos.

    Args:
        video_summaries: List of all video summaries

    Returns:
        Accumulated context with all topics, entities, etc.
    """
    if not video_summaries:
        return {
            "covered_topics": [],
            "entities_introduced": [],
            "narrative_functions": {},
            "total_videos": 0
        }

    all_topics = set()
    all_entities = set()
    narrative_functions = {}

    for summary in video_summaries:
        all_topics.update(summary.get("topics_covered", []))
        all_topics.update(summary.get("key_points", []))
        all_entities.update(summary.get("entities_mentioned", []))

        func = summary.get("narrative_function", "unknown")
        narrative_functions[func] = narrative_functions.get(func, 0) + 1

    return {
        "covered_topics": list(all_topics),
        "entities_introduced": list(all_entities),
        "narrative_functions": narrative_functions,
        "total_videos": len(video_summaries)
    }


# ============================================================================
# Storage Functions
# ============================================================================

def save_video_summary(
    project_id: str,
    workflow_id: str,
    summary: Dict[str, Any],
    bucket_name: Optional[str] = None
) -> str:
    """
    Save video summary to GCS.

    Args:
        project_id: The project ID
        workflow_id: The workflow ID
        summary: The summary data
        bucket_name: GCS bucket name

    Returns:
        GCS path where summary was saved
    """
    from google.cloud import storage

    bucket_name = bucket_name or os.environ.get("GCP_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("GCP_BUCKET_NAME required")

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    path = f"projects/{project_id}/context/video_summaries/{workflow_id}.json"
    blob = bucket.blob(path)

    blob.upload_from_string(
        json.dumps(summary, ensure_ascii=False),
        content_type="application/json"
    )

    logger.info(f"Saved video summary to gs://{bucket_name}/{path}")
    return f"gs://{bucket_name}/{path}"


def load_video_summary(
    project_id: str,
    workflow_id: str,
    bucket_name: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Load video summary from GCS.

    Args:
        project_id: The project ID
        workflow_id: The workflow ID
        bucket_name: GCS bucket name

    Returns:
        Summary data or None if not found
    """
    from google.cloud import storage

    bucket_name = bucket_name or os.environ.get("GCP_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("GCP_BUCKET_NAME required")

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    path = f"projects/{project_id}/context/video_summaries/{workflow_id}.json"
    blob = bucket.blob(path)

    if not blob.exists():
        return None

    content = blob.download_as_string()
    return json.loads(content)


def load_all_video_summaries(
    project_id: str,
    workflow_ids: List[str],
    bucket_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Load all video summaries for a project.

    Args:
        project_id: The project ID
        workflow_ids: List of workflow IDs
        bucket_name: GCS bucket name

    Returns:
        List of summaries (only those that exist)
    """
    summaries = []

    for wf_id in workflow_ids:
        summary = load_video_summary(project_id, wf_id, bucket_name)
        if summary:
            summaries.append(summary)

    # Sort by sequence index
    summaries.sort(key=lambda x: x.get("sequence_index", 0))

    return summaries


def save_project_context(
    project_id: str,
    context: Dict[str, Any],
    bucket_name: Optional[str] = None
) -> str:
    """
    Save accumulated project context to GCS.

    Args:
        project_id: The project ID
        context: The accumulated context
        bucket_name: GCS bucket name

    Returns:
        GCS path where context was saved
    """
    from google.cloud import storage

    bucket_name = bucket_name or os.environ.get("GCP_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("GCP_BUCKET_NAME required")

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    path = f"projects/{project_id}/context/project_context.json"
    blob = bucket.blob(path)

    context["updated_at"] = datetime.utcnow().isoformat()

    blob.upload_from_string(
        json.dumps(context, ensure_ascii=False),
        content_type="application/json"
    )

    logger.info(f"Saved project context to gs://{bucket_name}/{path}")
    return f"gs://{bucket_name}/{path}"


def load_project_context(
    project_id: str,
    bucket_name: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Load accumulated project context from GCS.

    Args:
        project_id: The project ID
        bucket_name: GCS bucket name

    Returns:
        Context data or None if not found
    """
    from google.cloud import storage

    bucket_name = bucket_name or os.environ.get("GCP_BUCKET_NAME")
    if not bucket_name:
        raise ValueError("GCP_BUCKET_NAME required")

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    path = f"projects/{project_id}/context/project_context.json"
    blob = bucket.blob(path)

    if not blob.exists():
        return None

    content = blob.download_as_string()
    return json.loads(content)
