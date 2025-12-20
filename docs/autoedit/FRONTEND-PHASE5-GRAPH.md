# Phase 5: Graph API - Frontend Integration Guide

## Overview

The Graph API provides access to the Neo4j knowledge graph for querying project structure, concept relationships, and semantic connections across video content. It enables powerful visualizations and intelligent queries.

**Feature Flag Required**: `USE_KNOWLEDGE_GRAPH=true`

## Endpoints Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/autoedit/project/{id}/graph/knowledge-graph` | GET | Get complete graph structure |
| `/v1/autoedit/project/{id}/graph/concept-relationships` | GET | Get entity/topic relationships |
| `/v1/autoedit/project/{id}/graph/query` | POST | Execute semantic queries |

---

## 1. Get Knowledge Graph

Retrieves the complete knowledge graph for visualization. Returns nodes and relationships in a format suitable for graph libraries (D3.js, Cytoscape.js, etc.).

### Request

```http
GET /v1/autoedit/project/{project_id}/graph/knowledge-graph?include_segments=false&include_embeddings=false&max_depth=2
X-API-Key: your_api_key
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `include_segments` | boolean | false | Include segment nodes (can be large) |
| `include_embeddings` | boolean | false | Include FAISS IDs for vector lookups |
| `max_depth` | number | 2 | Max relationship depth from project |

### Response

```json
{
  "project_id": "proj_abc123",
  "nodes": [
    {
      "id": "proj_abc123",
      "type": "Project",
      "label": "My Documentary Series",
      "state": "completed",
      "video_count": 5
    },
    {
      "id": "wf_001",
      "type": "Video",
      "label": "Episode 1: Introduction",
      "sequence_index": 0,
      "status": "ready"
    },
    {
      "id": "wf_002",
      "type": "Video",
      "label": "Episode 2: Deep Dive",
      "sequence_index": 1,
      "status": "ready"
    },
    {
      "id": "ent_gps",
      "type": "Entity",
      "label": "GPS Technology",
      "entity_type": "technology",
      "mention_count": 8
    },
    {
      "id": "topic_navigation",
      "type": "Topic",
      "label": "Navigation Systems",
      "relevance_score": 0.92
    }
  ],
  "edges": [
    {
      "source": "proj_abc123",
      "target": "wf_001",
      "type": "CONTAINS",
      "properties": {}
    },
    {
      "source": "wf_001",
      "target": "wf_002",
      "type": "FOLLOWED_BY",
      "properties": {}
    },
    {
      "source": "wf_001",
      "target": "ent_gps",
      "type": "MENTIONS",
      "properties": { "count": 5 }
    },
    {
      "source": "wf_002",
      "target": "ent_gps",
      "type": "MENTIONS",
      "properties": { "count": 3 }
    },
    {
      "source": "wf_001",
      "target": "topic_navigation",
      "type": "COVERS",
      "properties": {}
    }
  ],
  "statistics": {
    "node_count": 5,
    "edge_count": 5,
    "by_type": {
      "Project": 1,
      "Video": 2,
      "Entity": 1,
      "Topic": 1
    }
  }
}
```

### Response (GCS Fallback)

When Neo4j is not populated, returns basic structure from GCS:

```json
{
  "project_id": "proj_abc123",
  "nodes": [...],
  "edges": [...],
  "source": "gcs",
  "note": "Graph built from GCS data. Run sync to populate Neo4j.",
  "statistics": {
    "node_count": 3,
    "edge_count": 2
  }
}
```

### Node Types

| Type | Description | Key Properties |
|------|-------------|----------------|
| `Project` | Root project node | state, video_count |
| `Video` | Individual video/workflow | sequence_index, status, title |
| `Segment` | Content segment (if included) | in_ms, out_ms, text preview |
| `Entity` | Named entity (person, place, etc.) | entity_type, mention_count |
| `Topic` | Topic/theme | relevance_score |

### Edge Types

| Type | Description | Properties |
|------|-------------|------------|
| `CONTAINS` | Project → Video | - |
| `FOLLOWED_BY` | Video → Video (sequence) | - |
| `HAS_SEGMENT` | Video → Segment | - |
| `MENTIONS` | Video/Segment → Entity | count |
| `COVERS` | Video → Topic | - |
| `RELATED_TO` | Entity → Entity, Topic → Topic | similarity |

### Frontend Implementation

```typescript
interface GraphNode {
  id: string;
  type: 'Project' | 'Video' | 'Segment' | 'Entity' | 'Topic';
  label: string;
  [key: string]: any;
}

