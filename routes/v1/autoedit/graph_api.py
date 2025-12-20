# Copyright (c) 2025 Stephen G. Pope
# Licensed under GPL-2.0

"""
Graph API for AutoEdit Phase 5

Endpoints for querying the Neo4j knowledge graph.
Provides access to project structure, concept relationships,
and semantic queries across video content.

Endpoints:
- GET  /v1/autoedit/project/{id}/graph/knowledge-graph
- GET  /v1/autoedit/project/{id}/graph/concept-relationships
- POST /v1/autoedit/project/{id}/graph/query
"""

import logging
from flask import Blueprint, request, jsonify

from services.authentication import authenticate

logger = logging.getLogger(__name__)

v1_autoedit_graph_bp = Blueprint(
    'v1_autoedit_graph',
    __name__
)


# =============================================================================
# GET KNOWLEDGE GRAPH
# =============================================================================

@v1_autoedit_graph_bp.route(
    '/v1/autoedit/project/<project_id>/graph/knowledge-graph',
    methods=['GET']
)
@authenticate
def get_knowledge_graph(project_id: str):
    """
    Get the complete knowledge graph for a project.

    Returns nodes and relationships in a format suitable for
    graph visualization (D3.js, Cytoscape.js, etc.)

    Query Parameters:
        include_segments: Include segment nodes (default: false, can be large)
        include_embeddings: Include FAISS IDs for vector lookups (default: false)
        max_depth: Max relationship depth from project (default: 2)

    Returns:
    {
        "project_id": "...",
        "nodes": [
            {"id": "proj_123", "type": "Project", "label": "My Project", ...},
            {"id": "wf_001", "type": "Video", "label": "Video 1", ...}
        ],
        "edges": [
            {"source": "proj_123", "target": "wf_001", "type": "CONTAINS"},
            {"source": "wf_001", "target": "wf_002", "type": "FOLLOWED_BY"}
        ],
        "statistics": {
            "node_count": 25,
            "edge_count": 40,
            "video_count": 3
        }
    }
    """
    try:
        from services.v1.autoedit.graph_manager import get_graph_manager
        from services.v1.autoedit.project import get_project
        from config import USE_KNOWLEDGE_GRAPH

        # Check feature flag
        if not USE_KNOWLEDGE_GRAPH:
            return jsonify({
                "error": "Knowledge graph not enabled",
                "hint": "Set USE_KNOWLEDGE_GRAPH=true"
            }), 400

        # Check project exists
        project = get_project(project_id)
        if not project:
            return jsonify({"error": "Project not found"}), 404

        # Get graph manager
        graph = get_graph_manager()
        if not graph.is_available():
            return jsonify({
                "error": "Neo4j not available",
                "hint": "Check NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD"
            }), 503

        # Parse options
        include_segments = request.args.get("include_segments", "false").lower() == "true"
        include_embeddings = request.args.get("include_embeddings", "false").lower() == "true"
        max_depth = int(request.args.get("max_depth", 2))

        # Get graph data
        result = graph.get_project_graph(project_id)

        if not result:
            # Graph not populated yet - return structure from GCS
            return _build_graph_from_project(project, include_segments)

        # Process nodes
        nodes = []
        edges = []

        for record in result:
            node = record.get("n")
            if node:
                node_data = {
                    "id": node.get("id") or node.get("project_id") or node.get("workflow_id"),
                    "type": list(node.labels)[0] if hasattr(node, 'labels') else "Unknown",
                    "label": node.get("name", node.get("id", "Unknown")),
                    **{k: v for k, v in node.items() if k not in ["id", "name"]}
                }

                # Optionally include FAISS ID
                if include_embeddings and "faiss_id" in node:
                    node_data["faiss_id"] = node["faiss_id"]

                # Filter segments if not requested
                if node_data["type"] == "Segment" and not include_segments:
                    continue

                nodes.append(node_data)

            rel = record.get("r")
            if rel:
                edges.append({
                    "source": rel.start_node.get("id", str(rel.start_node.id)),
                    "target": rel.end_node.get("id", str(rel.end_node.id)),
                    "type": type(rel).__name__,
                    "properties": dict(rel)
                })

        # Remove duplicates
        seen_nodes = set()
        unique_nodes = []
        for node in nodes:
            if node["id"] not in seen_nodes:
                seen_nodes.add(node["id"])
                unique_nodes.append(node)

        seen_edges = set()
        unique_edges = []
        for edge in edges:
            key = (edge["source"], edge["target"], edge["type"])
            if key not in seen_edges:
                seen_edges.add(key)
                unique_edges.append(edge)

        # Statistics
        type_counts = {}
        for node in unique_nodes:
            t = node["type"]
            type_counts[t] = type_counts.get(t, 0) + 1

        return jsonify({
            "project_id": project_id,
            "nodes": unique_nodes,
            "edges": unique_edges,
            "statistics": {
                "node_count": len(unique_nodes),
                "edge_count": len(unique_edges),
                "by_type": type_counts
            }
        })

    except Exception as e:
        logger.error(f"Get knowledge graph failed for {project_id}: {e}")
        return jsonify({"error": str(e)}), 500


