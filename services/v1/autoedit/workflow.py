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

"""
Workflow State Manager for AutoEdit Pipeline

Manages workflow state with file-based storage (JSON files) and optional Redis backend.
Supports TTL for automatic cleanup of stale workflows.
"""

import os
import json
import uuid
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path

from config import LOCAL_STORAGE_PATH

logger = logging.getLogger(__name__)

# =============================================================================
# WORKFLOW STATES
# =============================================================================

WORKFLOW_STATES = {
    # Phase 1: Transcription and Analysis
    "created": "Workflow created",
    "transcribing": "Transcribing with ElevenLabs",
    "transcribed": "Transcription complete",
    "analyzing": "Analyzing with Gemini",

    # HITL 1: XML Review
    "pending_review_1": "HITL 1: Waiting for XML review",
    "xml_approved": "XML approved by user",

    # Phase 2: Processing
    "processing": "Mapping XML to timestamps",

    # HITL 2: Preview and Refinement
    "generating_preview": "Generating low-res preview",
    "pending_review_2": "HITL 2: Preview ready, waiting for approval",
    "modifying_blocks": "User modifying blocks",
    "regenerating_preview": "Regenerating preview with changes",

    # Phase 3: Final Render
    "rendering": "FFmpeg processing final video (high quality)",
    "completed": "Final video ready",

    # Errors
    "error": "Error in some step"
}

# Default TTL: 24 hours
DEFAULT_TTL_HOURS = 24