interface GraphEdge {
  source: string;
  target: string;
  type: string;
  properties: Record<string, any>;
}

interface KnowledgeGraphResponse {
  project_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  statistics: {
    node_count: number;
    edge_count: number;
    by_type: Record<string, number>;
  };
  source?: 'neo4j' | 'gcs';
  note?: string;
}

interface GetGraphOptions {
  includeSegments?: boolean;
  includeEmbeddings?: boolean;
  maxDepth?: number;
}

async function getKnowledgeGraph(
  projectId: string,
  options: GetGraphOptions = {}
): Promise<KnowledgeGraphResponse> {
  const params = new URLSearchParams();
  if (options.includeSegments) params.set('include_segments', 'true');
  if (options.includeEmbeddings) params.set('include_embeddings', 'true');
  if (options.maxDepth) params.set('max_depth', options.maxDepth.toString());

  const response = await fetch(
    `${API_BASE}/v1/autoedit/project/${projectId}/graph/knowledge-graph?${params}`,
    {
      headers: { 'X-API-Key': API_KEY }
    }
  );

  return response.json();
}
```

---

## 2. Get Concept Relationships

Retrieves entity and topic relationships showing how concepts are connected across videos.

### Request

```http
GET /v1/autoedit/project/{project_id}/graph/concept-relationships?entity_type=technology&min_mentions=2&include_topics=true
X-API-Key: your_api_key
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `entity_type` | string | null | Filter: "person", "place", "technology", etc. |
| `min_mentions` | number | 2 | Minimum mention count |
| `include_topics` | boolean | true | Include topic nodes |

### Response

```json
{
  "project_id": "proj_abc123",
  "entities": [
    {
      "id": "ent_gps",
      "name": "GPS",
      "type": "technology",
      "mention_count": 8,
      "appears_in": ["wf_001", "wf_002", "wf_004"]
    },
    {
      "id": "ent_galileo",
      "name": "Galileo System",
      "type": "technology",
      "mention_count": 5,
      "appears_in": ["wf_002", "wf_003"]
    },
    {
      "id": "ent_elon_musk",
      "name": "Elon Musk",
      "type": "person",
      "mention_count": 3,
      "appears_in": ["wf_005"]
    }
  ],
  "topics": [
    "satellite navigation",
    "geolocation",
    "space technology",
    "mobile positioning"
  ],
  "source": "neo4j"
}
```

### Entity Types

| Type | Examples |
|------|----------|
| `person` | Names of individuals |
| `place` | Locations, cities, countries |
| `organization` | Companies, institutions |
| `technology` | Tools, systems, protocols |
| `product` | Products, services |
| `concept` | Abstract ideas, theories |
| `event` | Historical events, conferences |

### Frontend Implementation

```typescript
interface Entity {
  id: string;
  name: string;
  type: string;
  mention_count: number;
  appears_in: string[];
}

interface ConceptRelationshipsResponse {
  project_id: string;
  entities: Entity[];
  topics: string[] | null;
  source: 'neo4j' | 'gcs_analysis';
}

interface GetConceptsOptions {
  entityType?: string;
  minMentions?: number;
  includeTopics?: boolean;
}

async function getConceptRelationships(
  projectId: string,
  options: GetConceptsOptions = {}
): Promise<ConceptRelationshipsResponse> {
  const params = new URLSearchParams();
  if (options.entityType) params.set('entity_type', options.entityType);
  if (options.minMentions) params.set('min_mentions', options.minMentions.toString());
  if (options.includeTopics !== undefined) {
    params.set('include_topics', options.includeTopics.toString());
  }

  const response = await fetch(
    `${API_BASE}/v1/autoedit/project/${projectId}/graph/concept-relationships?${params}`,
    {
      headers: { 'X-API-Key': API_KEY }
    }
  );

  return response.json();
}
```

---

## 3. Query Graph

Execute semantic queries against the knowledge graph without exposing raw Cypher.

### Request

```http
POST /v1/autoedit/project/{project_id}/graph/query
Content-Type: application/json
X-API-Key: your_api_key
```

