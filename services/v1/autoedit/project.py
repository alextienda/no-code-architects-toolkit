# Copyright (c) 2025
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

"""
Project Manager for AutoEdit Pipeline - Multi-Video Support

Manages projects that group multiple workflows (videos) together.
Provides batch processing capabilities and aggregated statistics.

Storage: GCS-based with local fallback (same pattern as WorkflowManager)
Path: gs://{bucket}/projects/{project_id}.json
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

# GCS storage configuration
GCS_BUCKET_NAME = os.environ.get("GCP_BUCKET_NAME", "")
PROJECT_PREFIX = "projects/"  # Prefix for project files in GCS

# Project states
PROJECT_STATES = {
    "created": "Project created, no videos added",
    "ready": "Videos added, ready to start processing",
    "processing": "Processing videos",
    "partial_complete": "Some videos completed, others pending/failed",
    "completed": "All videos processed successfully",
    "failed": "All videos failed processing",
    "error": "Project error"
}

# Consolidation states (for multi-video context analysis)
CONSOLIDATION_STATES = {
    "not_started": "Consolidation not yet initiated",
    "generating_embeddings": "Generating video embeddings with TwelveLabs",
    "generating_summaries": "Generating video summaries with Gemini",
    "detecting_redundancies": "Detecting cross-video redundancies",
    "analyzing_narrative": "Analyzing global narrative structure",
    "consolidating": "Running full consolidation pipeline",
    "consolidated": "Consolidation complete, ready for review",
    "review_consolidation": "User reviewing consolidation recommendations",
    "applying_recommendations": "Applying recommended cuts",
    "consolidation_complete": "Consolidation applied successfully",
    "consolidation_failed": "Consolidation process failed",
    "invalidated": "Consolidation invalidated (videos reordered/added/removed)"
}

# Default TTL: 7 days for projects (longer than workflows)
DEFAULT_PROJECT_TTL_HOURS = 168


class ProjectManager:
    """Manages multi-video projects with GCS-based storage."""

    def __init__(self, storage_path: Optional[str] = None, ttl_hours: int = DEFAULT_PROJECT_TTL_HOURS):
        """Initialize the project manager.

        Args:
            storage_path: Base path for local project storage (fallback).
            ttl_hours: Time-to-live for projects in hours
        """
        self.storage_path = Path(storage_path or os.path.join(LOCAL_STORAGE_PATH, "projects"))
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.ttl_hours = ttl_hours

        # Initialize GCS client if bucket is configured
        self.use_gcs = bool(GCS_BUCKET_NAME)
        self.gcs_client = None
        self.gcs_bucket = None

        if self.use_gcs:
            try:
                from google.cloud import storage
                self.gcs_client = storage.Client()
                self.gcs_bucket = self.gcs_client.bucket(GCS_BUCKET_NAME)
                logger.info(f"ProjectManager initialized with GCS storage: gs://{GCS_BUCKET_NAME}/{PROJECT_PREFIX}")
            except Exception as e:
                logger.warning(f"Failed to initialize GCS client for projects, falling back to local storage: {e}")
                self.use_gcs = False
                self.gcs_client = None
                self.gcs_bucket = None

        if not self.use_gcs:
            logger.info(f"ProjectManager initialized with local storage: {self.storage_path}")

    def _get_project_path(self, project_id: str) -> Path:
        """Get the local file path for a project (fallback)."""
        return self.storage_path / f"{project_id}.json"

    def _get_gcs_blob_name(self, project_id: str) -> str:
        """Get the GCS blob name for a project."""
        return f"{PROJECT_PREFIX}{project_id}.json"

    def _is_expired(self, project_data: Dict[str, Any]) -> bool:
        """Check if a project has expired based on TTL."""
        created_at = project_data.get("created_at")
        if not created_at:
            return False
        created_time = datetime.fromisoformat(created_at)
        expiry_time = created_time + timedelta(hours=self.ttl_hours)
        return datetime.utcnow() > expiry_time

    def create(
        self,
        name: str,
        description: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
        project_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a new project.

        Args:
            name: Project name (e.g., "Viaje a México")
            description: Optional project description
            options: Optional project configuration (language, style, etc.)
            project_context: Optional creator profile overrides for this project.
                Can include: campaign, sponsor, specific_audience, tone_override,
                style_override, focus, call_to_action, keywords_to_keep, keywords_to_avoid

        Returns:
            project_id: Unique identifier for the project
        """
        project_id = f"proj_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow().isoformat()

        project_data = {
            "project_id": project_id,
            "name": name,
            "description": description or "",
            "state": "created",
            "state_message": PROJECT_STATES["created"],
            "created_at": now,
            "updated_at": now,

            # Video workflows in this project
            "workflow_ids": [],

            # Project-wide options
            "options": {
                "language": "es",
                "style": "dynamic",
                **(options or {})
            },

            # Creator profile overrides for this project
            # Merged with CREATOR_GLOBAL_PROFILE when generating prompts
            "project_context": project_context or {},

            # Aggregated statistics
            "stats": {
                "total_videos": 0,
                "completed": 0,
                "pending": 0,
                "processing": 0,
                "failed": 0,
                "total_original_duration_ms": 0,
                "total_result_duration_ms": 0,
                "total_removed_duration_ms": 0,
                "avg_removal_percentage": 0.0
            },

            # Error tracking
            "error": None,
            "error_details": None,

            # Consolidation (multi-video context analysis)
            "consolidation_state": "not_started",
            "consolidation_state_message": CONSOLIDATION_STATES["not_started"],
            "consolidation_updated_at": None,
            "consolidation_options": {
                "redundancy_threshold": 0.85,
                "auto_apply": False,
                "generate_embeddings": True,
                "generate_summaries": True
            },
            "consolidation_results": None  # Stores last consolidation results
        }

        self._save(project_id, project_data)
        logger.info(f"Created project {project_id}: {name}")
        return project_id

    def get(self, project_id: str, include_generation: bool = False) -> Optional[Dict[str, Any]]:
        """Get project data by ID.

        Args:
            project_id: Project identifier
            include_generation: If True, include GCS generation number

        Returns:
            Project data dict or None if not found/expired
        """
        try:
            if self.use_gcs and self.gcs_bucket:
                blob_name = self._get_gcs_blob_name(project_id)
                blob = self.gcs_bucket.blob(blob_name)

                blob.reload()
                if not blob.exists():
                    logger.warning(f"Project not found in GCS: {project_id}")
                    return None

                content = blob.download_as_string()
                data = json.loads(content)

                if include_generation and blob.generation:
                    data["_gcs_generation"] = blob.generation

                if self._is_expired(data):
                    logger.info(f"Project expired: {project_id}")
                    self.delete(project_id)
                    return None

                return data
            else:
                path = self._get_project_path(project_id)
                if not path.exists():
                    logger.warning(f"Project not found in local storage: {project_id}")
                    return None

                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if self._is_expired(data):
                    logger.info(f"Project expired: {project_id}")
                    self.delete(project_id)
                    return None

                return data
        except Exception as e:
            logger.error(f"Error loading project {project_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def update(self, project_id: str, updates: Dict[str, Any], max_retries: int = 5) -> bool:
        """Update project data with optimistic locking.

        Args:
            project_id: Project identifier
            updates: Dictionary of fields to update
            max_retries: Maximum number of retries on conflict

        Returns:
            True if successful, False otherwise
        """
        from google.api_core import exceptions as gcs_exceptions

        for attempt in range(max_retries):
            data = self.get(project_id, include_generation=True)
            if not data:
                return False

            generation = data.pop("_gcs_generation", None)

            # Update fields
            for key, value in updates.items():
                if key in data:
                    data[key] = value
                elif key.startswith("stats."):
                    stat_key = key.split(".", 1)[1]
                    if data["stats"] is None:
                        data["stats"] = {}
                    data["stats"][stat_key] = value

            data["updated_at"] = datetime.utcnow().isoformat()

            # Update state message if state changed
            if "state" in updates and updates["state"] in PROJECT_STATES:
                data["state_message"] = PROJECT_STATES[updates["state"]]

            # Update consolidation state message if consolidation_state changed
            if "consolidation_state" in updates and updates["consolidation_state"] in CONSOLIDATION_STATES:
                data["consolidation_state_message"] = CONSOLIDATION_STATES[updates["consolidation_state"]]
                data["consolidation_updated_at"] = datetime.utcnow().isoformat()

            try:
                success = self._save(project_id, data, if_generation_match=generation)
                if success:
                    return True
            except gcs_exceptions.PreconditionFailed:
                logger.warning(f"Conflict on project {project_id}, retrying (attempt {attempt + 1}/{max_retries})")
                time.sleep(0.1 * (attempt + 1))
                continue

        logger.error(f"Failed to update project {project_id} after {max_retries} retries")
        return False

    def add_workflow(self, project_id: str, workflow_id: str) -> bool:
        """Add a workflow (video) to the project.

        Args:
            project_id: Project identifier
            workflow_id: Workflow identifier to add

        Returns:
            True if successful
        """
        data = self.get(project_id)
        if not data:
            return False

        if workflow_id not in data["workflow_ids"]:
            data["workflow_ids"].append(workflow_id)
            data["stats"]["total_videos"] = len(data["workflow_ids"])
            data["stats"]["pending"] += 1

            # Update state if this is the first video
            if data["state"] == "created":
                data["state"] = "ready"
                data["state_message"] = PROJECT_STATES["ready"]

            return self.update(project_id, {
                "workflow_ids": data["workflow_ids"],
                "stats": data["stats"],
                "state": data["state"]
            })

        return True  # Already added

    def remove_workflow(self, project_id: str, workflow_id: str) -> bool:
        """Remove a workflow from the project.

        Args:
            project_id: Project identifier
            workflow_id: Workflow identifier to remove

        Returns:
            True if successful
        """
        data = self.get(project_id)
        if not data:
            return False

        if workflow_id in data["workflow_ids"]:
            data["workflow_ids"].remove(workflow_id)
            data["stats"]["total_videos"] = len(data["workflow_ids"])

            # Recalculate stats (will be done properly by refresh_stats)
            if len(data["workflow_ids"]) == 0:
                data["state"] = "created"
                data["state_message"] = PROJECT_STATES["created"]

            return self.update(project_id, {
                "workflow_ids": data["workflow_ids"],
                "stats": data["stats"],
                "state": data["state"]
            })

        return True  # Already removed

    def get_workflows(self, project_id: str) -> List[Dict[str, Any]]:
        """Get all workflows in the project with their current status.

        Args:
            project_id: Project identifier

        Returns:
            List of workflow summaries
        """
        from services.v1.autoedit.workflow import get_workflow_manager

        data = self.get(project_id)
        if not data:
            return []

        workflows = []
        wf_manager = get_workflow_manager()

        for workflow_id in data["workflow_ids"]:
            wf_data = wf_manager.get(workflow_id)
            if wf_data:
                workflows.append({
                    "workflow_id": workflow_id,
                    "status": wf_data.get("status"),
                    "status_message": wf_data.get("status_message"),
                    "video_url": wf_data.get("video_url", "")[:50] + "..." if len(wf_data.get("video_url", "")) > 50 else wf_data.get("video_url", ""),
                    "preview_url": wf_data.get("preview_url"),
                    "output_url": wf_data.get("output_url"),
                    "stats": wf_data.get("stats"),
                    "created_at": wf_data.get("created_at"),
                    "updated_at": wf_data.get("updated_at")
                })
            else:
                # Workflow not found (may have been deleted)
                workflows.append({
                    "workflow_id": workflow_id,
                    "status": "not_found",
                    "status_message": "Workflow not found or expired"
                })

        return workflows

    def refresh_stats(self, project_id: str) -> bool:
        """Recalculate project statistics from workflow data.

        Args:
            project_id: Project identifier

        Returns:
            True if successful
        """
        from services.v1.autoedit.workflow import get_workflow_manager

        data = self.get(project_id)
        if not data:
            return False

        wf_manager = get_workflow_manager()

        # Initialize counters
        stats = {
            "total_videos": len(data["workflow_ids"]),
            "completed": 0,
            "pending": 0,
            "processing": 0,
            "failed": 0,
            "total_original_duration_ms": 0,
            "total_result_duration_ms": 0,
            "total_removed_duration_ms": 0,
            "avg_removal_percentage": 0.0
        }

        removal_percentages = []

        for workflow_id in data["workflow_ids"]:
            wf_data = wf_manager.get(workflow_id)
            if not wf_data:
                continue

            status = wf_data.get("status", "")

            # Count by status
            if status == "completed":
                stats["completed"] += 1
            elif status in ["error", "failed"]:
                stats["failed"] += 1
            elif status in ["created", "transcribed", "pending_review_1", "xml_approved", "pending_review_2"]:
                stats["pending"] += 1
            else:
                stats["processing"] += 1

            # Aggregate durations
            wf_stats = wf_data.get("stats", {})
            if wf_stats:
                if wf_stats.get("original_duration_ms"):
                    stats["total_original_duration_ms"] += wf_stats["original_duration_ms"]
                if wf_stats.get("result_duration_ms"):
                    stats["total_result_duration_ms"] += wf_stats["result_duration_ms"]
                if wf_stats.get("removed_duration_ms"):
                    stats["total_removed_duration_ms"] += wf_stats["removed_duration_ms"]
                if wf_stats.get("removal_percentage"):
                    removal_percentages.append(wf_stats["removal_percentage"])

        # Calculate average removal percentage
        if removal_percentages:
            stats["avg_removal_percentage"] = sum(removal_percentages) / len(removal_percentages)

        # Determine project state
        if stats["total_videos"] == 0:
            new_state = "created"
        elif stats["completed"] == stats["total_videos"]:
            new_state = "completed"
        elif stats["failed"] == stats["total_videos"]:
            new_state = "failed"
        elif stats["completed"] > 0 or stats["failed"] > 0:
            new_state = "partial_complete"
        elif stats["processing"] > 0:
            new_state = "processing"
        else:
            new_state = "ready"

        return self.update(project_id, {
            "stats": stats,
            "state": new_state
        })

    def delete(self, project_id: str) -> bool:
        """Delete a project.

        Note: This does NOT delete the associated workflows.

        Args:
            project_id: Project identifier

        Returns:
            True if deleted, False if not found
        """
        try:
            if self.use_gcs and self.gcs_bucket:
                blob_name = self._get_gcs_blob_name(project_id)
                blob = self.gcs_bucket.blob(blob_name)
                if blob.exists():
                    blob.delete()
                    logger.info(f"Deleted project from GCS: {project_id}")
                    return True
                return False
            else:
                path = self._get_project_path(project_id)
                if path.exists():
                    path.unlink()
                    logger.info(f"Deleted project: {project_id}")
                    return True
                return False
        except Exception as e:
            logger.error(f"Error deleting project {project_id}: {e}")
            return False

    def list_projects(self, state: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """List all projects, optionally filtered by state.

        Args:
            state: Filter by state (optional)
            limit: Maximum number of projects to return

        Returns:
            List of project summaries
        """
        projects = []

        try:
            if self.use_gcs and self.gcs_bucket:
                blobs = self.gcs_bucket.list_blobs(prefix=PROJECT_PREFIX)
                for blob in blobs:
                    if not blob.name.endswith('.json'):
                        continue
                    try:
                        content = blob.download_as_string()
                        data = json.loads(content)

                        if self._is_expired(data):
                            self.delete(data["project_id"])
                            continue

                        if state and data.get("state") != state:
                            continue

                        projects.append({
                            "project_id": data["project_id"],
                            "name": data["name"],
                            "description": data.get("description", ""),
                            "state": data["state"],
                            "state_message": data.get("state_message", ""),
                            "stats": data.get("stats", {}),
                            "created_at": data["created_at"],
                            "updated_at": data["updated_at"]
                        })

                        if len(projects) >= limit:
                            break
                    except Exception as e:
                        logger.error(f"Error reading project from GCS {blob.name}: {e}")
            else:
                for path in self.storage_path.glob("*.json"):
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            data = json.load(f)

                        if self._is_expired(data):
                            self.delete(data["project_id"])
                            continue

                        if state and data.get("state") != state:
                            continue

                        projects.append({
                            "project_id": data["project_id"],
                            "name": data["name"],
                            "description": data.get("description", ""),
                            "state": data["state"],
                            "state_message": data.get("state_message", ""),
                            "stats": data.get("stats", {}),
                            "created_at": data["created_at"],
                            "updated_at": data["updated_at"]
                        })

                        if len(projects) >= limit:
                            break
                    except Exception as e:
                        logger.error(f"Error reading project {path.stem}: {e}")
        except Exception as e:
            logger.error(f"Error listing projects: {e}")

        # Sort by updated_at descending
        projects.sort(key=lambda x: x["updated_at"], reverse=True)
        return projects

    def _save(self, project_id: str, data: Dict[str, Any], if_generation_match: Optional[int] = None) -> bool:
        """Save project data to storage.

        Args:
            project_id: Project identifier
            data: Project data
            if_generation_match: If provided, only save if blob generation matches

        Returns:
            True if successful
        """
        json_data = json.dumps(data, indent=2, ensure_ascii=False)

        if self.use_gcs and self.gcs_bucket:
            blob_name = self._get_gcs_blob_name(project_id)
            blob = self.gcs_bucket.blob(blob_name)

            if if_generation_match is not None:
                blob.upload_from_string(
                    json_data,
                    content_type='application/json',
                    if_generation_match=if_generation_match
                )
            else:
                blob.upload_from_string(json_data, content_type='application/json')

            logger.info(f"Saved project {project_id} to GCS - state: {data.get('state')}")
            return True
        else:
            try:
                path = self._get_project_path(project_id)
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(json_data)
                logger.info(f"Saved project {project_id} to LOCAL - state: {data.get('state')}")
                return True
            except Exception as e:
                logger.error(f"Error saving project {project_id}: {e}")
                return False


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_project_manager: Optional[ProjectManager] = None


def get_project_manager() -> ProjectManager:
    """Get the global project manager instance."""
    global _project_manager

    bucket_name = os.environ.get("GCP_BUCKET_NAME", "")
    should_use_gcs = bool(bucket_name)

    if _project_manager is not None:
        if should_use_gcs and not _project_manager.use_gcs:
            logger.info("Reinitializing ProjectManager: GCS now available")
            _project_manager = None

    if _project_manager is None:
        _project_manager = ProjectManager()

    return _project_manager


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_project(
    name: str,
    description: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None,
    project_context: Optional[Dict[str, Any]] = None
) -> str:
    """Create a new project (convenience function).

    Args:
        name: Project name
        description: Optional description
        options: Optional project options (language, style, etc.)
        project_context: Optional creator profile overrides for this project.
            Can include: campaign, sponsor, specific_audience, tone_override,
            style_override, focus, call_to_action, keywords_to_keep, keywords_to_avoid

    Returns:
        project_id
    """
    return get_project_manager().create(name, description, options, project_context)


def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    """Get project by ID (convenience function)."""
    return get_project_manager().get(project_id)


def update_project(project_id: str, updates: Dict[str, Any]) -> bool:
    """Update project (convenience function)."""
    return get_project_manager().update(project_id, updates)


def delete_project(project_id: str) -> bool:
    """Delete project (convenience function)."""
    return get_project_manager().delete(project_id)


def list_projects(state: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """List projects (convenience function)."""
    return get_project_manager().list_projects(state, limit)


def add_workflow_to_project(project_id: str, workflow_id: str) -> bool:
    """Add workflow to project (convenience function)."""
    return get_project_manager().add_workflow(project_id, workflow_id)


def remove_workflow_from_project(project_id: str, workflow_id: str) -> bool:
    """Remove workflow from project (convenience function)."""
    return get_project_manager().remove_workflow(project_id, workflow_id)


def get_project_workflows(project_id: str) -> List[Dict[str, Any]]:
    """Get project workflows (convenience function)."""
    return get_project_manager().get_workflows(project_id)


def refresh_project_stats(project_id: str) -> bool:
    """Refresh project statistics (convenience function)."""
    return get_project_manager().refresh_stats(project_id)
