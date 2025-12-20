# Phase 5: Visual API - Frontend Integration Guide

## Overview

The Visual API provides AI-powered visual enhancement recommendations including B-Roll, diagrams, data visualizations, maps, and text overlays. It analyzes video content to identify opportunities for visual enrichment and generates AI prompts for asset creation.

**Feature Flag Required**: `PHASE5_AGENTS_ENABLED=true`

## Endpoints Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/autoedit/project/{id}/visual/analyze-needs` | POST | Trigger visual analysis |
| `/v1/autoedit/project/{id}/visual/recommendations` | GET | Get project recommendations |
| `/v1/autoedit/workflow/{id}/visual/recommendations` | GET | Get workflow recommendations |
| `/v1/autoedit/project/{id}/visual/recommendations/{rec_id}/status` | PATCH | Update status (HITL) |

---

## 1. Analyze Visual Needs

Triggers AI analysis to identify visual enhancement opportunities across project videos.

### Request

```http
POST /v1/autoedit/project/{project_id}/visual/analyze-needs
Content-Type: application/json
X-API-Key: your_api_key
```

```json
{
  "workflow_ids": ["wf_001", "wf_002"],
  "types": ["broll", "diagram"],
  "force_reanalyze": false
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `workflow_ids` | string[] | null | Specific workflows to analyze (null = all) |
| `types` | string[] | null | Filter recommendation types |
| `force_reanalyze` | boolean | false | Reanalyze even if cached |

### Recommendation Types

| Type | Description |
|------|-------------|
| `broll` | Supplementary footage (stock video, screen recordings) |
| `diagram` | Technical diagrams, flowcharts, architecture |
| `data_visualization` | Charts, graphs, statistics |
| `map_animation` | Geographic visualizations, routes |
| `text_overlay` | Key points, quotes, callouts |
| `screenshot` | App/website screenshots |
| `animation` | Motion graphics, transitions |
| `infographic` | Data-rich visual summaries |

### Response

```json
{
  "project_id": "proj_abc123",
  "status": "completed",
  "total_recommendations": 15,
  "by_type": {
    "broll": 8,
    "diagram": 4,
    "data_visualization": 3
  },
  "high_priority_count": 5,
  "workflows_analyzed": 3,
  "analyzed_at": "2025-01-15T10:30:00Z"
}
```

### Response (Cached)

```json
{
  "project_id": "proj_abc123",
  "status": "cached",
  "message": "Analysis exists. Use force_reanalyze=true to refresh.",
  "total_recommendations": 15,
  "analyzed_at": "2025-01-15T10:30:00Z"
}
```

### Frontend Implementation

```typescript
interface AnalyzeVisualOptions {
  workflowIds?: string[];
  types?: VisualRecommendationType[];
  forceReanalyze?: boolean;
}

type VisualRecommendationType =
  | 'broll'
  | 'diagram'
  | 'data_visualization'
  | 'map_animation'
  | 'text_overlay'
  | 'screenshot'
  | 'animation'
  | 'infographic';

interface AnalyzeVisualResponse {
  project_id: string;
  status: 'completed' | 'cached';
  total_recommendations: number;
  by_type: Record<VisualRecommendationType, number>;
  high_priority_count: number;
  workflows_analyzed: number;
  analyzed_at: string;
  message?: string;
}

async function analyzeVisualNeeds(
  projectId: string,
  options: AnalyzeVisualOptions = {}
): Promise<AnalyzeVisualResponse> {
  const response = await fetch(
    `${API_BASE}/v1/autoedit/project/${projectId}/visual/analyze-needs`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY
      },
      body: JSON.stringify({
        workflow_ids: options.workflowIds,
        types: options.types,
        force_reanalyze: options.forceReanalyze ?? false
      })
    }
  );

  return response.json();
}
```

---

## 2. Get Project Recommendations

Retrieves all visual recommendations for a project with filtering and pagination.

### Request

```http
GET /v1/autoedit/project/{project_id}/visual/recommendations?type=broll&priority=high&status=pending&limit=50&offset=0
X-API-Key: your_api_key
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `type` | string | null | Filter by recommendation type |
| `priority` | string | null | Filter: "high", "medium", "low" |
| `status` | string | null | Filter: "pending", "accepted", "rejected" |
| `limit` | number | 50 | Max results per page |
| `offset` | number | 0 | Pagination offset |

### Response