### Query Type: `similar_segments`

Find segments similar to a given segment using FAISS vector search.

```json
{
  "query_type": "similar_segments",
  "parameters": {
    "segment_id": "wf_001_45000",
    "threshold": 0.8,
    "limit": 10
  }
}
```

**Response:**

```json
{
  "project_id": "proj_abc123",
  "query_type": "similar_segments",
  "segment_id": "wf_001_45000",
  "results": [
    { "segment_id": "wf_003_120000", "similarity": 0.92 },
    { "segment_id": "wf_002_60000", "similarity": 0.87 },
    { "segment_id": "wf_004_30000", "similarity": 0.81 }
  ]
}
```

### Query Type: `redundancy_clusters`

Get clusters of semantically redundant segments.

```json
{
  "query_type": "redundancy_clusters",
  "parameters": {
    "min_similarity": 0.85
  }
}
```

**Response:**

```json
{
  "project_id": "proj_abc123",
  "query_type": "redundancy_clusters",
  "min_similarity": 0.85,
  "pairs": [
    {
      "segment_a": "wf_001_45000",
      "segment_b": "wf_003_120000",
      "similarity": 0.92
    },
    {
      "segment_a": "wf_002_60000",
      "segment_b": "wf_004_30000",
      "similarity": 0.88
    }
  ],
  "total_pairs": 2
}
```

### Query Type: `topic_videos`

Find videos that cover a specific topic.

```json
{
  "query_type": "topic_videos",
  "parameters": {
    "topic": "machine learning"
  }
}
```

**Response:**

```json
{
  "project_id": "proj_abc123",
  "query_type": "topic_videos",
  "topic": "machine learning",
  "matching_videos": [
    {
      "workflow_id": "wf_001",
      "title": "Introduction to ML",
      "topics": ["machine learning", "neural networks", "AI"]
    },
    {
      "workflow_id": "wf_003",
      "title": "ML in Practice",
      "topics": ["machine learning", "python", "tensorflow"]
    }
  ],
  "count": 2
}
```

### Query Type: `segment_path`

Find the relationship path between two segments.

```json
{
  "query_type": "segment_path",
  "parameters": {
    "from_segment": "wf_001_45000",
    "to_segment": "wf_003_120000"
  }
}
```

**Response:**

```json
{
  "project_id": "proj_abc123",
  "query_type": "segment_path",
  "from_segment": "wf_001_45000",
  "to_segment": "wf_003_120000",
  "path": [
    { "node": "wf_001_45000", "type": "Segment" },
    { "edge": "HAS_SEGMENT", "direction": "incoming" },
    { "node": "wf_001", "type": "Video" },
    { "edge": "FOLLOWED_BY", "direction": "outgoing" },
    { "node": "wf_002", "type": "Video" },
    { "edge": "FOLLOWED_BY", "direction": "outgoing" },
    { "node": "wf_003", "type": "Video" },
    { "edge": "HAS_SEGMENT", "direction": "outgoing" },
    { "node": "wf_003_120000", "type": "Segment" }
  ]
}
```

### Frontend Implementation