def _build_graph_from_project(project: dict, include_segments: bool) -> dict:
    """Build graph structure from GCS project data when Neo4j not populated."""
    from services.v1.autoedit.workflow import get_workflow

    project_id = project.get("id")
    workflow_ids = project.get("workflow_ids", [])

    nodes = [{
        "id": project_id,
        "type": "Project",
        "label": project.get("name", project_id),
        "state": project.get("state"),
        "video_count": len(workflow_ids)
    }]

    edges = []

    prev_wf_id = None
    for wf_id in workflow_ids:
        wf = get_workflow(wf_id)
        if wf:
            nodes.append({
                "id": wf_id,
                "type": "Video",
                "label": wf.get("title", wf_id),
                "sequence_index": wf.get("sequence_index", 0),
                "status": wf.get("status")
            })

            edges.append({
                "source": project_id,
                "target": wf_id,
                "type": "CONTAINS"
            })

            if prev_wf_id:
                edges.append({
                    "source": prev_wf_id,
                    "target": wf_id,
                    "type": "FOLLOWED_BY"
                })
            prev_wf_id = wf_id

            # Add segments if requested
            if include_segments:
                for block in wf.get("blocks", []):
                    if block.get("action") == "keep":
                        seg_id = block.get("id", f"{wf_id}_{block.get('in')}")
                        nodes.append({
                            "id": seg_id,
                            "type": "Segment",
                            "label": block.get("text", "")[:50],
                            "in_ms": block.get("in"),
                            "out_ms": block.get("out")
                        })
                        edges.append({
                            "source": wf_id,
                            "target": seg_id,
                            "type": "HAS_SEGMENT"
                        })

    return jsonify({
        "project_id": project_id,
        "nodes": nodes,
        "edges": edges,
        "source": "gcs",
        "note": "Graph built from GCS data. Run sync to populate Neo4j.",
        "statistics": {
            "node_count": len(nodes),
            "edge_count": len(edges)
        }
    })


# =============================================================================
# GET CONCEPT RELATIONSHIPS
# =============================================================================

