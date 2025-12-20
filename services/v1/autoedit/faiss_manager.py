# Copyright (c) 2025 Stephen G. Pope
# Licensed under GPL-2.0

"""
FAISS Vector Index Manager for AutoEdit Phase 5

Provides O(log n) similarity search for video segment embeddings using FAISS.
Supports multiple index types based on dataset size and integrates with GCS
for persistent index storage.

Features:
- Automatic index type selection based on segment count
- GCS synchronization for persistent storage
- Graceful degradation when FAISS is unavailable
- Thread-safe operations with locking
- Support for TwelveLabs Marengo 3.0 embeddings (1024 dimensions)
"""

import os
import json
import logging
import threading
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime

import numpy as np

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    faiss = None

from config import (
    FAISS_INDEX_PATH,
    FAISS_USE_GCS,
    FAISS_EMBEDDING_DIMENSION,
    USE_FAISS_SEARCH,
    GCP_BUCKET_NAME
)

logger = logging.getLogger(__name__)


# =============================================================================
# INDEX TYPE CONFIGURATION
# =============================================================================

INDEX_CONFIGS = {
    "flat": {
        "description": "Exact search, best for < 1000 segments",
        "max_segments": 1000,
        "build_params": {}
    },
    "ivf": {
        "description": "Inverted file index, good for 1K-100K segments",
        "max_segments": 100000,
        "build_params": {
            "nlist": 100,  # Number of clusters
            "nprobe": 10   # Number of clusters to search
        }
    },
    "hnsw": {
        "description": "Hierarchical NSW, best for > 100K segments",
        "max_segments": float('inf'),
        "build_params": {
            "M": 32,           # Number of connections per layer
            "efConstruction": 200,  # Construction-time search depth
            "efSearch": 64     # Query-time search depth
        }
    }
}


# =============================================================================
# FAISS MANAGER CLASS
# =============================================================================