```typescript
type QueryType = 'similar_segments' | 'redundancy_clusters' | 'topic_videos' | 'segment_path';

interface SimilarSegmentsParams {
  segment_id: string;
  threshold?: number;
  limit?: number;
}

interface RedundancyClustersParams {
  min_similarity?: number;
}

interface TopicVideosParams {
  topic: string;
}

interface SegmentPathParams {
  from_segment: string;
  to_segment: string;
}

type QueryParams =
  | SimilarSegmentsParams
  | RedundancyClustersParams
  | TopicVideosParams
  | SegmentPathParams;

interface GraphQueryRequest {
  query_type: QueryType;
  parameters: QueryParams;
}

interface SimilarSegmentsResult {
  segment_id: string;
  similarity: number;
}

interface RedundancyPair {
  segment_a: string;
  segment_b: string;
  similarity: number;
}

interface MatchingVideo {
  workflow_id: string;
  title: string;
  topics: string[];
}

interface PathNode {
  node?: string;
  edge?: string;
  type?: string;
  direction?: 'incoming' | 'outgoing';
}

// Union type for all query responses
type GraphQueryResponse =
  | {
      project_id: string;
      query_type: 'similar_segments';
      segment_id: string;
      results: SimilarSegmentsResult[];
    }
  | {
      project_id: string;
      query_type: 'redundancy_clusters';
      min_similarity: number;
      pairs: RedundancyPair[];
      total_pairs: number;
    }
  | {
      project_id: string;
      query_type: 'topic_videos';
      topic: string;
      matching_videos: MatchingVideo[];
      count: number;
    }
  | {
      project_id: string;
      query_type: 'segment_path';
      from_segment: string;
      to_segment: string;
      path: PathNode[];
    };

async function queryGraph(
  projectId: string,
  request: GraphQueryRequest
): Promise<GraphQueryResponse> {
  const response = await fetch(
    `${API_BASE}/v1/autoedit/project/${projectId}/graph/query`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY
      },
      body: JSON.stringify(request)
    }
  );

  return response.json();
}

// Convenience functions
async function findSimilarSegments(
  projectId: string,
  segmentId: string,
  threshold: number = 0.8,
  limit: number = 10
) {
  return queryGraph(projectId, {
    query_type: 'similar_segments',
    parameters: { segment_id: segmentId, threshold, limit }
  });
}

async function findRedundancyClusters(
  projectId: string,
  minSimilarity: number = 0.85
) {
  return queryGraph(projectId, {
    query_type: 'redundancy_clusters',
    parameters: { min_similarity: minSimilarity }
  });
}

async function findVideosByTopic(projectId: string, topic: string) {
  return queryGraph(projectId, {
    query_type: 'topic_videos',
    parameters: { topic }
  });
}

async function findSegmentPath(
  projectId: string,
  fromSegment: string,
  toSegment: string
) {
  return queryGraph(projectId, {
    query_type: 'segment_path',
    parameters: { from_segment: fromSegment, to_segment: toSegment }
  });
}
```

---

## UI/UX Recommendations

### Knowledge Graph Visualization

Use D3.js, Cytoscape.js, or vis.js for interactive graph visualization.

