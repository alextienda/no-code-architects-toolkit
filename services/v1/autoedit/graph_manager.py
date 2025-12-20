"""
Neo4j Knowledge Graph Manager for AutoEdit Phase 5.

Provides CRUD operations for the knowledge graph containing:
- Projects, Videos, Segments, Entities, Topics
- Relationships: CONTAINS, HAS_SEGMENT, MENTIONS, COVERS, SIMILAR_TO, FOLLOWED_BY

This is a derived view from GCS (source of truth). Use data_sync.py for synchronization.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import json

try:
    from neo4j import GraphDatabase, Driver
    from neo4j.exceptions import ServiceUnavailable, AuthError
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    GraphDatabase = None
    Driver = None

from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, USE_KNOWLEDGE_GRAPH

logger = logging.getLogger(__name__)


class Neo4jManager:
    """
    Manages Neo4j connection and graph operations for AutoEdit.

    Node Types:
        - Project: Multi-video project container
        - Video: Individual video (workflow)
        - Segment: A-Roll or B-Roll segment
        - Entity: Named entities from transcripts (PERSON, LOCATION, PRODUCT, etc.)
        - Topic: Themes and subjects covered

    Relationship Types:
        - CONTAINS: Project -> Video
        - HAS_SEGMENT: Video -> Segment
        - MENTIONS: Segment -> Entity
        - COVERS: Video -> Topic
        - DISCUSSES: Segment -> Topic
        - SIMILAR_TO: Segment -> Segment (redundancy)
        - FOLLOWED_BY: Video -> Video (sequence)
    """

    _instance: Optional['Neo4jManager'] = None
    _driver: Optional[Driver] = None

    def __new__(cls):
        """Singleton pattern for connection pooling."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize Neo4j connection."""
        if not NEO4J_AVAILABLE:
            logger.warning("neo4j package not installed. Knowledge graph features disabled.")
            return

        if not USE_KNOWLEDGE_GRAPH:
            logger.info("Knowledge graph disabled via USE_KNOWLEDGE_GRAPH=false")
            return

        if self._driver is None and NEO4J_PASSWORD:
            try:
                self._driver = GraphDatabase.driver(
                    NEO4J_URI,
                    auth=(NEO4J_USER, NEO4J_PASSWORD)
                )
                # Verify connection
                self._driver.verify_connectivity()
                logger.info(f"Connected to Neo4j at {NEO4J_URI}")
            except (ServiceUnavailable, AuthError) as e:
                logger.error(f"Failed to connect to Neo4j: {e}")
                self._driver = None

    @property
    def is_available(self) -> bool:
        """Check if Neo4j connection is available."""
        return self._driver is not None

    def close(self):
        """Close the Neo4j connection."""
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")

    # =========================================================================
    # PROJECT OPERATIONS
    # =========================================================================

    def create_project_node(self, project_data: Dict[str, Any]) -> Optional[str]:
        """
        Create a Project node.

        Args:
            project_data: Dict with keys:
                - project_id (required)
                - name
                - description
                - state
                - creator_name
                - total_videos

        Returns:
            project_id if successful, None otherwise
        """
        if not self.is_available:
            return None

        query = """
        MERGE (p:Project {project_id: $project_id})
        SET p.name = $name,
            p.description = $description,
            p.state = $state,
            p.creator_name = $creator_name,
            p.total_videos = $total_videos,
            p.updated_at = datetime()
        ON CREATE SET p.created_at = datetime()
        RETURN p.project_id AS project_id
        """

        try:
            with self._driver.session() as session:
                result = session.run(query, {
                    "project_id": project_data.get("project_id"),
                    "name": project_data.get("name", ""),
                    "description": project_data.get("description", ""),
                    "state": project_data.get("state", "created"),
                    "creator_name": project_data.get("creator_name", ""),
                    "total_videos": project_data.get("total_videos", 0)
                })
                record = result.single()
                return record["project_id"] if record else None
        except Exception as e:
            logger.error(f"Error creating project node: {e}")
            return None

    def get_project_node(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get a Project node by ID."""
        if not self.is_available:
            return None

        query = """
        MATCH (p:Project {project_id: $project_id})
        RETURN p
        """

        try:
            with self._driver.session() as session:
                result = session.run(query, {"project_id": project_id})
                record = result.single()
                return dict(record["p"]) if record else None
        except Exception as e:
            logger.error(f"Error getting project node: {e}")
            return None

    # =========================================================================
    # VIDEO OPERATIONS
    # =========================================================================

    def create_video_node(self, video_data: Dict[str, Any]) -> Optional[str]:
        """
        Create a Video node and link to Project.

        Args:
            video_data: Dict with keys:
                - workflow_id (required)
                - project_id (required for linking)
                - sequence_index
                - video_url
                - duration_ms
                - narrative_function
                - emotional_tone
                - summary
                - status

        Returns:
            workflow_id if successful, None otherwise
        """
        if not self.is_available:
            return None

        query = """
        MERGE (v:Video {workflow_id: $workflow_id})
        SET v.project_id = $project_id,
            v.sequence_index = $sequence_index,
            v.video_url = $video_url,
            v.duration_ms = $duration_ms,
            v.narrative_function = $narrative_function,
            v.emotional_tone = $emotional_tone,
            v.summary = $summary,
            v.status = $status,
            v.updated_at = datetime()
        ON CREATE SET v.created_at = datetime()

        WITH v
        MATCH (p:Project {project_id: $project_id})
        MERGE (p)-[r:CONTAINS]->(v)
        SET r.sequence_index = $sequence_index,
            r.added_at = datetime()

        RETURN v.workflow_id AS workflow_id
        """

        try:
            with self._driver.session() as session:
                result = session.run(query, {
                    "workflow_id": video_data.get("workflow_id"),
                    "project_id": video_data.get("project_id"),
                    "sequence_index": video_data.get("sequence_index", 0),
                    "video_url": video_data.get("video_url", ""),
                    "duration_ms": video_data.get("duration_ms", 0),
                    "narrative_function": video_data.get("narrative_function", ""),
                    "emotional_tone": video_data.get("emotional_tone", ""),
                    "summary": video_data.get("summary", ""),
                    "status": video_data.get("status", "")
                })
                record = result.single()
                return record["workflow_id"] if record else None
        except Exception as e:
            logger.error(f"Error creating video node: {e}")
            return None

    def create_video_sequence(self, project_id: str, workflow_ids: List[str]) -> bool:
        """
        Create FOLLOWED_BY relationships between videos in sequence order.

        Args:
            project_id: Project ID
            workflow_ids: List of workflow IDs in sequence order

        Returns:
            True if successful
        """
        if not self.is_available or len(workflow_ids) < 2:
            return False

        query = """
        UNWIND range(0, size($workflow_ids) - 2) AS i
        MATCH (v1:Video {workflow_id: $workflow_ids[i]})
        MATCH (v2:Video {workflow_id: $workflow_ids[i + 1]})
        MERGE (v1)-[r:FOLLOWED_BY]->(v2)
        SET r.transition_type = 'sequence',
            r.created_at = datetime()
        RETURN count(r) AS relationships_created
        """

        try:
            with self._driver.session() as session:
                result = session.run(query, {"workflow_ids": workflow_ids})
                record = result.single()
                return record["relationships_created"] > 0 if record else False
        except Exception as e:
            logger.error(f"Error creating video sequence: {e}")
            return False

    # =========================================================================
    # SEGMENT OPERATIONS
    # =========================================================================

    def create_segment_node(self, segment_data: Dict[str, Any]) -> Optional[str]:
        """
        Create a Segment node and link to Video.

        Args:
            segment_data: Dict with keys:
                - segment_id (required)
                - workflow_id (required for linking)
                - in_ms, out_ms, duration_ms
                - type (A-Roll, B-Roll)
                - category (for B-Roll)
                - action (keep, remove)
                - text (transcript)
                - description
                - faiss_id (for vector search)

        Returns:
            segment_id if successful
        """
        if not self.is_available:
            return None

        query = """
        MERGE (s:Segment {segment_id: $segment_id})
        SET s.workflow_id = $workflow_id,
            s.in_ms = $in_ms,
            s.out_ms = $out_ms,
            s.duration_ms = $duration_ms,
            s.type = $type,
            s.category = $category,
            s.action = $action,
            s.text = $text,
            s.description = $description,
            s.faiss_id = $faiss_id,
            s.confidence = $confidence,
            s.updated_at = datetime()
        ON CREATE SET s.created_at = datetime()

        WITH s
        MATCH (v:Video {workflow_id: $workflow_id})
        MERGE (v)-[r:HAS_SEGMENT]->(s)
        SET r.position = $position

        RETURN s.segment_id AS segment_id
        """

        try:
            with self._driver.session() as session:
                result = session.run(query, {
                    "segment_id": segment_data.get("segment_id"),
                    "workflow_id": segment_data.get("workflow_id"),
                    "in_ms": segment_data.get("in_ms", 0),
                    "out_ms": segment_data.get("out_ms", 0),
                    "duration_ms": segment_data.get("duration_ms", 0),
                    "type": segment_data.get("type", "A-Roll"),
                    "category": segment_data.get("category", ""),
                    "action": segment_data.get("action", "keep"),
                    "text": segment_data.get("text", "")[:5000],  # Limit text length
                    "description": segment_data.get("description", ""),
                    "faiss_id": segment_data.get("faiss_id"),
                    "confidence": segment_data.get("confidence", 1.0),
                    "position": segment_data.get("position", 0)
                })
                record = result.single()
                return record["segment_id"] if record else None
        except Exception as e:
            logger.error(f"Error creating segment node: {e}")
            return None

    def create_similarity_edge(
        self,
        segment_id_1: str,
        segment_id_2: str,
        similarity: float,
        similarity_type: str = "visual"
    ) -> bool:
        """
        Create a SIMILAR_TO relationship between two segments.

        Args:
            segment_id_1: First segment ID
            segment_id_2: Second segment ID
            similarity: Similarity score (0.0-1.0)
            similarity_type: Type of similarity (visual, semantic, both)

        Returns:
            True if successful
        """
        if not self.is_available:
            return False

        query = """
        MATCH (s1:Segment {segment_id: $segment_id_1})
        MATCH (s2:Segment {segment_id: $segment_id_2})
        MERGE (s1)-[r:SIMILAR_TO]->(s2)
        SET r.similarity = $similarity,
            r.similarity_type = $similarity_type,
            r.detected_at = datetime()
        RETURN r
        """

        try:
            with self._driver.session() as session:
                result = session.run(query, {
                    "segment_id_1": segment_id_1,
                    "segment_id_2": segment_id_2,
                    "similarity": similarity,
                    "similarity_type": similarity_type
                })
                return result.single() is not None
        except Exception as e:
            logger.error(f"Error creating similarity edge: {e}")
            return False

    # =========================================================================
    # ENTITY OPERATIONS
    # =========================================================================

    def create_entity_node(self, entity_data: Dict[str, Any]) -> Optional[str]:
        """
        Create or update an Entity node.

        Args:
            entity_data: Dict with keys:
                - name (required)
                - type (PERSON, LOCATION, ORGANIZATION, PRODUCT, CONCEPT)
                - normalized_name

        Returns:
            entity_id if successful
        """
        if not self.is_available:
            return None

        # Normalize name for matching
        name = entity_data.get("name", "")
        normalized = entity_data.get("normalized_name", name.lower().replace(" ", "_"))
        entity_id = f"entity_{normalized}"

        query = """
        MERGE (e:Entity {normalized_name: $normalized_name})
        ON CREATE SET
            e.entity_id = $entity_id,
            e.name = $name,
            e.type = $type,
            e.mention_count = 1,
            e.first_mentioned_at = datetime()
        ON MATCH SET
            e.mention_count = e.mention_count + 1
        RETURN e.entity_id AS entity_id
        """

        try:
            with self._driver.session() as session:
                result = session.run(query, {
                    "entity_id": entity_id,
                    "name": name,
                    "normalized_name": normalized,
                    "type": entity_data.get("type", "CONCEPT")
                })
                record = result.single()
                return record["entity_id"] if record else None
        except Exception as e:
            logger.error(f"Error creating entity node: {e}")
            return None

    def create_mentions_edge(
        self,
        segment_id: str,
        entity_name: str,
        context: str = ""
    ) -> bool:
        """
        Create a MENTIONS relationship between Segment and Entity.

        Args:
            segment_id: Segment ID
            entity_name: Entity name (will be normalized)
            context: Surrounding text context

        Returns:
            True if successful
        """
        if not self.is_available:
            return False

        normalized = entity_name.lower().replace(" ", "_")

        query = """
        MATCH (s:Segment {segment_id: $segment_id})
        MATCH (e:Entity {normalized_name: $normalized_name})
        MERGE (s)-[r:MENTIONS]->(e)
        SET r.context = $context,
            r.mentioned_at = datetime()
        RETURN r
        """

        try:
            with self._driver.session() as session:
                result = session.run(query, {
                    "segment_id": segment_id,
                    "normalized_name": normalized,
                    "context": context[:500]  # Limit context length
                })
                return result.single() is not None
        except Exception as e:
            logger.error(f"Error creating mentions edge: {e}")
            return False

    # =========================================================================
    # TOPIC OPERATIONS
    # =========================================================================

    def create_topic_node(self, topic_data: Dict[str, Any]) -> Optional[str]:
        """
        Create or update a Topic node.

        Args:
            topic_data: Dict with keys:
                - name (required)
                - category (technical, narrative, educational)

        Returns:
            topic_id if successful
        """
        if not self.is_available:
            return None

        name = topic_data.get("name", "")
        normalized = name.lower().replace(" ", "_")
        topic_id = f"topic_{normalized}"

        query = """
        MERGE (t:Topic {normalized_name: $normalized_name})
        ON CREATE SET
            t.topic_id = $topic_id,
            t.name = $name,
            t.category = $category,
            t.frequency = 1
        ON MATCH SET
            t.frequency = t.frequency + 1
        RETURN t.topic_id AS topic_id
        """

        try:
            with self._driver.session() as session:
                result = session.run(query, {
                    "topic_id": topic_id,
                    "name": name,
                    "normalized_name": normalized,
                    "category": topic_data.get("category", "")
                })
                record = result.single()
                return record["topic_id"] if record else None
        except Exception as e:
            logger.error(f"Error creating topic node: {e}")
            return None

    def create_covers_edge(
        self,
        workflow_id: str,
        topic_name: str,
        depth: str = "moderate"
    ) -> bool:
        """
        Create a COVERS relationship between Video and Topic.

        Args:
            workflow_id: Video workflow ID
            topic_name: Topic name (will be normalized)
            depth: How deeply topic is covered (shallow, moderate, deep)

        Returns:
            True if successful
        """
        if not self.is_available:
            return False

        normalized = topic_name.lower().replace(" ", "_")

        query = """
        MATCH (v:Video {workflow_id: $workflow_id})
        MATCH (t:Topic {normalized_name: $normalized_name})
        MERGE (v)-[r:COVERS]->(t)
        SET r.depth = $depth,
            r.covered_at = datetime()
        RETURN r
        """

        try:
            with self._driver.session() as session:
                result = session.run(query, {
                    "workflow_id": workflow_id,
                    "normalized_name": normalized,
                    "depth": depth
                })
                return result.single() is not None
        except Exception as e:
            logger.error(f"Error creating covers edge: {e}")
            return False

    # =========================================================================
    # QUERY OPERATIONS
    # =========================================================================

    def get_project_graph(self, project_id: str) -> Dict[str, Any]:
        """
        Get the full knowledge graph for a project.

        Returns:
            Dict with nodes and edges for visualization
        """
        if not self.is_available:
            return {"nodes": [], "edges": [], "error": "Neo4j not available"}

        query = """
        MATCH (p:Project {project_id: $project_id})-[:CONTAINS]->(v:Video)
        OPTIONAL MATCH (v)-[:HAS_SEGMENT]->(s:Segment)
        OPTIONAL MATCH (s)-[:MENTIONS]->(e:Entity)
        OPTIONAL MATCH (v)-[:COVERS]->(t:Topic)
        OPTIONAL MATCH (s1:Segment)-[sim:SIMILAR_TO]->(s2:Segment)
        WHERE s1.workflow_id IN [v.workflow_id] OR s2.workflow_id IN [v.workflow_id]

        RETURN p, collect(DISTINCT v) AS videos,
               collect(DISTINCT s) AS segments,
               collect(DISTINCT e) AS entities,
               collect(DISTINCT t) AS topics,
               collect(DISTINCT {from: s1.segment_id, to: s2.segment_id, similarity: sim.similarity}) AS similarities
        """

        try:
            with self._driver.session() as session:
                result = session.run(query, {"project_id": project_id})
                record = result.single()

                if not record:
                    return {"nodes": [], "edges": []}

                nodes = []
                edges = []

                # Add project node
                project = dict(record["p"])
                nodes.append({
                    "id": f"project_{project_id}",
                    "type": "project",
                    "label": project.get("name", project_id),
                    "properties": project
                })

                # Add video nodes
                for v in record["videos"]:
                    video = dict(v)
                    vid = video.get("workflow_id")
                    nodes.append({
                        "id": f"video_{vid}",
                        "type": "video",
                        "label": vid[:8],
                        "properties": video
                    })
                    edges.append({
                        "source": f"project_{project_id}",
                        "target": f"video_{vid}",
                        "type": "CONTAINS"
                    })

                # Add entity nodes
                for e in record["entities"]:
                    if e:
                        entity = dict(e)
                        eid = entity.get("entity_id")
                        nodes.append({
                            "id": eid,
                            "type": "entity",
                            "label": entity.get("name", ""),
                            "properties": entity
                        })

                # Add topic nodes
                for t in record["topics"]:
                    if t:
                        topic = dict(t)
                        tid = topic.get("topic_id")
                        nodes.append({
                            "id": tid,
                            "type": "topic",
                            "label": topic.get("name", ""),
                            "properties": topic
                        })

                # Add similarity edges
                for sim in record["similarities"]:
                    if sim.get("from") and sim.get("to"):
                        edges.append({
                            "source": f"segment_{sim['from']}",
                            "target": f"segment_{sim['to']}",
                            "type": "SIMILAR_TO",
                            "properties": {"similarity": sim.get("similarity", 0)}
                        })

                return {"nodes": nodes, "edges": edges}

        except Exception as e:
            logger.error(f"Error getting project graph: {e}")
            return {"nodes": [], "edges": [], "error": str(e)}

    def find_similar_segments(
        self,
        segment_id: str,
        threshold: float = 0.85
    ) -> List[Dict[str, Any]]:
        """
        Find segments similar to the given segment.

        Args:
            segment_id: Source segment ID
            threshold: Minimum similarity threshold

        Returns:
            List of similar segments with similarity scores
        """
        if not self.is_available:
            return []

        query = """
        MATCH (s1:Segment {segment_id: $segment_id})-[r:SIMILAR_TO]-(s2:Segment)
        WHERE r.similarity >= $threshold
        RETURN s2, r.similarity AS similarity
        ORDER BY similarity DESC
        """

        try:
            with self._driver.session() as session:
                result = session.run(query, {
                    "segment_id": segment_id,
                    "threshold": threshold
                })
                return [
                    {**dict(record["s2"]), "similarity": record["similarity"]}
                    for record in result
                ]
        except Exception as e:
            logger.error(f"Error finding similar segments: {e}")
            return []

    def get_entity_timeline(
        self,
        entity_name: str,
        project_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get all mentions of an entity across videos in a project.

        Returns:
            List of mentions ordered by video sequence and segment position
        """
        if not self.is_available:
            return []

        normalized = entity_name.lower().replace(" ", "_")

        query = """
        MATCH (p:Project {project_id: $project_id})-[:CONTAINS]->(v:Video)
        MATCH (v)-[:HAS_SEGMENT]->(s:Segment)-[m:MENTIONS]->(e:Entity {normalized_name: $normalized_name})
        RETURN v.workflow_id AS video_id,
               v.sequence_index AS sequence,
               s.segment_id AS segment_id,
               s.in_ms AS in_ms,
               s.out_ms AS out_ms,
               s.text AS text,
               m.context AS context
        ORDER BY v.sequence_index, s.in_ms
        """

        try:
            with self._driver.session() as session:
                result = session.run(query, {
                    "project_id": project_id,
                    "normalized_name": normalized
                })
                return [dict(record) for record in result]
        except Exception as e:
            logger.error(f"Error getting entity timeline: {e}")
            return []

    def calculate_redundancy_clusters(
        self,
        project_id: str,
        threshold: float = 0.85
    ) -> List[List[str]]:
        """
        Find clusters of redundant segments using graph algorithms.

        Returns:
            List of clusters, each cluster is a list of segment IDs
        """
        if not self.is_available:
            return []

        query = """
        MATCH (p:Project {project_id: $project_id})-[:CONTAINS]->(v:Video)-[:HAS_SEGMENT]->(s:Segment)
        WITH collect(s) AS segments

        MATCH (s1:Segment)-[r:SIMILAR_TO]->(s2:Segment)
        WHERE s1 IN segments AND s2 IN segments AND r.similarity >= $threshold

        WITH s1, s2, r.similarity AS similarity
        RETURN s1.segment_id AS seg1, s2.segment_id AS seg2, similarity
        ORDER BY similarity DESC
        """

        try:
            with self._driver.session() as session:
                result = session.run(query, {
                    "project_id": project_id,
                    "threshold": threshold
                })

                # Build clusters using union-find
                parent = {}

                def find(x):
                    if x not in parent:
                        parent[x] = x
                    if parent[x] != x:
                        parent[x] = find(parent[x])
                    return parent[x]

                def union(x, y):
                    px, py = find(x), find(y)
                    if px != py:
                        parent[px] = py

                for record in result:
                    union(record["seg1"], record["seg2"])

                # Group by cluster
                clusters = {}
                for seg_id in parent:
                    root = find(seg_id)
                    if root not in clusters:
                        clusters[root] = []
                    clusters[root].append(seg_id)

                return [segs for segs in clusters.values() if len(segs) > 1]

        except Exception as e:
            logger.error(f"Error calculating redundancy clusters: {e}")
            return []

    # =========================================================================
    # INDEX MANAGEMENT
    # =========================================================================

    def create_indexes(self) -> bool:
        """
        Create necessary indexes for performance.
        Should be called once during setup.

        Returns:
            True if successful
        """
        if not self.is_available:
            return False

        indexes = [
            "CREATE INDEX IF NOT EXISTS FOR (p:Project) ON (p.project_id)",
            "CREATE INDEX IF NOT EXISTS FOR (v:Video) ON (v.workflow_id)",
            "CREATE INDEX IF NOT EXISTS FOR (v:Video) ON (v.project_id)",
            "CREATE INDEX IF NOT EXISTS FOR (s:Segment) ON (s.segment_id)",
            "CREATE INDEX IF NOT EXISTS FOR (s:Segment) ON (s.workflow_id)",
            "CREATE INDEX IF NOT EXISTS FOR (s:Segment) ON (s.faiss_id)",
            "CREATE INDEX IF NOT EXISTS FOR (e:Entity) ON (e.normalized_name)",
            "CREATE INDEX IF NOT EXISTS FOR (t:Topic) ON (t.normalized_name)"
        ]

        try:
            with self._driver.session() as session:
                for index_query in indexes:
                    session.run(index_query)
            logger.info("Neo4j indexes created successfully")
            return True
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")
            return False

    def delete_project_graph(self, project_id: str) -> bool:
        """
        Delete all nodes and relationships for a project.

        Args:
            project_id: Project ID to delete

        Returns:
            True if successful
        """
        if not self.is_available:
            return False

        query = """
        MATCH (p:Project {project_id: $project_id})
        OPTIONAL MATCH (p)-[:CONTAINS]->(v:Video)
        OPTIONAL MATCH (v)-[:HAS_SEGMENT]->(s:Segment)
        DETACH DELETE p, v, s
        """

        try:
            with self._driver.session() as session:
                session.run(query, {"project_id": project_id})
            logger.info(f"Deleted graph for project {project_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting project graph: {e}")
            return False


# Convenience function for getting the singleton instance
def get_neo4j_manager() -> Neo4jManager:
    """Get the Neo4j manager singleton instance."""
    return Neo4jManager()