```json
{
  "project_id": "proj_abc123",
  "recommendations": [
    {
      "id": "vis_001",
      "segment_id": "wf_001_45000",
      "workflow_id": "wf_001",
      "type": "diagram",
      "priority": "high",
      "status": "pending",
      "content": {
        "description": "Technical architecture diagram showing API flow",
        "context": "Speaker explains microservices communication",
        "timestamp_ms": 45000,
        "duration_ms": 12000
      },
      "generation": {
        "ai_prompt": "Create a clean, modern technical diagram showing a microservices architecture with three services (User Service, Order Service, Notification Service) connected via message queue. Use blue and white color scheme with minimal styling. Include API gateway at the top. Format: 1920x1080, PNG with transparency.",
        "recommended_tool": "DALL-E 3",
        "alternative_tools": ["Midjourney", "Canva", "Lucidchart"]
      },
      "alternatives": {
        "stock_keywords": ["microservices diagram", "api architecture", "system design"],
        "stock_sources": ["Shutterstock", "Getty Images", "Envato"]
      }
    },
    {
      "id": "vis_002",
      "segment_id": "wf_001_120000",
      "workflow_id": "wf_001",
      "type": "broll",
      "priority": "medium",
      "status": "pending",
      "content": {
        "description": "Footage of server room or data center",
        "context": "Discussion about cloud infrastructure",
        "timestamp_ms": 120000,
        "duration_ms": 8000
      },
      "generation": {
        "ai_prompt": "Modern data center with blue LED lighting, rows of server racks, cable management visible. Slight camera movement. Cinematic, professional look. 4K resolution, 10 seconds duration.",
        "recommended_tool": "Runway Gen-3",
        "alternative_tools": ["Pika Labs", "Sora"]
      },
      "alternatives": {
        "stock_keywords": ["data center", "server room", "cloud infrastructure", "networking"],
        "stock_sources": ["Storyblocks", "Pond5", "Artgrid"]
      }
    },
    {
      "id": "vis_003",
      "segment_id": "wf_002_60000",
      "workflow_id": "wf_002",
      "type": "data_visualization",
      "priority": "high",
      "status": "pending",
      "content": {
        "description": "Bar chart comparing performance metrics",
        "context": "Presenter discusses benchmark results",
        "timestamp_ms": 60000,
        "duration_ms": 15000,
        "data_hint": {
          "type": "bar_chart",
          "labels": ["Solution A", "Solution B", "Solution C"],
          "series": "Performance (ops/sec)",
          "values_mentioned": true
        }
      },
      "generation": {
        "ai_prompt": "Create an animated bar chart showing performance comparison. Three bars with labels 'Solution A', 'Solution B', 'Solution C'. Use gradient colors (blue to purple). Animate bars growing from zero. Include Y-axis label 'Operations per Second'. Modern, clean style. 1920x1080.",
        "recommended_tool": "After Effects",
        "alternative_tools": ["Flourish", "D3.js", "Motion Canvas"]
      },
      "alternatives": {
        "template_sources": ["Envato Elements", "Motion Array"]
      }
    }
  ],
  "total": 15,
  "filtered": 10,
  "returned": 3,
  "pagination": {
    "limit": 50,
    "offset": 0,
    "has_more": true
  },
  "analyzed_at": "2025-01-15T10:30:00Z"
}
```

### Frontend Implementation

```typescript
interface VisualRecommendation {
  id: string;
  segment_id: string;
  workflow_id: string;
  type: VisualRecommendationType;
  priority: 'high' | 'medium' | 'low';
  status: 'pending' | 'accepted' | 'rejected';
  content: {
    description: string;
    context: string;
    timestamp_ms: number;
    duration_ms: number;
    data_hint?: {
      type: string;
      labels?: string[];
      series?: string;
      values_mentioned?: boolean;
    };
  };
  generation: {
    ai_prompt: string;
    recommended_tool: string;
    alternative_tools: string[];
    custom_prompt?: string;  // User-modified prompt
  };
  alternatives: {
    stock_keywords?: string[];
    stock_sources?: string[];
    template_sources?: string[];
  };
  notes?: string;
  assigned_to?: string;
  updated_at?: string;
}

interface GetRecommendationsOptions {
  type?: VisualRecommendationType;
  priority?: 'high' | 'medium' | 'low';
  status?: 'pending' | 'accepted' | 'rejected';
  limit?: number;
  offset?: number;
}

interface VisualRecommendationsResponse {
  project_id: string;
  recommendations: VisualRecommendation[];
  total: number;
  filtered: number;
  returned: number;
  pagination: {
    limit: number;
    offset: number;
    has_more: boolean;
  };
  analyzed_at: string;
  status?: string;
  message?: string;
}

async function getVisualRecommendations(
  projectId: string,
  options: GetRecommendationsOptions = {}
): Promise<VisualRecommendationsResponse> {
  const params = new URLSearchParams();
  if (options.type) params.set('type', options.type);
  if (options.priority) params.set('priority', options.priority);
  if (options.status) params.set('status', options.status);
  if (options.limit) params.set('limit', options.limit.toString());
  if (options.offset) params.set('offset', options.offset.toString());

  const response = await fetch(
    `${API_BASE}/v1/autoedit/project/${projectId}/visual/recommendations?${params}`,
    {
      headers: { 'X-API-Key': API_KEY }
    }
  );

  return response.json();
}
```

