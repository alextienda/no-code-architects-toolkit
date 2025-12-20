# Copyright (c) 2025 Stephen G. Pope
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

"""
AutoEdit Tasks API - Cloud Tasks Handlers

These endpoints are called by Cloud Tasks to execute pipeline steps.
They are NOT meant to be called directly by clients.

Flow:
1. Client calls POST /workflow with auto_start=true
2. System enqueues transcribe task
3. /tasks/transcribe executes and enqueues analyze
4. /tasks/analyze executes -> HITL 1 (stops)
5. Client approves HITL 1, system enqueues process
6. /tasks/process executes and enqueues preview
7. /tasks/preview executes -> HITL 2 (stops)
8. Client approves HITL 2, system enqueues render
9. /tasks/render executes -> done
"""

import os
import logging
from flask import Blueprint, request, jsonify
from services.authentication import authenticate
from services.v1.autoedit.workflow import get_workflow_manager
from services.v1.autoedit.task_queue import enqueue_next_task

v1_autoedit_tasks_api_bp = Blueprint('v1_autoedit_tasks_api', __name__)
logger = logging.getLogger(__name__)


def is_cloud_task_request():
    """Check if request comes from Cloud Tasks."""
    return request.headers.get("X-Cloud-Tasks") == "true"


# =============================================================================
# TASK: TRANSCRIBE
# =============================================================================
@v1_autoedit_tasks_api_bp.route('/v1/autoedit/tasks/transcribe', methods=['POST'])
@authenticate
def task_transcribe():
    """
    Cloud Task handler for transcription.

    Executes ElevenLabs transcription and automatically enqueues analyze task.
    """
    from services.v1.autoedit.pipeline import (
        transcribe_with_elevenlabs,
        transform_to_internal_format
    )

    data = request.json or {}
    workflow_id = data.get("workflow_id")
    language = data.get("language", "es")
    style = data.get("style", "dynamic")  # Pass through for analyze

    if not workflow_id:
        return jsonify({"error": "workflow_id required"}), 400

    logger.info(f"[TASK] Transcribe started for workflow {workflow_id}")

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return jsonify({"error": "Workflow not found", "workflow_id": workflow_id}), 404

        # Update status
        manager.set_status(workflow_id, "transcribing")

        # Get API key
        elevenlabs_api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not elevenlabs_api_key:
            manager.set_status(workflow_id, "error", error="ELEVENLABS_API_KEY not configured")
            return jsonify({"error": "ELEVENLABS_API_KEY not configured"}), 500

        # Execute transcription
        video_url = workflow["video_url"]
        elevenlabs_result = transcribe_with_elevenlabs(video_url, elevenlabs_api_key)

        # Transform to internal format
        transcript_internal = transform_to_internal_format(elevenlabs_result)

        # Calculate duration
        duration_ms = 0
        if transcript_internal:
            duration_ms = max(w["outMs"] for w in transcript_internal)

        # Store transcript and update status in a single atomic update
        # to avoid race conditions with GCS
        manager.update(workflow_id, {
            "transcript": elevenlabs_result.get("words", []),
            "transcript_internal": transcript_internal,
            "status": "transcribed",
            "stats": {
                "original_duration_ms": duration_ms,
                "word_count": len(transcript_internal)
            }
        })

        logger.info(f"[TASK] Transcribe completed for {workflow_id}: {len(transcript_internal)} words")

        # Auto-enqueue next task (analyze)
        enqueue_result = enqueue_next_task(
            current_task="transcribe",
            workflow_id=workflow_id,
            payload={"style": style}
        )

        return jsonify({
            "status": "transcribed",
            "workflow_id": workflow_id,
            "word_count": len(transcript_internal),
            "duration_ms": duration_ms,
            "next_task": enqueue_result
        }), 200

    except Exception as e:
        logger.error(f"[TASK] Transcribe failed for {workflow_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        manager.set_status(workflow_id, "error", error=str(e))
        return jsonify({"error": str(e), "workflow_id": workflow_id}), 500


# =============================================================================
# TASK: ANALYZE
# =============================================================================
@v1_autoedit_tasks_api_bp.route('/v1/autoedit/tasks/analyze', methods=['POST'])
@authenticate
def task_analyze():
    """
    Cloud Task handler for Gemini analysis.

    Executes Gemini analysis. Does NOT auto-enqueue - stops for HITL 1.
    Includes retry logic for GCS eventual consistency.
    """
    from services.v1.autoedit.pipeline import (
        prepare_blocks_for_gemini,
        analyze_with_gemini,
        combine_gemini_outputs
    )
    import google.auth
    import google.auth.transport.requests
    import time

    data = request.json or {}
    workflow_id = data.get("workflow_id")
    style = data.get("style", "dynamic")

    if not workflow_id:
        return jsonify({"error": "workflow_id required"}), 400

    logger.info(f"[TASK] Analyze started for workflow {workflow_id}")

    try:
        manager = get_workflow_manager()

        # Retry logic for GCS eventual consistency
        # The transcribe task may have just saved the transcript, give GCS time to sync
        max_retries = 5
        retry_delay = 2  # seconds
        transcript_internal = None

        for attempt in range(max_retries):
            workflow = manager.get(workflow_id)

            if not workflow:
                return jsonify({"error": "Workflow not found", "workflow_id": workflow_id}), 404

            transcript_internal = workflow.get("transcript_internal")
            if transcript_internal:
                logger.info(f"[TASK] Analyze: Found transcript on attempt {attempt + 1}")
                break

            if attempt < max_retries - 1:
                logger.info(f"[TASK] Analyze: No transcript yet, waiting {retry_delay}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)

        if not transcript_internal:
            logger.error(f"[TASK] Analyze: No transcript after {max_retries} attempts")
            return jsonify({"error": "No transcript available after retries", "workflow_id": workflow_id}), 400

        # Update status
        manager.set_status(workflow_id, "analyzing")

        # Prepare blocks for Gemini
        blocks_data = prepare_blocks_for_gemini(transcript_internal)
        blocks = blocks_data.get("blocks", [])
        formatted_text = blocks_data.get("formatted_text", "")

        if not blocks or not formatted_text:
            manager.set_status(workflow_id, "error", error="No text blocks to analyze")
            return jsonify({"error": "No text blocks to analyze", "workflow_id": workflow_id}), 400

        # Get GCP access token
        try:
            credentials, project = google.auth.default()
            auth_req = google.auth.transport.requests.Request()
            credentials.refresh(auth_req)
            access_token = credentials.token
        except Exception as auth_error:
            logger.error(f"Failed to get GCP credentials: {auth_error}")
            manager.set_status(workflow_id, "error", error=f"GCP auth failed: {str(auth_error)}")
            return jsonify({"error": f"GCP auth failed: {str(auth_error)}"}), 500

        # Build config
        gemini_config = {
            "gcp_project_id": os.environ.get("GCP_PROJECT_ID", "autoedit-at"),
            "gcp_location": os.environ.get("GCP_LOCATION", "us-central1"),
            "gemini_model": os.environ.get("GEMINI_MODEL", "gemini-2.5-pro"),
            "gemini_temperature": 0.0
        }

        # Analyze with Gemini
        gemini_results = analyze_with_gemini(
            formatted_text=formatted_text,
            access_token=access_token,
            config=gemini_config
        )

        # Combine outputs
        combined_xml = combine_gemini_outputs(gemini_results)

        # Store in workflow
        manager.set_gemini_xml(workflow_id, combined_xml)

        # Set status to pending_review_1 (HITL 1)
        # Note: We do NOT auto-enqueue the next task - user must approve

        logger.info(f"[TASK] Analyze completed for {workflow_id}: {len(blocks)} blocks -> pending_review_1")

        return jsonify({
            "status": "pending_review_1",
            "workflow_id": workflow_id,
            "block_count": len(blocks),
            "message": "Analysis complete. Waiting for HITL 1 approval."
        }), 200

    except Exception as e:
        logger.error(f"[TASK] Analyze failed for {workflow_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        manager.set_status(workflow_id, "error", error=str(e))
        return jsonify({"error": str(e), "workflow_id": workflow_id}), 500


# =============================================================================
# TASK: PROCESS (XML to Blocks)
# =============================================================================
@v1_autoedit_tasks_api_bp.route('/v1/autoedit/tasks/process', methods=['POST'])
@authenticate
def task_process():
    """
    Cloud Task handler for processing XML to blocks.

    Calls unified-processor and auto-enqueues preview task.
    """
    import requests as http_requests

    data = request.json or {}
    workflow_id = data.get("workflow_id")
    config = data.get("config", {})

    if not workflow_id:
        return jsonify({"error": "workflow_id required"}), 400

    logger.info(f"[TASK] Process started for workflow {workflow_id}")

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return jsonify({"error": "Workflow not found", "workflow_id": workflow_id}), 404

        # Get XML and transcript
        xml_string = workflow.get("user_xml") or workflow.get("gemini_xml")
        transcript = workflow.get("transcript_internal")

        if not xml_string:
            return jsonify({"error": "No XML to process", "workflow_id": workflow_id}), 400
        if not transcript:
            return jsonify({"error": "No transcript available", "workflow_id": workflow_id}), 400

        # Update status
        manager.set_status(workflow_id, "processing")

        # Call unified processor
        nca_url = os.environ.get("NCA_TOOLKIT_URL", "http://localhost:8080")
        api_key = os.environ.get("API_KEY", "")

        processor_payload = {
            "xml_string": xml_string,
            "transcript": transcript,
            "config": {
                "padding_before_ms": config.get("padding_before_ms", 90),
                "padding_after_ms": config.get("padding_after_ms", 130),
                "silence_threshold_ms": config.get("silence_threshold_ms", 50),
                "merge_threshold_ms": config.get("merge_threshold_ms", 100)
            }
        }

        response = http_requests.post(
            f"{nca_url}/v1/transcription/unified-processor",
            json=processor_payload,
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            timeout=120
        )

        if response.status_code != 200:
            logger.error(f"Unified processor failed: {response.text}")
            manager.set_status(workflow_id, "error", error=f"Processing failed: {response.text}")
            return jsonify({"error": f"Processing failed: {response.text}"}), 500

        result = response.json()
        # Unified processor returns "cortes" not "blocks"
        response_data = result.get("response", {})
        blocks = response_data.get("cortes", response_data.get("blocks", result.get("cortes", result.get("blocks", []))))

        if not blocks:
            manager.set_status(workflow_id, "error", error="No blocks returned from processor")
            return jsonify({"error": "No blocks returned from processor"}), 500

        # Ensure blocks have IDs
        from services.v1.autoedit.blocks import ensure_block_ids, calculate_gaps, calculate_stats
        blocks = ensure_block_ids(blocks)

        # Get video duration
        video_duration_ms = workflow.get("stats", {}).get("original_duration_ms", 0)
        if not video_duration_ms and transcript:
            video_duration_ms = max(w.get("outMs", 0) for w in transcript)

        # Calculate gaps and stats
        gaps = calculate_gaps(blocks, video_duration_ms, transcript)
        stats = calculate_stats(blocks, video_duration_ms)

        # Store in workflow
        manager.set_blocks(workflow_id, blocks, gaps, stats)
        manager.set_status(workflow_id, "generating_preview")

        logger.info(f"[TASK] Process completed for {workflow_id}: {len(blocks)} blocks")

        # Auto-enqueue preview task
        enqueue_result = enqueue_next_task(
            current_task="process",
            workflow_id=workflow_id,
            payload={"quality": "480p"}
        )

        return jsonify({
            "status": "generating_preview",
            "workflow_id": workflow_id,
            "block_count": len(blocks),
            "next_task": enqueue_result
        }), 200

    except Exception as e:
        logger.error(f"[TASK] Process failed for {workflow_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        manager.set_status(workflow_id, "error", error=str(e))
        return jsonify({"error": str(e), "workflow_id": workflow_id}), 500


# =============================================================================
# TASK: PREVIEW
# =============================================================================
@v1_autoedit_tasks_api_bp.route('/v1/autoedit/tasks/preview', methods=['POST'])
@authenticate
def task_preview():
    """
    Cloud Task handler for preview generation.

    Generates low-res preview. Does NOT auto-enqueue - stops for HITL 2.
    """
    from services.v1.autoedit.preview import generate_preview

    data = request.json or {}
    workflow_id = data.get("workflow_id")
    quality = data.get("quality", "480p")
    fade_duration = data.get("fade_duration", 0.025)

    if not workflow_id:
        return jsonify({"error": "workflow_id required"}), 400

    logger.info(f"[TASK] Preview started for workflow {workflow_id}")

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return jsonify({"error": "Workflow not found", "workflow_id": workflow_id}), 404

        blocks = workflow.get("blocks")
        logger.info(f"[TASK] Preview - blocks type: {type(blocks)}, length: {len(blocks) if blocks else 0}")
        if blocks and len(blocks) > 0:
            logger.info(f"[TASK] Preview - first block type: {type(blocks[0])}, content: {str(blocks[0])[:200]}")

        if not blocks:
            return jsonify({"error": "No blocks available", "workflow_id": workflow_id}), 400

        # Validate blocks format
        if not isinstance(blocks[0], dict):
            error_msg = f"Blocks have invalid format: first item is {type(blocks[0])}, expected dict"
            logger.error(f"[TASK] Preview failed: {error_msg}")
            manager.set_status(workflow_id, "error", error=error_msg)
            return jsonify({"error": error_msg, "workflow_id": workflow_id}), 500

        # Update status
        manager.set_status(workflow_id, "generating_preview")

        # Get video duration
        video_duration_ms = workflow.get("stats", {}).get("original_duration_ms", 0)

        # Generate preview
        result = generate_preview(
            workflow_id=workflow_id,
            video_url=workflow["video_url"],
            blocks=blocks,
            video_duration_ms=video_duration_ms,
            transcript_words=workflow.get("transcript_internal"),
            quality=quality,
            fade_duration=fade_duration
        )

        # Update workflow with preview
        manager.set_preview(workflow_id, result["preview_url"], result["preview_duration_ms"])
        manager.update(workflow_id, {
            "blocks": result["blocks"],
            "gaps": result["gaps"]
        })

        # Set status to pending_review_2 (HITL 2)
        # Note: We do NOT auto-enqueue - user must approve

        logger.info(f"[TASK] Preview completed for {workflow_id}: {result['preview_url']}")

        return jsonify({
            "status": "pending_review_2",
            "workflow_id": workflow_id,
            "preview_url": result["preview_url"],
            "preview_duration_ms": result["preview_duration_ms"],
            "message": "Preview ready. Waiting for HITL 2 approval."
        }), 200

    except Exception as e:
        logger.error(f"[TASK] Preview failed for {workflow_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        manager.set_status(workflow_id, "error", error=str(e))
        return jsonify({"error": str(e), "workflow_id": workflow_id}), 500


# =============================================================================
# TASK: RENDER
# =============================================================================
@v1_autoedit_tasks_api_bp.route('/v1/autoedit/tasks/render', methods=['POST'])
@authenticate
def task_render():
    """
    Cloud Task handler for final render.

    Generates high-quality final video. No next task.
    """
    from services.v1.autoedit.preview import generate_final_render
    from services.v1.autoedit.ffmpeg_builder import blocks_to_cuts

    data = request.json or {}
    workflow_id = data.get("workflow_id")
    quality = data.get("quality", "high")
    crossfade_duration = data.get("crossfade_duration", 0.025)

    if not workflow_id:
        return jsonify({"error": "workflow_id required"}), 400

    logger.info(f"[TASK] Render started for workflow {workflow_id} at {quality} quality")

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return jsonify({"error": "Workflow not found", "workflow_id": workflow_id}), 404

        blocks = workflow.get("blocks")
        if not blocks:
            return jsonify({"error": "No blocks available", "workflow_id": workflow_id}), 400

        # Update status
        manager.set_status(workflow_id, "rendering")

        # Get video duration
        video_duration_ms = workflow.get("stats", {}).get("original_duration_ms", 0)

        # Generate final render
        result = generate_final_render(
            workflow_id=workflow_id,
            video_url=workflow["video_url"],
            blocks=blocks,
            video_duration_ms=video_duration_ms,
            quality=quality,
            fade_duration=crossfade_duration
        )

        # Update workflow with output
        manager.set_output(
            workflow_id=workflow_id,
            output_url=result["output_url"],
            output_duration_ms=result["output_duration_ms"],
            render_time_sec=result["stats"]["render_time_sec"]
        )

        # Store cuts for reference
        cuts = blocks_to_cuts(blocks)
        manager.update(workflow_id, {"cuts": cuts})

        logger.info(f"[TASK] Render completed for {workflow_id}: {result['output_url']}")

        # Send webhook if configured
        webhook_url = workflow.get("options", {}).get("webhook_url")
        if webhook_url:
            try:
                from services.webhook import send_webhook
                send_webhook(webhook_url, {
                    "workflow_id": workflow_id,
                    "status": "completed",
                    "output_url": result["output_url"],
                    "output_duration_ms": result["output_duration_ms"],
                    "stats": result["stats"]
                })
            except Exception as webhook_error:
                logger.warning(f"Failed to send webhook: {webhook_error}")

        return jsonify({
            "status": "completed",
            "workflow_id": workflow_id,
            "output_url": result["output_url"],
            "output_duration_ms": result["output_duration_ms"],
            "stats": result["stats"]
        }), 200

    except Exception as e:
        logger.error(f"[TASK] Render failed for {workflow_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        manager.set_status(workflow_id, "error", error=str(e))
        return jsonify({"error": str(e), "workflow_id": workflow_id}), 500


# =============================================================================
# TASK: ANALYZE B-ROLL (Visual Analysis with Gemini Vision)
# =============================================================================
@v1_autoedit_tasks_api_bp.route('/v1/autoedit/tasks/analyze-broll', methods=['POST'])
@authenticate
def task_analyze_broll():
    """
    Cloud Task handler for B-Roll visual analysis.

    Extracts frames from video and sends to Gemini Vision for B-Roll identification.
    Can run in parallel with A-Roll analysis.
    """
    from services.v1.autoedit.analyze_broll import analyze_workflow_broll

    data = request.json or {}
    workflow_id = data.get("workflow_id")

    if not workflow_id:
        return jsonify({"error": "workflow_id required"}), 400

    logger.info(f"[TASK] Analyze B-Roll started for workflow {workflow_id}")

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return jsonify({"error": "Workflow not found", "workflow_id": workflow_id}), 404

        # Run B-Roll analysis
        result = analyze_workflow_broll(workflow_id)

        if "error" in result:
            logger.error(f"[TASK] Analyze B-Roll failed for {workflow_id}: {result['error']}")
            return jsonify({
                "status": "error",
                "workflow_id": workflow_id,
                "error": result["error"]
            }), 500

        # Get summary info
        summary = result.get("analysis_summary", {})
        segments = result.get("segments", [])

        logger.info(f"[TASK] Analyze B-Roll completed for {workflow_id}: {len(segments)} segments found")

        return jsonify({
            "status": "broll_analyzed",
            "workflow_id": workflow_id,
            "segments_count": len(segments),
            "total_broll_duration_ms": summary.get("total_broll_duration_ms", 0),
            "broll_percentage": summary.get("broll_percentage", 0),
            "message": "B-Roll analysis complete."
        }), 200

    except Exception as e:
        logger.error(f"[TASK] Analyze B-Roll failed for {workflow_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e), "workflow_id": workflow_id}), 500


# =============================================================================
# TASK: GENERATE EMBEDDINGS (Multi-Video Context - Fase 4B)
# =============================================================================
@v1_autoedit_tasks_api_bp.route('/v1/autoedit/tasks/generate-embeddings', methods=['POST'])
@authenticate
def task_generate_embeddings():
    """
    Cloud Task handler for generating video embeddings with TwelveLabs.

    Generates Marengo 3.0 embeddings for cross-video similarity detection.
    """
    from services.v1.autoedit.twelvelabs_embeddings import (
        create_video_embeddings,
        save_embeddings_to_gcs
    )

    data = request.json or {}
    workflow_id = data.get("workflow_id")
    project_id = data.get("project_id")
    video_url = data.get("video_url")
    video_duration_sec = data.get("video_duration_sec")

    if not workflow_id:
        return jsonify({"error": "workflow_id required"}), 400

    logger.info(f"[TASK] Generate embeddings started for workflow {workflow_id}")

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return jsonify({"error": "Workflow not found", "workflow_id": workflow_id}), 404

        # Get video URL if not provided
        if not video_url:
            video_url = workflow.get("video_url")
        if not video_url:
            return jsonify({"error": "No video URL available", "workflow_id": workflow_id}), 400

        # Get duration if not provided
        if not video_duration_sec:
            video_duration_sec = workflow.get("stats", {}).get("original_duration_ms", 0) / 1000

        # Generate embeddings
        result = create_video_embeddings(
            video_url=video_url,
            video_duration_sec=video_duration_sec,
            wait_for_result=True
        )

        if not result.get("success"):
            error = result.get("error", "Unknown error")
            logger.error(f"[TASK] Embeddings failed for {workflow_id}: {error}")
            return jsonify({
                "status": "error",
                "workflow_id": workflow_id,
                "error": error
            }), 500

        # Save embeddings to GCS
        gcs_path = save_embeddings_to_gcs(workflow_id, result)

        # Update workflow with embeddings info
        manager.update(workflow_id, {
            "embeddings_path": gcs_path,
            "embeddings_count": len(result.get("embeddings", [])),
            "embeddings_model": result.get("model", "marengo3.0")
        })

        logger.info(f"[TASK] Embeddings completed for {workflow_id}: {len(result.get('embeddings', []))} vectors")

        return jsonify({
            "status": "embeddings_generated",
            "workflow_id": workflow_id,
            "embeddings_count": len(result.get("embeddings", [])),
            "segments_count": len(result.get("segments", [])),
            "gcs_path": gcs_path
        }), 200

    except Exception as e:
        logger.error(f"[TASK] Generate embeddings failed for {workflow_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e), "workflow_id": workflow_id}), 500


# =============================================================================
# TASK: GENERATE SUMMARY (Multi-Video Context - Fase 4B)
# =============================================================================
@v1_autoedit_tasks_api_bp.route('/v1/autoedit/tasks/generate-summary', methods=['POST'])
@authenticate
def task_generate_summary():
    """
    Cloud Task handler for generating video summary for context.

    Generates a semantic summary using Gemini to pass as context
    to subsequent video analyses.
    """
    from services.v1.autoedit.context_builder import (
        generate_video_summary,
        save_video_summary
    )

    data = request.json or {}
    workflow_id = data.get("workflow_id")
    project_id = data.get("project_id")
    sequence_index = data.get("sequence_index", 0)

    if not workflow_id:
        return jsonify({"error": "workflow_id required"}), 400
    if not project_id:
        return jsonify({"error": "project_id required"}), 400

    logger.info(f"[TASK] Generate summary started for workflow {workflow_id} (seq {sequence_index})")

    try:
        manager = get_workflow_manager()
        workflow = manager.get(workflow_id)

        if not workflow:
            return jsonify({"error": "Workflow not found", "workflow_id": workflow_id}), 404

        # Get transcript
        transcript_internal = workflow.get("transcript_internal", [])
        transcript_text = " ".join(w.get("text", "") for w in transcript_internal)

        if not transcript_text:
            return jsonify({
                "error": "No transcript available",
                "workflow_id": workflow_id
            }), 400

        # Generate summary
        summary = generate_video_summary(
            workflow_id=workflow_id,
            transcript_text=transcript_text,
            gemini_xml=workflow.get("gemini_xml"),
            sequence_index=sequence_index
        )

        # Save summary
        gcs_path = save_video_summary(project_id, workflow_id, summary)

        logger.info(f"[TASK] Summary completed for {workflow_id}: {len(summary.get('key_points', []))} key points")

        return jsonify({
            "status": "summary_generated",
            "workflow_id": workflow_id,
            "project_id": project_id,
            "sequence_index": sequence_index,
            "key_points_count": len(summary.get("key_points", [])),
            "narrative_function": summary.get("narrative_function", "unknown"),
            "gcs_path": gcs_path
        }), 200

    except Exception as e:
        logger.error(f"[TASK] Generate summary failed for {workflow_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e), "workflow_id": workflow_id}), 500


# =============================================================================
# TASK: CONSOLIDATE (Multi-Video Context - Fase 4B)
# =============================================================================
@v1_autoedit_tasks_api_bp.route('/v1/autoedit/tasks/consolidate', methods=['POST'])
@authenticate
def task_consolidate():
    """
    Cloud Task handler for project consolidation.

    Runs the full consolidation pipeline:
    1. Generate embeddings (if needed)
    2. Generate summaries (if needed)
    3. Detect cross-video redundancies
    4. Analyze narrative structure
    5. Generate recommendations
    """
    from services.v1.autoedit.project_consolidation import consolidate_project
    from services.v1.autoedit.project import get_project, update_project

    data = request.json or {}
    project_id = data.get("project_id")
    force_regenerate = data.get("force_regenerate", False)
    redundancy_threshold = data.get("redundancy_threshold", 0.85)
    auto_apply = data.get("auto_apply", False)
    webhook_url = data.get("webhook_url")

    if not project_id:
        return jsonify({"error": "project_id required"}), 400

    logger.info(f"[TASK] Consolidation started for project {project_id}")

    try:
        # Verify project exists
        project = get_project(project_id)
        if not project:
            return jsonify({"error": "Project not found", "project_id": project_id}), 404

        # Update consolidation state
        update_project(project_id, {"consolidation_state": "consolidating"})

        # Run consolidation
        results = consolidate_project(
            project_id=project_id,
            force_regenerate=force_regenerate,
            redundancy_threshold=redundancy_threshold,
            auto_apply=auto_apply
        )

        status = results.get("status", "unknown")
        logger.info(f"[TASK] Consolidation completed for {project_id}: {status}")

        # Send webhook if configured
        if webhook_url and status == "success":
            try:
                import requests as http_requests
                http_requests.post(
                    webhook_url,
                    json={
                        "project_id": project_id,
                        "status": "consolidated",
                        "redundancy_count": results.get("steps", {}).get("redundancies", {}).get("redundancies_found", 0),
                        "recommendations": results.get("recommendations", [])
                    },
                    timeout=30
                )
            except Exception as webhook_error:
                logger.warning(f"Failed to send consolidation webhook: {webhook_error}")

        return jsonify({
            "status": status,
            "project_id": project_id,
            "consolidation_results": results
        }), 200

    except Exception as e:
        logger.error(f"[TASK] Consolidation failed for {project_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())

        # Update project state
        try:
            update_project(project_id, {"consolidation_state": "consolidation_failed"})
        except:
            pass

        return jsonify({"error": str(e), "project_id": project_id}), 500