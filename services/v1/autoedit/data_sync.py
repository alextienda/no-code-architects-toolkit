# Copyright (c) 2025 Stephen G. Pope
# Licensed under GPL-2.0

"""
Data Synchronization Service for AutoEdit Phase 5

Synchronizes data between:
- GCS (Source of Truth) - Workflow JSON files
- Neo4j (Knowledge Graph) - Relationship queries
- FAISS (Vector Index) - Similarity search

GCS remains the authoritative source. Neo4j and FAISS are derived views
that are populated and updated based on GCS data.
"""

import os
import json
import logging
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime

from config import (
    USE_KNOWLEDGE_GRAPH,
    USE_FAISS_SEARCH,
    GCP_BUCKET_NAME
)

logger = logging.getLogger(__name__)


# =============================================================================
# DATA SYNC MANAGER
# =============================================================================

class DataSyncManager:
    """
    Manages synchronization between GCS, Neo4j, and FAISS.

    Provides methods to:
    - Populate Neo4j/FAISS from existing GCS data
    - Update derived stores when GCS data changes
    - Rebuild indexes from scratch
    - Handle partial sync failures gracefully
    """

    def __init__(self):
        self._graph_manager = None
        self._faiss_manager = None

    def _get_graph_manager(self):
        """Lazy load graph manager."""
        if self._graph_manager is None and USE_KNOWLEDGE_GRAPH:
            try:
                from services.v1.autoedit.graph_manager import get_graph_manager
                self._graph_manager = get_graph_manager()
            except Exception as e:
                logger.error(f"Failed to load graph manager: {e}")
        return self._graph_manager

    def _get_faiss_manager(self):
        """Lazy load FAISS manager."""
        if self._faiss_manager is None and USE_FAISS_SEARCH:
            try:
                from services.v1.autoedit.faiss_manager import get_faiss_manager
                self._faiss_manager = get_faiss_manager()
            except Exception as e:
                logger.error(f"Failed to load FAISS manager: {e}")
        return self._faiss_manager

    def _get_gcs_client(self):
        """Get GCS client."""
        try:
            from google.cloud import storage
            return storage.Client()
        except Exception as e:
            logger.error(f"Failed to create GCS client: {e}")
            return None

    # =========================================================================
    # PROJECT SYNC
    # =========================================================================

    def sync_project_to_graph(
        self,
        project_id: str,
        project_data: Dict[str, Any]
    ) -> bool:
        """
        Sync project data to Neo4j knowledge graph.

        Args:
            project_id: Project identifier
            project_data: Project data from GCS

        Returns:
            True if sync successful
        """
        graph = self._get_graph_manager()
        if not graph or not graph.is_available():
            logger.debug("Neo4j not available, skipping project sync")
            return False

        try:
            # Create or update project node
            graph.create_project_node(
                project_id=project_id,
                name=project_data.get("name", project_id),
                state=project_data.get("state", "unknown"),
                creator_name=project_data.get("creator_name"),
                total_videos=len(project_data.get("workflows", []))
            )

            # Create video nodes and relationships
            workflows = project_data.get("workflows", [])
            for idx, workflow_id in enumerate(workflows):
                workflow_data = project_data.get("workflow_data", {}).get(workflow_id, {})

                graph.create_video_node(
                    workflow_id=workflow_id,
                    project_id=project_id,
                    sequence_index=idx,
                    narrative_function=workflow_data.get("narrative_function"),
                    emotional_tone=workflow_data.get("emotional_tone")
                )

            # Create video sequence relationships
            if len(workflows) > 1:
                graph.create_video_sequence(project_id, workflows)

            logger.info(f"Synced project {project_id} to Neo4j")
            return True

        except Exception as e:
            logger.error(f"Failed to sync project to graph: {e}")
            return False

    def sync_workflow_to_graph(
        self,
        workflow_id: str,
        workflow_data: Dict[str, Any]
    ) -> bool:
        """
        Sync workflow (video) data to Neo4j including segments.

        Args:
            workflow_id: Workflow identifier
            workflow_data: Workflow data from GCS

        Returns:
            True if sync successful
        """
        graph = self._get_graph_manager()
        if not graph or not graph.is_available():
            return False

        try:
            project_id = workflow_data.get("project_id")

            # Create video node if not exists
            graph.create_video_node(
                workflow_id=workflow_id,
                project_id=project_id,
                sequence_index=workflow_data.get("sequence_index", 0),
                narrative_function=workflow_data.get("narrative_function"),
                emotional_tone=workflow_data.get("emotional_tone")
            )

            # Sync segments (blocks)
            blocks = workflow_data.get("blocks", [])
            for block in blocks:
                if block.get("action") == "keep":
                    graph.create_segment_node(
                        segment_id=block.get("id", f"{workflow_id}_{block.get('in')}"),
                        workflow_id=workflow_id,
                        in_ms=block.get("in", 0),
                        out_ms=block.get("out", 0),
                        segment_type=block.get("type", "speech"),
                        action=block.get("action"),
                        text=block.get("text", "")
                    )

            # Extract and sync entities
            entities = self._extract_entities(workflow_data)
            for entity in entities:
                graph.create_entity_node(
                    entity_id=f"{workflow_id}_{entity['name']}",
                    name=entity["name"],
                    entity_type=entity["type"],
                    mention_count=entity.get("count", 1)
                )

            # Extract and sync topics
            topics = self._extract_topics(workflow_data)
            for topic in topics:
                graph.create_topic_node(
                    topic_id=f"{workflow_id}_{topic['name']}",
                    name=topic["name"],
                    category=topic.get("category"),
                    frequency=topic.get("frequency", 1)
                )

            logger.info(f"Synced workflow {workflow_id} to Neo4j")
            return True

        except Exception as e:
            logger.error(f"Failed to sync workflow to graph: {e}")
            return False

    def sync_embeddings_to_faiss(
        self,
        project_id: str,
        embeddings_data: Dict[str, Any]
    ) -> bool:
        """
        Sync TwelveLabs embeddings to FAISS index.

        Args:
            project_id: Project identifier
            embeddings_data: Embeddings data with segment mappings

        Returns:
            True if sync successful
        """
        faiss_mgr = self._get_faiss_manager()
        if not faiss_mgr or not faiss_mgr.is_available():
            logger.debug("FAISS not available, skipping embeddings sync")
            return False

        try:
            import numpy as np

            segments = embeddings_data.get("segments", [])
            if not segments:
                logger.warning(f"No segments to sync for project {project_id}")
                return True

            # Prepare batch
            batch = []
            for segment in segments:
                segment_id = segment.get("segment_id")
                embedding = segment.get("embedding")

                if segment_id and embedding:
                    # Convert to numpy if needed
                    if isinstance(embedding, list):
                        embedding = np.array(embedding, dtype='float32')
                    batch.append((segment_id, embedding))

            if batch:
                faiss_mgr.add_embeddings_batch(project_id, batch)
                faiss_mgr.save_project_index(project_id)

            logger.info(f"Synced {len(batch)} embeddings to FAISS for project {project_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to sync embeddings to FAISS: {e}")
            return False

    # =========================================================================
    # FULL REBUILD
    # =========================================================================

    def rebuild_project_graph(self, project_id: str) -> Dict[str, Any]:
        """
        Rebuild Neo4j graph for a project from GCS data.

        Args:
            project_id: Project identifier

        Returns:
            Sync result with statistics
        """
        result = {
            "project_id": project_id,
            "success": False,
            "nodes_created": 0,
            "relationships_created": 0,
            "errors": []
        }

        graph = self._get_graph_manager()
        if not graph or not graph.is_available():
            result["errors"].append("Neo4j not available")
            return result

        client = self._get_gcs_client()
        if not client:
            result["errors"].append("GCS client not available")
            return result

        try:
            bucket = client.bucket(GCP_BUCKET_NAME)

            # Load project data
            project_blob = bucket.blob(f"projects/{project_id}/project.json")
            if not project_blob.exists():
                result["errors"].append("Project not found in GCS")
                return result

            project_data = json.loads(project_blob.download_as_text())

            # Clear existing project data in Neo4j
            graph.delete_project_graph(project_id)

            # Sync project
            if self.sync_project_to_graph(project_id, project_data):
                result["nodes_created"] += 1

            # Sync each workflow
            workflows = project_data.get("workflows", [])
            for workflow_id in workflows:
                workflow_blob = bucket.blob(f"workflows/{workflow_id}.json")
                if workflow_blob.exists():
                    workflow_data = json.loads(workflow_blob.download_as_text())
                    if self.sync_workflow_to_graph(workflow_id, workflow_data):
                        result["nodes_created"] += 1 + len(workflow_data.get("blocks", []))

            # Load and sync embeddings if available
            embeddings_blob = bucket.blob(f"projects/{project_id}/embeddings.json")
            if embeddings_blob.exists():
                embeddings_data = json.loads(embeddings_blob.download_as_text())

                # Create similarity relationships from embeddings
                segments = embeddings_data.get("segments", [])
                for segment in segments:
                    segment_id = segment.get("segment_id")
                    similar = segment.get("similar_segments", [])
                    for sim in similar:
                        graph.create_similarity_edge(
                            segment_a=segment_id,
                            segment_b=sim["segment_id"],
                            similarity=sim.get("similarity", 0.8)
                        )
                        result["relationships_created"] += 1

            result["success"] = True
            logger.info(f"Rebuilt graph for project {project_id}: "
                       f"{result['nodes_created']} nodes, "
                       f"{result['relationships_created']} relationships")

        except Exception as e:
            result["errors"].append(str(e))
            logger.error(f"Failed to rebuild project graph: {e}")

        return result

    def rebuild_project_faiss(self, project_id: str) -> Dict[str, Any]:
        """
        Rebuild FAISS index for a project from GCS data.

        Args:
            project_id: Project identifier

        Returns:
            Sync result with statistics
        """
        result = {
            "project_id": project_id,
            "success": False,
            "embeddings_indexed": 0,
            "errors": []
        }

        faiss_mgr = self._get_faiss_manager()
        if not faiss_mgr or not faiss_mgr.is_available():
            result["errors"].append("FAISS not available")
            return result

        client = self._get_gcs_client()
        if not client:
            result["errors"].append("GCS client not available")
            return result

        try:
            import numpy as np

            bucket = client.bucket(GCP_BUCKET_NAME)

            # Delete existing index
            faiss_mgr.delete_project_index(project_id)

            # Load embeddings from GCS
            embeddings_blob = bucket.blob(f"projects/{project_id}/embeddings.json")
            if not embeddings_blob.exists():
                # Try loading from individual workflow files
                project_blob = bucket.blob(f"projects/{project_id}/project.json")
                if not project_blob.exists():
                    result["errors"].append("Project not found")
                    return result

                project_data = json.loads(project_blob.download_as_text())
                workflows = project_data.get("workflows", [])

                all_segments = []
                for workflow_id in workflows:
                    wf_emb_blob = bucket.blob(
                        f"workflows/{workflow_id}/embeddings.json"
                    )
                    if wf_emb_blob.exists():
                        wf_emb_data = json.loads(wf_emb_blob.download_as_text())
                        all_segments.extend(wf_emb_data.get("segments", []))

                embeddings_data = {"segments": all_segments}
            else:
                embeddings_data = json.loads(embeddings_blob.download_as_text())

            # Sync to FAISS
            if self.sync_embeddings_to_faiss(project_id, embeddings_data):
                result["embeddings_indexed"] = len(embeddings_data.get("segments", []))
                result["success"] = True

            logger.info(f"Rebuilt FAISS index for project {project_id}: "
                       f"{result['embeddings_indexed']} embeddings")

        except Exception as e:
            result["errors"].append(str(e))
            logger.error(f"Failed to rebuild FAISS index: {e}")

        return result

    def rebuild_all(self, project_id: str) -> Dict[str, Any]:
        """
        Rebuild both Neo4j graph and FAISS index for a project.

        Args:
            project_id: Project identifier

        Returns:
            Combined result
        """
        return {
            "project_id": project_id,
            "graph": self.rebuild_project_graph(project_id),
            "faiss": self.rebuild_project_faiss(project_id),
            "timestamp": datetime.utcnow().isoformat()
        }

    # =========================================================================
    # INCREMENTAL UPDATES
    # =========================================================================

    def on_workflow_updated(
        self,
        workflow_id: str,
        workflow_data: Dict[str, Any]
    ) -> bool:
        """
        Handle workflow update event.

        Called when a workflow is modified in GCS. Updates Neo4j and FAISS.

        Args:
            workflow_id: Updated workflow
            workflow_data: New workflow data

        Returns:
            True if all syncs successful
        """
        success = True

        # Update graph
        if not self.sync_workflow_to_graph(workflow_id, workflow_data):
            success = False

        # Update FAISS if embeddings present
        project_id = workflow_data.get("project_id")
        if project_id and "embeddings" in workflow_data:
            embeddings_data = {
                "segments": workflow_data.get("embeddings", [])
            }
            if not self.sync_embeddings_to_faiss(project_id, embeddings_data):
                success = False

        return success

    def on_project_updated(
        self,
        project_id: str,
        project_data: Dict[str, Any]
    ) -> bool:
        """
        Handle project update event.

        Args:
            project_id: Updated project
            project_data: New project data

        Returns:
            True if sync successful
        """
        return self.sync_project_to_graph(project_id, project_data)

    def on_embeddings_generated(
        self,
        project_id: str,
        embeddings_data: Dict[str, Any]
    ) -> bool:
        """
        Handle new embeddings event.

        Called after TwelveLabs generates embeddings.

        Args:
            project_id: Project identifier
            embeddings_data: New embeddings

        Returns:
            True if sync successful
        """
        success = True

        # Sync to FAISS
        if not self.sync_embeddings_to_faiss(project_id, embeddings_data):
            success = False

        # Create similarity edges in graph
        graph = self._get_graph_manager()
        faiss_mgr = self._get_faiss_manager()

        if graph and graph.is_available() and faiss_mgr and faiss_mgr.is_available():
            # Find redundant pairs and create edges
            pairs = faiss_mgr.find_redundant_pairs(project_id, threshold=0.8)
            for pair in pairs:
                graph.create_similarity_edge(
                    segment_a=pair["segment_a"],
                    segment_b=pair["segment_b"],
                    similarity=pair["similarity"]
                )

        return success

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _extract_entities(self, workflow_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract named entities from workflow data.

        Args:
            workflow_data: Workflow with transcription

        Returns:
            List of entity dictionaries
        """
        entities = []

        # Check for explicit entity annotations
        if "entities" in workflow_data:
            return workflow_data["entities"]

        # Extract from analysis if available
        analysis = workflow_data.get("analysis", {})
        if "entities" in analysis:
            return analysis["entities"]

        # Basic extraction from blocks text
        blocks = workflow_data.get("blocks", [])
        entity_counts = {}

        for block in blocks:
            text = block.get("text", "")
            # Very basic: extract capitalized words as potential entities
            # Real implementation would use NER
            words = text.split()
            for word in words:
                if word and word[0].isupper() and len(word) > 2:
                    clean = word.strip(".,!?\"'")
                    if clean:
                        entity_counts[clean] = entity_counts.get(clean, 0) + 1

        for name, count in entity_counts.items():
            if count >= 2:  # Only include if mentioned more than once
                entities.append({
                    "name": name,
                    "type": "unknown",
                    "count": count
                })

        return entities

    def _extract_topics(self, workflow_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract topics from workflow data.

        Args:
            workflow_data: Workflow with analysis

        Returns:
            List of topic dictionaries
        """
        topics = []

        # Check for explicit topic annotations
        if "topics" in workflow_data:
            return workflow_data["topics"]

        # Extract from analysis
        analysis = workflow_data.get("analysis", {})
        if "topics" in analysis:
            return analysis["topics"]

        if "main_topics" in analysis:
            for topic in analysis["main_topics"]:
                topics.append({
                    "name": topic,
                    "category": "main",
                    "frequency": 1
                })

        return topics


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_sync_manager = None


def get_sync_manager() -> DataSyncManager:
    """Get the singleton DataSyncManager instance."""
    global _sync_manager
    if _sync_manager is None:
        _sync_manager = DataSyncManager()
    return _sync_manager


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def sync_workflow(workflow_id: str, workflow_data: Dict[str, Any]) -> bool:
    """Sync a workflow to Neo4j and FAISS."""
    manager = get_sync_manager()
    return manager.on_workflow_updated(workflow_id, workflow_data)


def sync_project(project_id: str, project_data: Dict[str, Any]) -> bool:
    """Sync a project to Neo4j."""
    manager = get_sync_manager()
    return manager.on_project_updated(project_id, project_data)


def sync_embeddings(project_id: str, embeddings_data: Dict[str, Any]) -> bool:
    """Sync embeddings to FAISS and create similarity edges."""
    manager = get_sync_manager()
    return manager.on_embeddings_generated(project_id, embeddings_data)


def rebuild_project_indexes(project_id: str) -> Dict[str, Any]:
    """Rebuild all indexes for a project from GCS."""
    manager = get_sync_manager()
    return manager.rebuild_all(project_id)