---

## 3. Get Workflow Recommendations

Retrieves visual recommendations for a specific workflow/video with gap analysis.

### Request

```http
GET /v1/autoedit/workflow/{workflow_id}/visual/recommendations?type=broll&priority=high&include_ai_prompts=true&include_stock=true
X-API-Key: your_api_key
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `type` | string | null | Filter by recommendation type |
| `priority` | string | null | Filter by priority |
| `include_ai_prompts` | boolean | true | Include AI generation prompts |
| `include_stock` | boolean | true | Include stock search keywords |

### Response

```json
{
  "workflow_id": "wf_001",
  "recommendations": [
    {
      "id": "vis_001",
      "segment_id": "wf_001_45000",
      "type": "diagram",
      "priority": "high",
      "content": {...},
      "generation": {...},
      "alternatives": {...}
    }
  ],
  "gaps": [
    {
      "segment_id": "wf_001_180000",
      "timestamp_ms": 180000,
      "duration_ms": 25000,
      "type": "extended_talking_head",
      "severity": "medium",
      "suggestion": "Consider adding B-Roll or visual examples to break up long talking segment"
    },
    {
      "segment_id": "wf_001_300000",
      "timestamp_ms": 300000,
      "duration_ms": 10000,
      "type": "technical_concept",
      "severity": "high",
      "suggestion": "Technical explanation without visual aid - consider diagram or animation"
    }
  ],
  "total": 5
}
```

### Frontend Implementation

```typescript
interface VisualGap {
  segment_id: string;
  timestamp_ms: number;
  duration_ms: number;
  type: 'extended_talking_head' | 'technical_concept' | 'data_without_chart' | 'location_reference';
  severity: 'low' | 'medium' | 'high';
  suggestion: string;
}

interface WorkflowVisualResponse {
  workflow_id: string;
  recommendations: VisualRecommendation[];
  gaps: VisualGap[];
  total: number;
}