```tsx
import React, { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';

function KnowledgeGraphViewer({ projectId }: { projectId: string }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [graphData, setGraphData] = useState<KnowledgeGraphResponse | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [includeSegments, setIncludeSegments] = useState(false);

  useEffect(() => {
    loadGraph();
  }, [projectId, includeSegments]);

  const loadGraph = async () => {
    const data = await getKnowledgeGraph(projectId, { includeSegments });
    setGraphData(data);
  };

  useEffect(() => {
    if (!graphData || !svgRef.current) return;
    renderGraph(graphData);
  }, [graphData]);

  const renderGraph = (data: KnowledgeGraphResponse) => {
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const width = 800;
    const height = 600;

    // Color scheme by node type
    const colorScale = d3.scaleOrdinal<string>()
      .domain(['Project', 'Video', 'Segment', 'Entity', 'Topic'])
      .range(['#e74c3c', '#3498db', '#9b59b6', '#2ecc71', '#f39c12']);

    // Size by node type
    const sizeScale = (type: string) => {
      switch (type) {
        case 'Project': return 30;
        case 'Video': return 20;
        case 'Entity': return 15;
        case 'Topic': return 15;
        case 'Segment': return 8;
        default: return 10;
      }
    };

    // Create force simulation
    const simulation = d3.forceSimulation(data.nodes as any)
      .force('link', d3.forceLink(data.edges as any)
        .id((d: any) => d.id)
        .distance(100)
      )
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius((d: any) => sizeScale(d.type) + 5));

    // Render edges
    const links = svg.append('g')
      .selectAll('line')
      .data(data.edges)
      .enter()
      .append('line')
      .attr('stroke', '#999')
      .attr('stroke-opacity', 0.6)
      .attr('stroke-width', 1);

    // Render edge labels
    const linkLabels = svg.append('g')
      .selectAll('text')
      .data(data.edges)
      .enter()
      .append('text')
      .attr('font-size', '8px')
      .attr('fill', '#666')
      .text((d: any) => d.type);

    // Render nodes
    const nodes = svg.append('g')
      .selectAll('circle')
      .data(data.nodes)
      .enter()
      .append('circle')
      .attr('r', (d: any) => sizeScale(d.type))
      .attr('fill', (d: any) => colorScale(d.type))
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)
      .style('cursor', 'pointer')
      .on('click', (event, d: any) => setSelectedNode(d))
      .call(d3.drag<any, any>()
        .on('start', dragstarted)
        .on('drag', dragged)
        .on('end', dragended)
      );

    // Render node labels
    const labels = svg.append('g')
      .selectAll('text')
      .data(data.nodes)
      .enter()
      .append('text')
      .attr('font-size', '10px')
      .attr('dx', (d: any) => sizeScale(d.type) + 5)
      .attr('dy', 4)
      .text((d: any) => d.label.substring(0, 20));

    // Update positions on tick
    simulation.on('tick', () => {
      links
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y);

      linkLabels
        .attr('x', (d: any) => (d.source.x + d.target.x) / 2)
        .attr('y', (d: any) => (d.source.y + d.target.y) / 2);

      nodes
        .attr('cx', (d: any) => d.x)
        .attr('cy', (d: any) => d.y);

      labels
        .attr('x', (d: any) => d.x)
        .attr('y', (d: any) => d.y);
    });

    function dragstarted(event: any) {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      event.subject.fx = event.subject.x;
      event.subject.fy = event.subject.y;
    }

    function dragged(event: any) {
      event.subject.fx = event.x;
      event.subject.fy = event.y;
    }

    function dragended(event: any) {
      if (!event.active) simulation.alphaTarget(0);
      event.subject.fx = null;
      event.subject.fy = null;
    }
  };

  return (
    <div className="knowledge-graph-viewer">
      <div className="controls">
        <label>
          <input
            type="checkbox"
            checked={includeSegments}
            onChange={(e) => setIncludeSegments(e.target.checked)}
          />
          Include Segments
        </label>

        {graphData && (
          <div className="stats">
            <span>{graphData.statistics.node_count} nodes</span>
            <span>{graphData.statistics.edge_count} edges</span>
          </div>
        )}
      </div>

      <svg ref={svgRef} width={800} height={600} />

      {/* Legend */}
      <div className="legend">
        <div className="legend-item">
          <span className="dot" style={{ backgroundColor: '#e74c3c' }} /> Project
        </div>
        <div className="legend-item">
          <span className="dot" style={{ backgroundColor: '#3498db' }} /> Video
        </div>
        <div className="legend-item">
          <span className="dot" style={{ backgroundColor: '#9b59b6' }} /> Segment
        </div>
        <div className="legend-item">
          <span className="dot" style={{ backgroundColor: '#2ecc71' }} /> Entity
        </div>
        <div className="legend-item">
          <span className="dot" style={{ backgroundColor: '#f39c12' }} /> Topic
        </div>
      </div>

      {/* Node Detail Panel */}
      {selectedNode && (
        <NodeDetailPanel
          node={selectedNode}
          onClose={() => setSelectedNode(null)}
          projectId={projectId}
        />
      )}
    </div>
  );
}
```

### Entity Browser Component