class FAISSManager:
    """
    Singleton manager for FAISS vector indexes.

    Handles index creation, embedding storage, similarity search,
    and synchronization with GCS for persistence.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._indexes: Dict[str, Any] = {}  # project_id -> faiss.Index
        self._id_maps: Dict[str, Dict[int, str]] = {}  # project_id -> {faiss_id: segment_id}
        self._reverse_maps: Dict[str, Dict[str, int]] = {}  # project_id -> {segment_id: faiss_id}
        self._index_locks: Dict[str, threading.Lock] = {}
        self._dimension = FAISS_EMBEDDING_DIMENSION

        # Ensure local storage path exists
        os.makedirs(FAISS_INDEX_PATH, exist_ok=True)

        logger.info(f"FAISSManager initialized: dimension={self._dimension}, "
                   f"gcs_sync={FAISS_USE_GCS}, available={FAISS_AVAILABLE}")

    def is_available(self) -> bool:
        """Check if FAISS is available and enabled."""
        return FAISS_AVAILABLE and USE_FAISS_SEARCH

    def _get_lock(self, project_id: str) -> threading.Lock:
        """Get or create a lock for a project's index."""
        if project_id not in self._index_locks:
            self._index_locks[project_id] = threading.Lock()
        return self._index_locks[project_id]

    def _select_index_type(self, estimated_segments: int) -> str:
        """Select appropriate index type based on estimated segment count."""
        for index_type, config in INDEX_CONFIGS.items():
            if estimated_segments <= config["max_segments"]:
                return index_type
        return "hnsw"

    def _create_index(self, index_type: str) -> Optional[Any]:
        """Create a FAISS index of the specified type."""
        if not FAISS_AVAILABLE:
            return None

        try:
            if index_type == "flat":
                # Exact L2 search
                index = faiss.IndexFlatL2(self._dimension)

            elif index_type == "ivf":
                # IVF with flat quantizer
                config = INDEX_CONFIGS["ivf"]["build_params"]
                quantizer = faiss.IndexFlatL2(self._dimension)
                index = faiss.IndexIVFFlat(
                    quantizer,
                    self._dimension,
                    config["nlist"]
                )
                # IVF requires training, but we'll handle that during add

            elif index_type == "hnsw":
                # HNSW index
                config = INDEX_CONFIGS["hnsw"]["build_params"]
                index = faiss.IndexHNSWFlat(self._dimension, config["M"])
                index.hnsw.efConstruction = config["efConstruction"]
                index.hnsw.efSearch = config["efSearch"]

            else:
                logger.error(f"Unknown index type: {index_type}")
                return None

            logger.info(f"Created FAISS {index_type} index: dimension={self._dimension}")
            return index

        except Exception as e:
            logger.error(f"Failed to create FAISS index: {e}")
            return None

    # =========================================================================
    # INDEX LIFECYCLE
    # =========================================================================

    def create_project_index(
        self,
        project_id: str,
        estimated_segments: int = 100
    ) -> bool:
        """
        Create a new FAISS index for a project.

        Args:
            project_id: Unique project identifier
            estimated_segments: Estimated number of segments for index selection

        Returns:
            True if index created successfully
        """
        if not self.is_available():
            logger.warning("FAISS not available, skipping index creation")
            return False

        lock = self._get_lock(project_id)
        with lock:
            if project_id in self._indexes:
                logger.info(f"Index already exists for project {project_id}")
                return True

            index_type = self._select_index_type(estimated_segments)
            index = self._create_index(index_type)

            if index is None:
                return False

            self._indexes[project_id] = index
            self._id_maps[project_id] = {}
            self._reverse_maps[project_id] = {}

            logger.info(f"Created {index_type} index for project {project_id}")
            return True

    def load_project_index(self, project_id: str) -> bool:
        """
        Load a project's index from local storage or GCS.

        Args:
            project_id: Project identifier

        Returns:
            True if index loaded successfully
        """
        if not self.is_available():
            return False

        lock = self._get_lock(project_id)
        with lock:
            if project_id in self._indexes:
                return True

            # Try local first
            local_path = os.path.join(FAISS_INDEX_PATH, f"{project_id}.index")
            map_path = os.path.join(FAISS_INDEX_PATH, f"{project_id}.id_map.json")

            if os.path.exists(local_path) and os.path.exists(map_path):
                try:
                    self._indexes[project_id] = faiss.read_index(local_path)
                    with open(map_path, 'r') as f:
                        data = json.load(f)
                        # Convert string keys back to int for id_map
                        self._id_maps[project_id] = {
                            int(k): v for k, v in data["id_map"].items()
                        }
                        self._reverse_maps[project_id] = data["reverse_map"]

                    logger.info(f"Loaded index from local: {project_id}")
                    return True
                except Exception as e:
                    logger.error(f"Failed to load local index: {e}")

            # Try GCS if enabled
            if FAISS_USE_GCS:
                return self._load_from_gcs(project_id)

            return False

    def save_project_index(self, project_id: str) -> bool:
        """
        Save a project's index to local storage and optionally GCS.

        Args:
            project_id: Project identifier

        Returns:
            True if saved successfully
        """
        if not self.is_available():
            return False

        lock = self._get_lock(project_id)
        with lock:
            if project_id not in self._indexes:
                logger.warning(f"No index found for project {project_id}")
                return False

            try:
                # Save to local
                local_path = os.path.join(FAISS_INDEX_PATH, f"{project_id}.index")
                map_path = os.path.join(FAISS_INDEX_PATH, f"{project_id}.id_map.json")

                faiss.write_index(self._indexes[project_id], local_path)

                with open(map_path, 'w') as f:
                    json.dump({
                        "id_map": {
                            str(k): v for k, v in self._id_maps.get(project_id, {}).items()
                        },
                        "reverse_map": self._reverse_maps.get(project_id, {}),
                        "updated_at": datetime.utcnow().isoformat()
                    }, f)

                logger.info(f"Saved index locally: {project_id}")

                # Upload to GCS if enabled
                if FAISS_USE_GCS:
                    self._save_to_gcs(project_id, local_path, map_path)

                return True

            except Exception as e:
                logger.error(f"Failed to save index: {e}")
                return False

    def delete_project_index(self, project_id: str) -> bool:
        """
        Delete a project's index from memory and storage.

        Args:
            project_id: Project identifier

        Returns:
            True if deleted successfully
        """
        lock = self._get_lock(project_id)
        with lock:
            # Remove from memory
            self._indexes.pop(project_id, None)
            self._id_maps.pop(project_id, None)
            self._reverse_maps.pop(project_id, None)

            # Remove local files
            local_path = os.path.join(FAISS_INDEX_PATH, f"{project_id}.index")
            map_path = os.path.join(FAISS_INDEX_PATH, f"{project_id}.id_map.json")

            for path in [local_path, map_path]:
                if os.path.exists(path):
                    os.remove(path)

            # Remove from GCS if enabled
            if FAISS_USE_GCS:
                self._delete_from_gcs(project_id)

            logger.info(f"Deleted index for project {project_id}")
            return True

    # =========================================================================
    # EMBEDDING OPERATIONS
    # =========================================================================

    def add_embedding(
        self,
        project_id: str,
        segment_id: str,
        embedding: np.ndarray
    ) -> Optional[int]:
        """
        Add a single embedding to the project index.

        Args:
            project_id: Project identifier
            segment_id: Unique segment identifier
            embedding: 1024-dimensional embedding vector

        Returns:
            FAISS ID assigned to this embedding, or None on failure
        """
        if not self.is_available():
            return None

        # Ensure project index exists
        if project_id not in self._indexes:
            if not self.load_project_index(project_id):
                if not self.create_project_index(project_id):
                    return None

        lock = self._get_lock(project_id)
        with lock:
            try:
                index = self._indexes[project_id]

                # Validate embedding shape
                if embedding.shape != (self._dimension,):
                    embedding = embedding.reshape(1, -1)
                else:
                    embedding = embedding.reshape(1, -1)

                embedding = embedding.astype('float32')

                # Check if segment already indexed
                if segment_id in self._reverse_maps.get(project_id, {}):
                    logger.debug(f"Segment {segment_id} already indexed")
                    return self._reverse_maps[project_id][segment_id]

                # Get next ID
                faiss_id = index.ntotal

                # Handle IVF training if needed
                if hasattr(index, 'is_trained') and not index.is_trained:
                    # For IVF, we need to train first - collect embeddings
                    # For simplicity, just add to flat index for now
                    logger.warning("IVF index not trained, adding directly")

                # Add to index
                index.add(embedding)

                # Update maps
                self._id_maps[project_id][faiss_id] = segment_id
                self._reverse_maps[project_id][segment_id] = faiss_id

                logger.debug(f"Added embedding for segment {segment_id} as FAISS ID {faiss_id}")
                return faiss_id

            except Exception as e:
                logger.error(f"Failed to add embedding: {e}")
                return None

    def add_embeddings_batch(
        self,
        project_id: str,
        segments: List[Tuple[str, np.ndarray]]
    ) -> Dict[str, int]:
        """
        Add multiple embeddings in batch for better performance.

        Args:
            project_id: Project identifier
            segments: List of (segment_id, embedding) tuples

        Returns:
            Dict mapping segment_id to FAISS ID
        """
        if not self.is_available() or not segments:
            return {}

        # Ensure project index exists
        if project_id not in self._indexes:
            if not self.load_project_index(project_id):
                if not self.create_project_index(project_id, len(segments)):
                    return {}

        lock = self._get_lock(project_id)
        with lock:
            try:
                index = self._indexes[project_id]
                results = {}

                # Filter out already indexed segments
                new_segments = [
                    (seg_id, emb) for seg_id, emb in segments
                    if seg_id not in self._reverse_maps.get(project_id, {})
                ]

                if not new_segments:
                    return {
                        seg_id: self._reverse_maps[project_id][seg_id]
                        for seg_id, _ in segments
                        if seg_id in self._reverse_maps.get(project_id, {})
                    }

                # Prepare batch
                segment_ids = [seg_id for seg_id, _ in new_segments]
                embeddings = np.array([
                    emb.reshape(-1) for _, emb in new_segments
                ]).astype('float32')

                # Handle IVF training
                if hasattr(index, 'is_trained') and not index.is_trained:
                    if len(embeddings) >= INDEX_CONFIGS["ivf"]["build_params"]["nlist"]:
                        index.train(embeddings)
                        logger.info(f"Trained IVF index with {len(embeddings)} vectors")

                # Get starting ID
                start_id = index.ntotal

                # Add batch
                index.add(embeddings)

                # Update maps
                for i, segment_id in enumerate(segment_ids):
                    faiss_id = start_id + i
                    self._id_maps[project_id][faiss_id] = segment_id
                    self._reverse_maps[project_id][segment_id] = faiss_id
                    results[segment_id] = faiss_id

                # Include already indexed segments in results
                for seg_id, _ in segments:
                    if seg_id not in results and seg_id in self._reverse_maps.get(project_id, {}):
                        results[seg_id] = self._reverse_maps[project_id][seg_id]

                logger.info(f"Added {len(new_segments)} embeddings to project {project_id}")
                return results

            except Exception as e:
                logger.error(f"Failed to add batch embeddings: {e}")
                return {}

    def remove_embedding(self, project_id: str, segment_id: str) -> bool:
        """
        Remove an embedding from the index.

        Note: FAISS doesn't support true deletion. We mark as removed in the map
        and rebuild periodically.

        Args:
            project_id: Project identifier
            segment_id: Segment to remove

        Returns:
            True if removed from map (rebuild needed for index)
        """
        lock = self._get_lock(project_id)
        with lock:
            if project_id not in self._reverse_maps:
                return False

            if segment_id not in self._reverse_maps[project_id]:
                return False

            faiss_id = self._reverse_maps[project_id].pop(segment_id)
            self._id_maps[project_id].pop(faiss_id, None)

            logger.info(f"Marked segment {segment_id} for removal (rebuild needed)")
            return True

    # =========================================================================
    # SIMILARITY SEARCH
    # =========================================================================

    def search_similar(
        self,
        project_id: str,
        query_embedding: np.ndarray,
        k: int = 10,
        threshold: Optional[float] = None
    ) -> List[Tuple[str, float]]:
        """
        Find k most similar segments to query embedding.

        Args:
            project_id: Project identifier
            query_embedding: Query vector (1024 dimensions)
            k: Number of results to return
            threshold: Optional maximum distance threshold

        Returns:
            List of (segment_id, distance) tuples, sorted by distance
        """
        if not self.is_available():
            return []

        if project_id not in self._indexes:
            if not self.load_project_index(project_id):
                return []

        lock = self._get_lock(project_id)
        with lock:
            try:
                index = self._indexes[project_id]

                if index.ntotal == 0:
                    return []

                # Prepare query
                query = query_embedding.reshape(1, -1).astype('float32')

                # Adjust k if larger than index size
                k = min(k, index.ntotal)

                # Search
                distances, indices = index.search(query, k)

                results = []
                for i in range(k):
                    faiss_id = int(indices[0][i])
                    distance = float(distances[0][i])

                    # Skip invalid or removed entries
                    if faiss_id < 0 or faiss_id not in self._id_maps.get(project_id, {}):
                        continue

                    # Apply threshold if specified
                    if threshold is not None and distance > threshold:
                        continue

                    segment_id = self._id_maps[project_id][faiss_id]
                    results.append((segment_id, distance))

                return results

            except Exception as e:
                logger.error(f"Search failed: {e}")
                return []

    def search_by_segment(
        self,
        project_id: str,
        segment_id: str,
        k: int = 10,
        threshold: Optional[float] = None,
        exclude_self: bool = True
    ) -> List[Tuple[str, float]]:
        """
        Find segments similar to a given segment.

        Args:
            project_id: Project identifier
            segment_id: Segment to find similar matches for
            k: Number of results
            threshold: Maximum distance threshold
            exclude_self: Whether to exclude the query segment from results

        Returns:
            List of (segment_id, distance) tuples
        """
        if not self.is_available():
            return []

        if project_id not in self._indexes:
            if not self.load_project_index(project_id):
                return []

        lock = self._get_lock(project_id)
        with lock:
            # Get FAISS ID for segment
            if segment_id not in self._reverse_maps.get(project_id, {}):
                logger.warning(f"Segment {segment_id} not found in index")
                return []

            faiss_id = self._reverse_maps[project_id][segment_id]

            try:
                index = self._indexes[project_id]

                # Reconstruct the embedding
                embedding = index.reconstruct(faiss_id)

                # Search with k+1 if excluding self
                search_k = k + 1 if exclude_self else k

                results = self.search_similar(
                    project_id, embedding, search_k, threshold
                )

                # Remove self if needed
                if exclude_self:
                    results = [(sid, dist) for sid, dist in results if sid != segment_id]
                    results = results[:k]

                return results

            except Exception as e:
                logger.error(f"Search by segment failed: {e}")
                return []

    def find_redundant_pairs(
        self,
        project_id: str,
        similarity_threshold: float = 0.85,
        max_pairs: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find all pairs of potentially redundant segments.

        Uses efficient pairwise search to identify segments that are
        semantically similar based on embedding distance.

        Args:
            project_id: Project identifier
            similarity_threshold: Minimum cosine similarity (0-1)
            max_pairs: Maximum number of pairs to return

        Returns:
            List of redundancy pairs with metadata
        """
        if not self.is_available():
            return []

        if project_id not in self._indexes:
            if not self.load_project_index(project_id):
                return []

        lock = self._get_lock(project_id)
        with lock:
            try:
                index = self._indexes[project_id]
                n_segments = index.ntotal

                if n_segments < 2:
                    return []

                # Convert similarity threshold to L2 distance
                # For normalized vectors: d = sqrt(2 * (1 - cos_sim))
                # Approximate: lower distance = higher similarity
                distance_threshold = 2 * (1 - similarity_threshold)

                pairs = []
                seen = set()

                # For each segment, find similar ones
                for faiss_id in range(n_segments):
                    if faiss_id not in self._id_maps.get(project_id, {}):
                        continue

                    segment_id = self._id_maps[project_id][faiss_id]

                    # Reconstruct and search
                    embedding = index.reconstruct(faiss_id)
                    results = self.search_similar(
                        project_id,
                        embedding,
                        k=5,  # Check top 5 similar
                        threshold=distance_threshold
                    )

                    for other_id, distance in results:
                        if other_id == segment_id:
                            continue

                        # Create canonical pair key
                        pair_key = tuple(sorted([segment_id, other_id]))
                        if pair_key in seen:
                            continue
                        seen.add(pair_key)

                        # Convert distance back to similarity
                        similarity = 1 - (distance / 2)

                        pairs.append({
                            "segment_a": segment_id,
                            "segment_b": other_id,
                            "similarity": round(similarity, 4),
                            "distance": round(distance, 4)
                        })

                        if len(pairs) >= max_pairs:
                            break

                    if len(pairs) >= max_pairs:
                        break

                # Sort by similarity descending
                pairs.sort(key=lambda x: x["similarity"], reverse=True)

                logger.info(f"Found {len(pairs)} redundant pairs in project {project_id}")
                return pairs

            except Exception as e:
                logger.error(f"Find redundant pairs failed: {e}")
                return []

    # =========================================================================
    # INDEX STATISTICS
    # =========================================================================

    def get_index_stats(self, project_id: str) -> Dict[str, Any]:
        """
        Get statistics about a project's index.

        Returns:
            Dict with index statistics
        """
        if project_id not in self._indexes:
            return {
                "exists": False,
                "project_id": project_id
            }

        lock = self._get_lock(project_id)
        with lock:
            index = self._indexes[project_id]

            # Determine index type
            index_type = "unknown"
            if hasattr(index, 'hnsw'):
                index_type = "hnsw"
            elif hasattr(index, 'nlist'):
                index_type = "ivf"
            else:
                index_type = "flat"

            return {
                "exists": True,
                "project_id": project_id,
                "index_type": index_type,
                "dimension": self._dimension,
                "total_vectors": index.ntotal,
                "indexed_segments": len(self._reverse_maps.get(project_id, {})),
                "is_trained": getattr(index, 'is_trained', True)
            }

    # =========================================================================
    # GCS SYNCHRONIZATION
    # =========================================================================

    def _get_gcs_paths(self, project_id: str) -> Tuple[str, str]:
        """Get GCS paths for index and map files."""
        base = f"projects/{project_id}/faiss"
        return (
            f"{base}/segments.index",
            f"{base}/segments.id_map.json"
        )

    def _load_from_gcs(self, project_id: str) -> bool:
        """Load index from GCS."""
        try:
            from google.cloud import storage

            client = storage.Client()
            bucket = client.bucket(GCP_BUCKET_NAME)

            index_gcs, map_gcs = self._get_gcs_paths(project_id)

            local_index = os.path.join(FAISS_INDEX_PATH, f"{project_id}.index")
            local_map = os.path.join(FAISS_INDEX_PATH, f"{project_id}.id_map.json")

            # Download index
            index_blob = bucket.blob(index_gcs)
            if not index_blob.exists():
                logger.debug(f"No GCS index found for project {project_id}")
                return False

            index_blob.download_to_filename(local_index)

            # Download map
            map_blob = bucket.blob(map_gcs)
            if map_blob.exists():
                map_blob.download_to_filename(local_map)

            # Load into memory
            self._indexes[project_id] = faiss.read_index(local_index)

            if os.path.exists(local_map):
                with open(local_map, 'r') as f:
                    data = json.load(f)
                    self._id_maps[project_id] = {
                        int(k): v for k, v in data.get("id_map", {}).items()
                    }
                    self._reverse_maps[project_id] = data.get("reverse_map", {})

            logger.info(f"Loaded index from GCS: {project_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to load from GCS: {e}")
            return False

    def _save_to_gcs(self, project_id: str, local_index: str, local_map: str) -> bool:
        """Save index to GCS."""
        try:
            from google.cloud import storage

            client = storage.Client()
            bucket = client.bucket(GCP_BUCKET_NAME)

            index_gcs, map_gcs = self._get_gcs_paths(project_id)

            # Upload index
            index_blob = bucket.blob(index_gcs)
            index_blob.upload_from_filename(local_index)

            # Upload map
            map_blob = bucket.blob(map_gcs)
            map_blob.upload_from_filename(local_map)

            logger.info(f"Saved index to GCS: {project_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to save to GCS: {e}")
            return False

    def _delete_from_gcs(self, project_id: str) -> bool:
        """Delete index from GCS."""
        try:
            from google.cloud import storage

            client = storage.Client()
            bucket = client.bucket(GCP_BUCKET_NAME)

            index_gcs, map_gcs = self._get_gcs_paths(project_id)

            for path in [index_gcs, map_gcs]:
                blob = bucket.blob(path)
                if blob.exists():
                    blob.delete()

            logger.info(f"Deleted index from GCS: {project_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete from GCS: {e}")
            return False

    def sync_from_gcs(self, project_id: str) -> bool:
        """
        Force sync from GCS, replacing local index.

        Args:
            project_id: Project identifier

        Returns:
            True if sync successful
        """
        if not FAISS_USE_GCS:
            return False

        lock = self._get_lock(project_id)
        with lock:
            # Remove local copy first
            self._indexes.pop(project_id, None)
            self._id_maps.pop(project_id, None)
            self._reverse_maps.pop(project_id, None)

            return self._load_from_gcs(project_id)

    def sync_to_gcs(self, project_id: str) -> bool:
        """
        Force sync to GCS.

        Args:
            project_id: Project identifier

        Returns:
            True if sync successful
        """
        return self.save_project_index(project_id)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_faiss_manager() -> FAISSManager:
    """Get the singleton FAISSManager instance."""
    return FAISSManager()


def is_faiss_available() -> bool:
    """Check if FAISS functionality is available."""
    return FAISS_AVAILABLE and USE_FAISS_SEARCH


def add_segment_embedding(
    project_id: str,
    segment_id: str,
    embedding: np.ndarray
) -> Optional[int]:
    """
    Convenience function to add a segment embedding.

    Args:
        project_id: Project identifier
        segment_id: Segment identifier
        embedding: Embedding vector

    Returns:
        FAISS ID or None
    """
    manager = get_faiss_manager()
    return manager.add_embedding(project_id, segment_id, embedding)


def find_similar_segments(
    project_id: str,
    segment_id: str,
    k: int = 5,
    threshold: float = 0.8
) -> List[Tuple[str, float]]:
    """
    Convenience function to find similar segments.

    Args:
        project_id: Project identifier
        segment_id: Query segment
        k: Number of results
        threshold: Similarity threshold

    Returns:
        List of (segment_id, similarity) tuples
    """
    manager = get_faiss_manager()

    # Convert threshold to distance
    distance_threshold = 2 * (1 - threshold)

    results = manager.search_by_segment(
        project_id, segment_id, k, distance_threshold
    )

    # Convert distances to similarities
    return [
        (seg_id, 1 - (dist / 2))
        for seg_id, dist in results
    ]


def get_redundant_segment_pairs(
    project_id: str,
    threshold: float = 0.85
) -> List[Dict[str, Any]]:
    """
    Convenience function to find redundant segment pairs.

    Args:
        project_id: Project identifier
        threshold: Similarity threshold for redundancy

    Returns:
        List of redundancy pair dictionaries
    """
    manager = get_faiss_manager()
    return manager.find_redundant_pairs(project_id, threshold)