async function getWorkflowVisualRecommendations(
  workflowId: string,
  options: {
    type?: VisualRecommendationType;
    priority?: 'high' | 'medium' | 'low';
    includeAiPrompts?: boolean;
    includeStock?: boolean;
  } = {}
): Promise<WorkflowVisualResponse> {
  const params = new URLSearchParams();
  if (options.type) params.set('type', options.type);
  if (options.priority) params.set('priority', options.priority);
  params.set('include_ai_prompts', (options.includeAiPrompts ?? true).toString());
  params.set('include_stock', (options.includeStock ?? true).toString());

  const response = await fetch(
    `${API_BASE}/v1/autoedit/workflow/${workflowId}/visual/recommendations?${params}`,
    {
      headers: { 'X-API-Key': API_KEY }
    }
  );

  return response.json();
}
```

---

## 4. Update Recommendation Status (HITL Point)

This is a **Human-in-the-Loop** endpoint. Users review recommendations and mark them as accepted/rejected.

### Request

```http
PATCH /v1/autoedit/project/{project_id}/visual/recommendations/{rec_id}/status
Content-Type: application/json
X-API-Key: your_api_key
```

```json
{
  "status": "accepted",
  "notes": "Using custom diagram instead of AI-generated",
  "assigned_to": "design_team",
  "custom_prompt": "Modified prompt with specific branding requirements..."
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `status` | string | Yes | "accepted", "rejected", or "pending" |
| `notes` | string | No | User notes/comments |
| `assigned_to` | string | No | Assign to team/person |
| `custom_prompt` | string | No | Override AI generation prompt |

### Response

```json
{
  "project_id": "proj_abc123",
  "recommendation_id": "vis_001",
  "status": "accepted",
  "updated_at": "2025-01-15T11:00:00Z",
  "review_progress": {
    "total": 15,
    "accepted": 8,
    "rejected": 2,
    "pending": 5
  }
}
```

### Frontend Implementation

```typescript
interface UpdateRecommendationOptions {
  status: 'accepted' | 'rejected' | 'pending';
  notes?: string;
  assignedTo?: string;
  customPrompt?: string;
}

interface UpdateRecommendationResponse {
  project_id: string;
  recommendation_id: string;
  status: string;
  updated_at: string;
  review_progress: {
    total: number;
    accepted: number;
    rejected: number;
    pending: number;
  };
}

async function updateRecommendationStatus(
  projectId: string,
  recId: string,
  options: UpdateRecommendationOptions
): Promise<UpdateRecommendationResponse> {
  const response = await fetch(
    `${API_BASE}/v1/autoedit/project/${projectId}/visual/recommendations/${recId}/status`,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY
      },
      body: JSON.stringify({
        status: options.status,
        notes: options.notes,
        assigned_to: options.assignedTo,
        custom_prompt: options.customPrompt
      })
    }
  );

  return response.json();
}
```

---

## UI/UX Recommendations

### Visual Recommendations Dashboard

```tsx
import React, { useState, useEffect } from 'react';

function VisualRecommendationsPanel({ projectId }: { projectId: string }) {
  const [recommendations, setRecommendations] = useState<VisualRecommendation[]>([]);
  const [filter, setFilter] = useState<GetRecommendationsOptions>({});
  const [progress, setProgress] = useState({ total: 0, accepted: 0, rejected: 0, pending: 0 });

  useEffect(() => {
    loadRecommendations();
  }, [projectId, filter]);

  const loadRecommendations = async () => {
    const result = await getVisualRecommendations(projectId, filter);
    setRecommendations(result.recommendations);
  };

  const handleStatusUpdate = async (recId: string, status: 'accepted' | 'rejected') => {
    const result = await updateRecommendationStatus(projectId, recId, { status });
    setProgress(result.review_progress);
    loadRecommendations();
  };

  return (
    <div className="visual-recommendations">
      {/* Progress Bar */}
      <ProgressBar progress={progress} />

      {/* Filters */}
      <FilterBar
        onFilterChange={setFilter}
        types={['broll', 'diagram', 'data_visualization', 'map_animation']}
        priorities={['high', 'medium', 'low']}
        statuses={['pending', 'accepted', 'rejected']}
      />

      {/* Recommendations Grid */}
      <div className="recommendations-grid">
        {recommendations.map(rec => (
          <VisualRecommendationCard
            key={rec.id}
            recommendation={rec}
            onAccept={() => handleStatusUpdate(rec.id, 'accepted')}
            onReject={() => handleStatusUpdate(rec.id, 'rejected')}
          />
        ))}
      </div>
    </div>
  );
}
```

### Recommendation Card Component

```tsx
function VisualRecommendationCard({
  recommendation,
  onAccept,
  onReject
}: {
  recommendation: VisualRecommendation;
  onAccept: () => void;
  onReject: () => void;
}) {
  const [showPrompt, setShowPrompt] = useState(false);
  const [customPrompt, setCustomPrompt] = useState(recommendation.generation.ai_prompt);

  const typeIcons = {
    broll: '🎬',
    diagram: '📊',
    data_visualization: '📈',
    map_animation: '🗺️',
    text_overlay: '💬',
    screenshot: '📱',
    animation: '✨',
    infographic: '📋'
  };

  const priorityColors = {
    high: '#e74c3c',
    medium: '#f39c12',
    low: '#3498db'
  };

  const formatTimestamp = (ms: number) => {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className={`recommendation-card ${recommendation.status}`}>
      <div className="header">
        <span className="type-icon">{typeIcons[recommendation.type]}</span>
        <span className="type-label">{recommendation.type.replace('_', ' ')}</span>
        <span
          className="priority-badge"
          style={{ backgroundColor: priorityColors[recommendation.priority] }}
        >
          {recommendation.priority}
        </span>
      </div>

      <div className="content">
        <p className="description">{recommendation.content.description}</p>
        <div className="context">
          <span className="timestamp">
            @ {formatTimestamp(recommendation.content.timestamp_ms)}
          </span>
          <span className="duration">
            {Math.round(recommendation.content.duration_ms / 1000)}s
          </span>
        </div>
      </div>

      {/* AI Prompt Section */}
      <div className="generation-section">
        <button
          className="toggle-prompt"
          onClick={() => setShowPrompt(!showPrompt)}
        >
          {showPrompt ? 'Hide' : 'Show'} AI Prompt
        </button>

        {showPrompt && (
          <div className="prompt-editor">
            <textarea
              value={customPrompt}
              onChange={(e) => setCustomPrompt(e.target.value)}
              rows={4}
            />
            <div className="tools">
              <span>Recommended: {recommendation.generation.recommended_tool}</span>
              <div className="alternatives">
                {recommendation.generation.alternative_tools.map(tool => (
                  <span key={tool} className="tool-chip">{tool}</span>
                ))}
              </div>
            </div>
            <button
              className="copy-prompt"
              onClick={() => navigator.clipboard.writeText(customPrompt)}
            >
              Copy Prompt
            </button>
          </div>
        )}
      </div>

      {/* Stock Keywords */}
      {recommendation.alternatives.stock_keywords && (
        <div className="stock-section">
          <span className="label">Stock Search:</span>
          <div className="keywords">
            {recommendation.alternatives.stock_keywords.map(kw => (
              <span key={kw} className="keyword-chip">{kw}</span>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      {recommendation.status === 'pending' && (
        <div className="actions">
          <button className="accept" onClick={onAccept}>
            Accept
          </button>
          <button className="reject" onClick={onReject}>
            Reject
          </button>
        </div>
      )}

      {recommendation.status !== 'pending' && (
        <div className={`status-badge ${recommendation.status}`}>
          {recommendation.status}
        </div>
      )}
    </div>
  );
}
```

### Timeline Visualization with Gaps

```tsx
function VideoTimelineWithGaps({
  workflowId,
  duration_ms
}: {
  workflowId: string;
  duration_ms: number;
}) {
  const [data, setData] = useState<WorkflowVisualResponse | null>(null);

  useEffect(() => {
    loadData();
  }, [workflowId]);

  const loadData = async () => {
    const result = await getWorkflowVisualRecommendations(workflowId);
    setData(result);
  };

  if (!data) return <div>Loading...</div>;

  const getPositionPercent = (ms: number) => (ms / duration_ms) * 100;

  return (
    <div className="timeline-with-gaps">
      {/* Timeline Track */}
      <div className="timeline-track">
        {/* Recommendations */}
        {data.recommendations.map(rec => (
          <div
            key={rec.id}
            className={`recommendation-marker ${rec.type} ${rec.priority}`}
            style={{
              left: `${getPositionPercent(rec.content.timestamp_ms)}%`,
              width: `${getPositionPercent(rec.content.duration_ms)}%`
            }}
            title={rec.content.description}
          />
        ))}

        {/* Gaps */}
        {data.gaps.map((gap, index) => (
          <div
            key={index}
            className={`gap-marker ${gap.severity}`}
            style={{
              left: `${getPositionPercent(gap.timestamp_ms)}%`,
              width: `${getPositionPercent(gap.duration_ms)}%`
            }}
            title={gap.suggestion}
          />
        ))}
      </div>

      {/* Legend */}
      <div className="legend">
        <span className="legend-item broll">B-Roll</span>
        <span className="legend-item diagram">Diagram</span>
        <span className="legend-item data">Data Viz</span>
        <span className="legend-item gap">Visual Gap</span>
      </div>
    </div>
  );
}
```

---

## Error Handling

### Common Errors

| Status Code | Error | Solution |
|-------------|-------|----------|
| 400 | "Phase 5 agents not enabled" | Set `PHASE5_AGENTS_ENABLED=true` |
| 400 | "status must be: accepted, rejected, or pending" | Validate status value |
| 404 | "Project not found" | Verify project ID |
| 404 | "Workflow not found" | Verify workflow ID |
| 404 | "Recommendation {id} not found" | Verify recommendation ID |
| 503 | "Visual analyzer not available" | Set `GEMINI_API_KEY` |

---

## Configuration

### Required Environment Variables

```bash
# Enable Phase 5 agents
PHASE5_AGENTS_ENABLED=true

# Gemini API for visual analysis
GEMINI_API_KEY=your_gemini_api_key
```

### Optional Configuration

```bash
# Creator profile for style matching
CREATOR_GLOBAL_PROFILE='{"name":"Creator","style":"professional","brand_colors":["#3498db","#2ecc71"]}'
```

---

## Workflow Integration

The Visual API integrates after narrative analysis:

```
Narrative Analysis → [Visual Analysis] → Recommendation Generation →
  ↓
[HITL: Review Recommendations] → Accept/Reject → Asset Assignment →
  ↓
[Export Prompts/Keywords] → External Asset Creation →
  ↓
Continue to Preview/Render...
```

### Recommended Trigger Points

1. **Auto-trigger**: After narrative analysis completes
2. **Manual trigger**: User clicks "Analyze Visual Needs"
3. **Per-video trigger**: When reviewing individual workflow

### Asset Creation Workflow

1. Review recommendations in dashboard
2. Copy AI prompts for accepted items
3. Use prompts in DALL-E 3, Midjourney, Runway, etc.
4. Or use stock keywords to find existing assets
5. Upload created/sourced assets to project
6. Link assets to segments in timeline