class WorkflowManager:
    """Manages workflow state with file-based storage."""

    def __init__(self, storage_path: Optional[str] = None, ttl_hours: int = DEFAULT_TTL_HOURS):
        """Initialize the workflow manager.

        Args:
            storage_path: Base path for workflow storage. Defaults to LOCAL_STORAGE_PATH/workflows
            ttl_hours: Time-to-live for workflows in hours
        """
        self.storage_path = Path(storage_path or os.path.join(LOCAL_STORAGE_PATH, "workflows"))
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.ttl_hours = ttl_hours
        logger.info(f"WorkflowManager initialized with storage: {self.storage_path}")

    def _get_workflow_path(self, workflow_id: str) -> Path:
        """Get the file path for a workflow."""
        return self.storage_path / f"{workflow_id}.json"

    def _is_expired(self, workflow_data: Dict[str, Any]) -> bool:
        """Check if a workflow has expired based on TTL."""
        created_at = workflow_data.get("created_at")
        if not created_at:
            return False
        created_time = datetime.fromisoformat(created_at)
        expiry_time = created_time + timedelta(hours=self.ttl_hours)
        return datetime.utcnow() > expiry_time

    def create(self, video_url: str, options: Optional[Dict[str, Any]] = None) -> str:
        """Create a new workflow.

        Args:
            video_url: URL of the source video
            options: Optional workflow configuration

        Returns:
            workflow_id: Unique identifier for the workflow
        """
        workflow_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        workflow_data = {
            "workflow_id": workflow_id,
            "status": "created",
            "status_message": WORKFLOW_STATES["created"],
            "video_url": video_url,
            "options": options or {},
            "created_at": now,
            "updated_at": now,

            # Data storage (populated as workflow progresses)
            "transcript": None,           # ElevenLabs transcript
            "transcript_internal": None,  # Internal format with NumID
            "gemini_xml": None,           # Combined XML from Gemini
            "user_xml": None,             # XML after HITL 1 modifications
            "blocks": None,               # Blocks with timestamps
            "gaps": None,                 # Removed segments
            "cuts": None,                 # Final cuts for FFmpeg
            "preview_url": None,          # Low-res preview URL
            "preview_duration_ms": None,
            "output_url": None,           # Final video URL
            "output_duration_ms": None,

            # Statistics
            "stats": {
                "original_duration_ms": None,
                "result_duration_ms": None,
                "removed_duration_ms": None,
                "removal_percentage": None,
                "render_time_sec": None
            },

            # Error tracking
            "error": None,
            "error_details": None
        }

        self._save(workflow_id, workflow_data)
        logger.info(f"Created workflow {workflow_id} for video: {video_url[:50]}...")
        return workflow_id

    def get(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get workflow data by ID.

        Args:
            workflow_id: Workflow identifier

        Returns:
            Workflow data dict or None if not found/expired
        """
        path = self._get_workflow_path(workflow_id)
        if not path.exists():
            logger.warning(f"Workflow not found: {workflow_id}")
            return None

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if self._is_expired(data):
                logger.info(f"Workflow expired: {workflow_id}")
                self.delete(workflow_id)
                return None

            return data
        except Exception as e:
            logger.error(f"Error loading workflow {workflow_id}: {e}")
            return None

    def update(self, workflow_id: str, updates: Dict[str, Any]) -> bool:
        """Update workflow data.

        Args:
            workflow_id: Workflow identifier
            updates: Dictionary of fields to update

        Returns:
            True if successful, False otherwise
        """
        data = self.get(workflow_id)
        if not data:
            return False

        # Update fields
        for key, value in updates.items():
            if key in data:
                data[key] = value
            elif key.startswith("stats."):
                # Handle nested stats updates like "stats.render_time_sec"
                stat_key = key.split(".", 1)[1]
                if data["stats"] is None:
                    data["stats"] = {}
                data["stats"][stat_key] = value

        data["updated_at"] = datetime.utcnow().isoformat()

        # Update status message if status changed
        if "status" in updates and updates["status"] in WORKFLOW_STATES:
            data["status_message"] = WORKFLOW_STATES[updates["status"]]

        return self._save(workflow_id, data)

    def set_status(
        self,
        workflow_id: str,
        status: str,
        error: Optional[str] = None,
        error_details: Optional[str] = None
    ) -> bool:
        """Update workflow status.

        Args:
            workflow_id: Workflow identifier
            status: New status (must be in WORKFLOW_STATES)
            error: Error message (for error status)
            error_details: Detailed error info

        Returns:
            True if successful, False otherwise
        """
        if status not in WORKFLOW_STATES:
            logger.error(f"Invalid status: {status}")
            return False

        updates = {"status": status}
        if error:
            updates["error"] = error
        if error_details:
            updates["error_details"] = error_details

        return self.update(workflow_id, updates)

    def set_transcript(
        self,
        workflow_id: str,
        transcript: List[Dict[str, Any]],
        transcript_internal: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """Store transcript data.

        Args:
            workflow_id: Workflow identifier
            transcript: ElevenLabs transcript format
            transcript_internal: Internal format with NumID

        Returns:
            True if successful
        """
        updates = {
            "transcript": transcript,
            "status": "transcribed"
        }
        if transcript_internal:
            updates["transcript_internal"] = transcript_internal
        return self.update(workflow_id, updates)

    def set_gemini_xml(self, workflow_id: str, xml_string: str) -> bool:
        """Store Gemini analysis XML.

        Args:
            workflow_id: Workflow identifier
            xml_string: Combined XML from Gemini

        Returns:
            True if successful
        """
        return self.update(workflow_id, {
            "gemini_xml": xml_string,
            "status": "pending_review_1"
        })

    def set_user_xml(self, workflow_id: str, xml_string: str) -> bool:
        """Store user-modified XML after HITL 1.

        Args:
            workflow_id: Workflow identifier
            xml_string: XML with user modifications

        Returns:
            True if successful
        """
        return self.update(workflow_id, {
            "user_xml": xml_string,
            "status": "xml_approved"
        })

    def set_blocks(
        self,
        workflow_id: str,
        blocks: List[Dict[str, Any]],
        gaps: Optional[List[Dict[str, Any]]] = None,
        stats: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Store blocks and gaps after unified processor.

        Args:
            workflow_id: Workflow identifier
            blocks: List of blocks with timestamps
            gaps: List of removed segments
            stats: Processing statistics

        Returns:
            True if successful
        """
        updates = {
            "blocks": blocks,
            "status": "generating_preview"
        }
        if gaps is not None:
            updates["gaps"] = gaps
        if stats:
            data = self.get(workflow_id)
            if data and data.get("stats"):
                data["stats"].update(stats)
                updates["stats"] = data["stats"]
            else:
                updates["stats"] = stats
        return self.update(workflow_id, updates)

    def set_preview(
        self,
        workflow_id: str,
        preview_url: str,
        preview_duration_ms: int
    ) -> bool:
        """Store preview video URL.

        Args:
            workflow_id: Workflow identifier
            preview_url: URL of the low-res preview
            preview_duration_ms: Duration of preview in milliseconds

        Returns:
            True if successful
        """
        return self.update(workflow_id, {
            "preview_url": preview_url,
            "preview_duration_ms": preview_duration_ms,
            "status": "pending_review_2"
        })

    def set_output(
        self,
        workflow_id: str,
        output_url: str,
        output_duration_ms: int,
        render_time_sec: float
    ) -> bool:
        """Store final output video URL.

        Args:
            workflow_id: Workflow identifier
            output_url: URL of the final video
            output_duration_ms: Duration in milliseconds
            render_time_sec: Time taken to render

        Returns:
            True if successful
        """
        data = self.get(workflow_id)
        stats = data.get("stats", {}) if data else {}
        stats["render_time_sec"] = render_time_sec
        stats["result_duration_ms"] = output_duration_ms

        return self.update(workflow_id, {
            "output_url": output_url,
            "output_duration_ms": output_duration_ms,
            "stats": stats,
            "status": "completed"
        })

    def delete(self, workflow_id: str) -> bool:
        """Delete a workflow.

        Args:
            workflow_id: Workflow identifier

        Returns:
            True if deleted, False if not found
        """
        path = self._get_workflow_path(workflow_id)
        if path.exists():
            try:
                path.unlink()
                logger.info(f"Deleted workflow: {workflow_id}")
                return True
            except Exception as e:
                logger.error(f"Error deleting workflow {workflow_id}: {e}")
                return False
        return False

    def list_workflows(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all workflows, optionally filtered by status.

        Args:
            status: Filter by status (optional)

        Returns:
            List of workflow summaries
        """
        workflows = []
        for path in self.storage_path.glob("*.json"):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if self._is_expired(data):
                    self.delete(data["workflow_id"])
                    continue

                if status and data.get("status") != status:
                    continue

                # Return summary, not full data
                workflows.append({
                    "workflow_id": data["workflow_id"],
                    "status": data["status"],
                    "status_message": data.get("status_message", ""),
                    "video_url": data["video_url"][:50] + "..." if len(data.get("video_url", "")) > 50 else data.get("video_url", ""),
                    "created_at": data["created_at"],
                    "updated_at": data["updated_at"]
                })
            except Exception as e:
                logger.error(f"Error reading workflow {path.stem}: {e}")

        # Sort by updated_at descending
        workflows.sort(key=lambda x: x["updated_at"], reverse=True)
        return workflows

    def cleanup_expired(self) -> int:
        """Clean up expired workflows.

        Returns:
            Number of workflows deleted
        """
        count = 0
        for path in self.storage_path.glob("*.json"):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if self._is_expired(data):
                    path.unlink()
                    count += 1
                    logger.info(f"Cleaned up expired workflow: {data.get('workflow_id')}")
            except Exception as e:
                logger.error(f"Error during cleanup of {path.stem}: {e}")
        return count

    def _save(self, workflow_id: str, data: Dict[str, Any]) -> bool:
        """Save workflow data to file.

        Args:
            workflow_id: Workflow identifier
            data: Workflow data

        Returns:
            True if successful
        """
        path = self._get_workflow_path(workflow_id)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Error saving workflow {workflow_id}: {e}")
            return False


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

# Global workflow manager instance
_workflow_manager: Optional[WorkflowManager] = None


def get_workflow_manager() -> WorkflowManager:
    """Get the global workflow manager instance.

    Creates the instance on first call.
    """
    global _workflow_manager
    if _workflow_manager is None:
        _workflow_manager = WorkflowManager()
    return _workflow_manager


def create_workflow(video_url: str, options: Optional[Dict[str, Any]] = None) -> str:
    """Create a new workflow (convenience function)."""
    return get_workflow_manager().create(video_url, options)


def get_workflow(workflow_id: str) -> Optional[Dict[str, Any]]:
    """Get workflow by ID (convenience function)."""
    return get_workflow_manager().get(workflow_id)


def update_workflow(workflow_id: str, updates: Dict[str, Any]) -> bool:
    """Update workflow (convenience function)."""
    return get_workflow_manager().update(workflow_id, updates)


def delete_workflow(workflow_id: str) -> bool:
    """Delete workflow (convenience function)."""
    return get_workflow_manager().delete(workflow_id)