```tsx
function EntityBrowser({ projectId }: { projectId: string }) {
  const [entities, setEntities] = useState<Entity[]>([]);
  const [topics, setTopics] = useState<string[]>([]);
  const [selectedType, setSelectedType] = useState<string>('');

  useEffect(() => {
    loadConcepts();
  }, [projectId, selectedType]);

  const loadConcepts = async () => {
    const result = await getConceptRelationships(projectId, {
      entityType: selectedType || undefined,
      minMentions: 2,
      includeTopics: true
    });
    setEntities(result.entities);
    setTopics(result.topics || []);
  };

  const entityTypes = ['person', 'place', 'organization', 'technology', 'product', 'concept'];

  return (
    <div className="entity-browser">
      <h3>Concepts & Entities</h3>

      <div className="type-filter">
        <button
          className={!selectedType ? 'active' : ''}
          onClick={() => setSelectedType('')}
        >
          All
        </button>
        {entityTypes.map(type => (
          <button
            key={type}
            className={selectedType === type ? 'active' : ''}
            onClick={() => setSelectedType(type)}
          >
            {type}
          </button>
        ))}
      </div>

      <div className="entities-list">
        {entities.map(entity => (
          <div key={entity.id} className="entity-card">
            <div className="header">
              <span className="name">{entity.name}</span>
              <span className="type-badge">{entity.type}</span>
            </div>
            <div className="stats">
              <span>{entity.mention_count} mentions</span>
              <span>{entity.appears_in.length} videos</span>
            </div>
            <div className="appears-in">
              {entity.appears_in.map(wfId => (
                <span key={wfId} className="video-chip">{wfId}</span>
              ))}
            </div>
          </div>
        ))}
      </div>

      {topics.length > 0 && (
        <div className="topics-section">
          <h4>Topics</h4>
          <div className="topics-cloud">
            {topics.map(topic => (
              <span key={topic} className="topic-chip">{topic}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

### Similarity Search Panel

```tsx
function SimilaritySearchPanel({ projectId }: { projectId: string }) {
  const [segmentId, setSegmentId] = useState('');
  const [threshold, setThreshold] = useState(0.8);
  const [results, setResults] = useState<SimilarSegmentsResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);

  const handleSearch = async () => {
    if (!segmentId) return;

    setIsSearching(true);
    try {
      const response = await findSimilarSegments(projectId, segmentId, threshold);
      if ('results' in response) {
        setResults(response.results);
      }
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div className="similarity-search">
      <h3>Find Similar Segments</h3>

      <div className="search-form">
        <input
          type="text"
          placeholder="Segment ID (e.g., wf_001_45000)"
          value={segmentId}
          onChange={(e) => setSegmentId(e.target.value)}
        />

        <label>
          Similarity Threshold: {Math.round(threshold * 100)}%
          <input
            type="range"
            min={0.5}
            max={1}
            step={0.05}
            value={threshold}
            onChange={(e) => setThreshold(parseFloat(e.target.value))}
          />
        </label>

        <button onClick={handleSearch} disabled={isSearching || !segmentId}>
          {isSearching ? 'Searching...' : 'Find Similar'}
        </button>
      </div>

      {results.length > 0 && (
        <div className="results">
          <h4>Found {results.length} similar segments</h4>
          {results.map((result, index) => (
            <div key={index} className="result-item">
              <span className="segment-id">{result.segment_id}</span>
              <div className="similarity-bar">
                <div
                  className="fill"
                  style={{ width: `${result.similarity * 100}%` }}
                />
                <span className="value">
                  {Math.round(result.similarity * 100)}%
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

---

## Error Handling

### Common Errors

| Status Code | Error | Solution |
|-------------|-------|----------|
| 400 | "Knowledge graph not enabled" | Set `USE_KNOWLEDGE_GRAPH=true` |
| 400 | "FAISS search not enabled" | Set `USE_FAISS_SEARCH=true` |
| 400 | "segment_id required" | Provide segment_id parameter |
| 400 | "Unknown query_type" | Use valid query type |
| 404 | "Project not found" | Verify project ID |
| 503 | "Neo4j not available" | Check NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD |
| 503 | "FAISS not available" | Check FAISS configuration |

### Error Response Format

```json
{
  "error": "Knowledge graph not enabled",
  "hint": "Set USE_KNOWLEDGE_GRAPH=true"
}
```

---

## Configuration

### Required Environment Variables

```bash
# Enable knowledge graph
USE_KNOWLEDGE_GRAPH=true

# Neo4j connection
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
```

### Optional Configuration (for FAISS)

```bash
# Enable FAISS vector search
USE_FAISS_SEARCH=true

# TwelveLabs for embeddings
TWELVELABS_API_KEY=your_twelvelabs_api_key
```

---

## Workflow Integration

The Graph API provides data for visualization and queries throughout the AutoEdit pipeline:

```
Videos Indexed → [FAISS Embeddings] → [Neo4j Population] →
  ↓
[Graph Queries] → Intelligence Analysis → Narrative Analysis →
  ↓
[Visualization] → Project Dashboard
```

### Data Synchronization

The graph is populated through:

1. **Auto-sync**: When videos are analyzed
2. **Manual sync**: Via Cloud Tasks endpoint
3. **Background job**: Periodic synchronization

### Performance Considerations

- **Include Segments**: Can significantly increase node count; use sparingly
- **Max Depth**: Higher values return more data but slower queries
- **FAISS Queries**: Fast similarity search, but requires embedding indexing
- **Neo4j Queries**: More flexible but may be slower for large graphs