@v1_autoedit_graph_bp.route(
    '/v1/autoedit/project/<project_id>/graph/concept-relationships',
    methods=['GET']
)
@authenticate
def get_concept_relationships(project_id: str):
    """
    Get entity and topic relationships within a project.

    Shows how concepts mentioned across videos are related.

    Query Parameters:
        entity_type: Filter by entity type (person, place, product, etc.)
        min_mentions: Minimum mention count (default: 2)
        include_topics: Include topic nodes (default: true)

    Returns:
    {
        "project_id": "...",
        "entities": [
            {
                "id": "ent_gps",
                "name": "GPS",
                "type": "technology",
                "mention_count": 5,
                "appears_in": ["wf_001", "wf_003"]
            }
        ],
        "topics": [...],
        "relationships": [
            {"source": "wf_001", "entity": "ent_gps", "type": "MENTIONS", "count": 3}
        ]
    }
    """
    try:
        from services.v1.autoedit.graph_manager import get_graph_manager
        from services.v1.autoedit.project import get_project
        from services.v1.autoedit.workflow import get_workflow
        from config import USE_KNOWLEDGE_GRAPH

        project = get_project(project_id)
        if not project:
            return jsonify({"error": "Project not found"}), 404

        # Parse options
        entity_type = request.args.get("entity_type")
        min_mentions = int(request.args.get("min_mentions", 2))
        include_topics = request.args.get("include_topics", "true").lower() == "true"

        # Try Neo4j first
        if USE_KNOWLEDGE_GRAPH:
            graph = get_graph_manager()
            if graph.is_available():
                # Query for entities and topics
                entities = graph.get_project_entities(project_id, entity_type, min_mentions)
                topics = graph.get_project_topics(project_id) if include_topics else []

                if entities or topics:
                    return jsonify({
                        "project_id": project_id,
                        "entities": entities,
                        "topics": topics if include_topics else None,
                        "source": "neo4j"
                    })

        # Fallback: extract from workflow analysis
        entities = {}
        topics = set()
        workflow_ids = project.get("workflow_ids", [])

        for wf_id in workflow_ids:
            wf = get_workflow(wf_id)
            if not wf:
                continue

            analysis = wf.get("analysis", {})

            # Extract entities from analysis
            for entity in analysis.get("entities", []):
                name = entity.get("name", "").lower()
                if name:
                    if name not in entities:
                        entities[name] = {
                            "id": f"ent_{name.replace(' ', '_')}",
                            "name": entity.get("name"),
                            "type": entity.get("type", "unknown"),
                            "mention_count": 0,
                            "appears_in": []
                        }
                    entities[name]["mention_count"] += entity.get("count", 1)
                    if wf_id not in entities[name]["appears_in"]:
                        entities[name]["appears_in"].append(wf_id)

            # Extract topics
            for topic in analysis.get("main_topics", []):
                topics.add(topic)

        # Filter by min_mentions
        filtered_entities = [
            e for e in entities.values()
            if e["mention_count"] >= min_mentions
        ]

        # Filter by entity_type if specified
        if entity_type:
            filtered_entities = [
                e for e in filtered_entities
                if e["type"] == entity_type
            ]

        return jsonify({
            "project_id": project_id,
            "entities": sorted(filtered_entities, key=lambda x: x["mention_count"], reverse=True),
            "topics": list(topics) if include_topics else None,
            "source": "gcs_analysis"
        })

    except Exception as e:
        logger.error(f"Get concept relationships failed for {project_id}: {e}")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# QUERY GRAPH
# =============================================================================

@v1_autoedit_graph_bp.route(
    '/v1/autoedit/project/<project_id>/graph/query',
    methods=['POST']
)
@authenticate
def query_graph(project_id: str):
    """
    Execute a simplified graph query.

    Supports common query patterns without exposing raw Cypher.

    Request Body:
    {
        "query_type": "similar_segments" | "segment_path" | "topic_videos" | "redundancy_clusters",
        "parameters": {
            // Depends on query_type
        }
    }

    Query Types:
    - similar_segments: Find segments similar to a given segment
        parameters: {segment_id, threshold, limit}
    - segment_path: Find path between two segments
        parameters: {from_segment, to_segment}
    - topic_videos: Find videos covering a topic
        parameters: {topic}
    - redundancy_clusters: Get redundancy clusters
        parameters: {min_similarity}

    Returns query-specific results.
    """
    try:
        from services.v1.autoedit.graph_manager import get_graph_manager
        from services.v1.autoedit.faiss_manager import get_faiss_manager
        from services.v1.autoedit.project import get_project
        from config import USE_KNOWLEDGE_GRAPH, USE_FAISS_SEARCH

        project = get_project(project_id)
        if not project:
            return jsonify({"error": "Project not found"}), 404

        data = request.get_json()
        if not data or "query_type" not in data:
            return jsonify({"error": "query_type is required"}), 400

        query_type = data["query_type"]
        params = data.get("parameters", {})

        # Handle different query types
        if query_type == "similar_segments":
            # Use FAISS for similarity search
            if not USE_FAISS_SEARCH:
                return jsonify({"error": "FAISS search not enabled"}), 400

            faiss = get_faiss_manager()
            if not faiss.is_available():
                return jsonify({"error": "FAISS not available"}), 503

            segment_id = params.get("segment_id")
            if not segment_id:
                return jsonify({"error": "segment_id required"}), 400

            threshold = params.get("threshold", 0.8)
            limit = params.get("limit", 10)

            results = faiss.search_by_segment(
                project_id,
                segment_id,
                k=limit,
                threshold=2 * (1 - threshold)  # Convert similarity to distance
            )

            return jsonify({
                "project_id": project_id,
                "query_type": query_type,
                "segment_id": segment_id,
                "results": [
                    {"segment_id": seg_id, "similarity": 1 - (dist / 2)}
                    for seg_id, dist in results
                ]
            })

        elif query_type == "redundancy_clusters":
            # Get redundancy clusters from FAISS
            if not USE_FAISS_SEARCH:
                return jsonify({"error": "FAISS search not enabled"}), 400

            faiss = get_faiss_manager()
            if not faiss.is_available():
                return jsonify({"error": "FAISS not available"}), 503

            min_similarity = params.get("min_similarity", 0.85)
            pairs = faiss.find_redundant_pairs(project_id, min_similarity)

            return jsonify({
                "project_id": project_id,
                "query_type": query_type,
                "min_similarity": min_similarity,
                "pairs": pairs,
                "total_pairs": len(pairs)
            })

        elif query_type == "topic_videos":
            # Find videos by topic
            topic = params.get("topic")
            if not topic:
                return jsonify({"error": "topic required"}), 400

            from services.v1.autoedit.workflow import get_workflow
            workflow_ids = project.get("workflow_ids", [])
            matching = []

            for wf_id in workflow_ids:
                wf = get_workflow(wf_id)
                if wf:
                    topics = wf.get("analysis", {}).get("main_topics", [])
                    if any(topic.lower() in t.lower() for t in topics):
                        matching.append({
                            "workflow_id": wf_id,
                            "title": wf.get("title", wf_id),
                            "topics": topics
                        })

            return jsonify({
                "project_id": project_id,
                "query_type": query_type,
                "topic": topic,
                "matching_videos": matching,
                "count": len(matching)
            })

        elif query_type == "segment_path":
            # Find relationship path between segments
            if not USE_KNOWLEDGE_GRAPH:
                return jsonify({"error": "Knowledge graph not enabled"}), 400

            graph = get_graph_manager()
            if not graph.is_available():
                return jsonify({"error": "Neo4j not available"}), 503

            from_seg = params.get("from_segment")
            to_seg = params.get("to_segment")
            if not from_seg or not to_seg:
                return jsonify({"error": "from_segment and to_segment required"}), 400

            path = graph.find_segment_path(project_id, from_seg, to_seg)

            return jsonify({
                "project_id": project_id,
                "query_type": query_type,
                "from_segment": from_seg,
                "to_segment": to_seg,
                "path": path
            })

        else:
            return jsonify({
                "error": f"Unknown query_type: {query_type}",
                "valid_types": ["similar_segments", "segment_path", "topic_videos", "redundancy_clusters"]
            }), 400

    except Exception as e:
        logger.error(f"Graph query failed for {project_id}: {e}")
        return jsonify({"error": str(e)}), 500
