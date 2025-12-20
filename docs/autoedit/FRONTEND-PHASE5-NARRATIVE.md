# Phase 5: Narrative API - Frontend Integration Guide

## Overview

The Narrative API provides LLM-powered analysis of story structure, pacing, emotional arcs, and video reordering suggestions. It helps creators optimize the narrative flow of multi-video projects.

**Feature Flag Required**: `PHASE5_AGENTS_ENABLED=true`

## Endpoints Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/autoedit/project/{id}/narrative/analyze-structure` | POST | Trigger narrative analysis |
| `/v1/autoedit/project/{id}/narrative/structure` | GET | Get analysis results |
| `/v1/autoedit/project/{id}/narrative/reorder-suggestions` | GET | Get reordering suggestions |
| `/v1/autoedit/project/{id}/narrative/apply-reorder` | POST | Apply new order (HITL) |

---

## 1. Analyze Narrative Structure

Triggers comprehensive narrative analysis including structure detection, pacing, and emotional arcs.

### Request

```http
POST /v1/autoedit/project/{project_id}/narrative/analyze-structure
Content-Type: application/json
X-API-Key: your_api_key
```

```json
{
  "include_pacing": true,
  "include_emotional": true,
  "include_gaps": true,
  "force_reanalyze": false
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `include_pacing` | boolean | true | Analyze pacing for each video |
| `include_emotional` | boolean | true | Generate emotional arc analysis |
| `include_gaps` | boolean | true | Detect narrative gaps/issues |
| `force_reanalyze` | boolean | false | Reanalyze even if cached |

### Response

```json
{
  "project_id": "proj_abc123",
  "status": "completed",
  "detected_structure": "three_act",
  "confidence": 0.85,
  "video_count": 5,
  "analyzed_at": "2025-01-15T10:30:00Z"
}
```

### Detected Structure Types

| Type | Description |
|------|-------------|
| `three_act` | Setup, Confrontation, Resolution |
| `heros_journey` | 12-stage mythic structure |
| `tutorial` | Step-by-step instructional |
| `documentary` | Observational with interviews |
| `vlog` | Personal narrative/diary style |
| `review` | Product/service evaluation |
| `comparison` | A vs B format |
| `listicle` | List-based content |

### Frontend Implementation

```typescript
interface AnalyzeNarrativeOptions {
  includePacing?: boolean;
  includeEmotional?: boolean;
  includeGaps?: boolean;
  forceReanalyze?: boolean;
}

interface AnalyzeNarrativeResponse {
  project_id: string;
  status: 'completed' | 'cached';
  detected_structure: string;
  confidence: number;
  video_count: number;
  analyzed_at: string;
  message?: string;
}

async function analyzeNarrativeStructure(
  projectId: string,
  options: AnalyzeNarrativeOptions = {}
): Promise<AnalyzeNarrativeResponse> {
  const response = await fetch(
    `${API_BASE}/v1/autoedit/project/${projectId}/narrative/analyze-structure`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY
      },
      body: JSON.stringify({
        include_pacing: options.includePacing ?? true,
        include_emotional: options.includeEmotional ?? true,
        include_gaps: options.includeGaps ?? true,
        force_reanalyze: options.forceReanalyze ?? false
      })
    }
  );

  return response.json();
}
```

---

## 2. Get Narrative Structure

Retrieves the complete narrative analysis for a project.

### Request

```http
GET /v1/autoedit/project/{project_id}/narrative/structure?section=all
X-API-Key: your_api_key
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `section` | string | "all" | Filter: "structure", "pacing", "emotional", "gaps", "all" |

### Response (Full)

```json
{
  "project_id": "proj_abc123",
  "status": "completed",
  "structure_analysis": {
    "detected_structure": {
      "type": "three_act",
      "confidence": 0.85,
      "elements_found": {
        "setup": {
          "videos": ["wf_001"],
          "duration_ms": 180000,
          "key_elements": ["introduction", "context_setting", "hook"]
        },
        "confrontation": {
          "videos": ["wf_002", "wf_003"],
          "duration_ms": 420000,
          "key_elements": ["problem_introduction", "rising_action", "challenges"]
        },
        "resolution": {
          "videos": ["wf_004", "wf_005"],
          "duration_ms": 240000,
          "key_elements": ["solution", "conclusion", "call_to_action"]
        }
      }
    },
    "alternative_structures": [
      {
        "type": "tutorial",
        "confidence": 0.72
      }
    ]
  },
  "pacing_analysis": [
    {
      "workflow_id": "wf_001",
      "title": "Introduction",
      "pacing_score": 0.8,
      "issues": [],
      "segments_analysis": [
        {
          "segment_id": "seg_001",
          "duration_ms": 15000,
          "pacing": "optimal",
          "engagement_prediction": 0.85
        }
      ]
    }
  ],
  "emotional_arc": {
    "overall_arc": "rising_with_resolution",
    "arc_points": [
      {
        "video": "wf_001",
        "emotion": "curiosity",
        "intensity": 0.6,
        "position_pct": 0
      },
      {
        "video": "wf_003",
        "emotion": "tension",
        "intensity": 0.85,
        "position_pct": 50
      },
      {
        "video": "wf_005",
        "emotion": "satisfaction",
        "intensity": 0.9,
        "position_pct": 100
      }
    ],
    "emotional_consistency": 0.88
  },
  "narrative_gaps": [
    {
      "type": "missing_transition",
      "between": ["wf_002", "wf_003"],
      "severity": "medium",
      "suggestion": "Add bridging content between topic A and topic B"
    },
    {
      "type": "abrupt_ending",
      "video": "wf_005",
      "severity": "low",
      "suggestion": "Consider adding a brief recap before CTA"
    }
  ]
}
```

### Response (Section Filter)

When `section=pacing`:

```json
{
  "project_id": "proj_abc123",
  "pacing_analysis": [...]
}
```

### Frontend Implementation

```typescript
type NarrativeSection = 'all' | 'structure' | 'pacing' | 'emotional' | 'gaps';

interface StructureElement {
  videos: string[];
  duration_ms: number;
  key_elements: string[];
}

interface DetectedStructure {
  type: string;
  confidence: number;
  elements_found: {
    setup?: StructureElement;
    confrontation?: StructureElement;
    resolution?: StructureElement;
    [key: string]: StructureElement | undefined;
  };
}

interface PacingAnalysis {
  workflow_id: string;
  title: string;
  pacing_score: number;
  issues: string[];
  segments_analysis: Array<{
    segment_id: string;
    duration_ms: number;
    pacing: 'too_slow' | 'optimal' | 'too_fast';
    engagement_prediction: number;
  }>;
}

interface EmotionalArcPoint {
  video: string;
  emotion: string;
  intensity: number;
  position_pct: number;
}

interface NarrativeGap {
  type: string;
  between?: string[];
  video?: string;
  severity: 'low' | 'medium' | 'high';
  suggestion: string;
}

interface NarrativeStructureResponse {
  project_id: string;
  status: 'completed' | 'not_analyzed';
  structure_analysis?: {
    detected_structure: DetectedStructure;
    alternative_structures: Array<{ type: string; confidence: number }>;
  };
  pacing_analysis?: PacingAnalysis[];
  emotional_arc?: {
    overall_arc: string;
    arc_points: EmotionalArcPoint[];
    emotional_consistency: number;
  };
  narrative_gaps?: NarrativeGap[];
  message?: string;
}

async function getNarrativeStructure(
  projectId: string,
  section: NarrativeSection = 'all'
): Promise<NarrativeStructureResponse> {
  const response = await fetch(
    `${API_BASE}/v1/autoedit/project/${projectId}/narrative/structure?section=${section}`,
    {
      headers: { 'X-API-Key': API_KEY }
    }
  );

  return response.json();
}
```

---

## 3. Get Reorder Suggestions

Get AI-powered suggestions for reordering videos to improve narrative flow.

### Request

```http
GET /v1/autoedit/project/{project_id}/narrative/reorder-suggestions?min_confidence=0.6
X-API-Key: your_api_key
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `min_confidence` | number | 0.6 | Minimum confidence for suggestions |

### Response

```json
{
  "project_id": "proj_abc123",
  "current_order": ["wf_001", "wf_002", "wf_003", "wf_004", "wf_005"],
  "video_count": 5,
  "suggestions": [
    {
      "proposed_order": ["wf_001", "wf_003", "wf_002", "wf_004", "wf_005"],
      "confidence": 0.82,
      "rationale": "Video 3 introduces concepts referenced in Video 2. Swapping improves logical flow.",
      "impact": {
        "narrative_flow": "improved",
        "learning_curve": "smoother",
        "viewer_retention_prediction": "+12%"
      },
      "changes": [
        {
          "video": "wf_003",
          "from_position": 2,
          "to_position": 1
        },
        {
          "video": "wf_002",
          "from_position": 1,
          "to_position": 2
        }
      ]
    }
  ],
  "total_suggestions": 2,
  "filtered_by_confidence": 0.6
}
```

### No Reordering Needed

```json
{
  "project_id": "proj_abc123",
  "message": "Single video project, no reordering needed",
  "current_order": ["wf_001"],
  "suggestions": []
}
```

### Frontend Implementation

```typescript
interface ReorderChange {
  video: string;
  from_position: number;
  to_position: number;
}

interface ReorderSuggestion {
  proposed_order: string[];
  confidence: number;
  rationale: string;
  impact: {
    narrative_flow: string;
    learning_curve: string;
    viewer_retention_prediction: string;
  };
  changes: ReorderChange[];
}

interface ReorderSuggestionsResponse {
  project_id: string;
  current_order: string[];
  video_count: number;
  suggestions: ReorderSuggestion[];
  total_suggestions: number;
  filtered_by_confidence: number;
  message?: string;
}

async function getReorderSuggestions(
  projectId: string,
  minConfidence: number = 0.6
): Promise<ReorderSuggestionsResponse> {
  const response = await fetch(
    `${API_BASE}/v1/autoedit/project/${projectId}/narrative/reorder-suggestions?min_confidence=${minConfidence}`,
    {
      headers: { 'X-API-Key': API_KEY }
    }
  );

  return response.json();
}
```

---

## 4. Apply Reorder (HITL Point)

This is a **Human-in-the-Loop** endpoint. The user reviews suggestions and chooses the final order.

### Request

```http
POST /v1/autoedit/project/{project_id}/narrative/apply-reorder
Content-Type: application/json
X-API-Key: your_api_key
```

```json
{
  "new_order": ["wf_001", "wf_003", "wf_002", "wf_004", "wf_005"],
  "suggestion_index": 0,
  "reason": "suggestion_0"
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `new_order` | string[] | Yes | Complete ordered list of workflow IDs |
| `suggestion_index` | number | No | Which AI suggestion was used |
| `reason` | string | No | Tracking: "user_choice", "suggestion_0", etc. |

### Response

```json
{
  "project_id": "proj_abc123",
  "applied": true,
  "previous_order": ["wf_001", "wf_002", "wf_003", "wf_004", "wf_005"],
  "new_order": ["wf_001", "wf_003", "wf_002", "wf_004", "wf_005"],
  "changes": [
    {
      "workflow_id": "wf_003",
      "from_index": 2,
      "to_index": 1
    },
    {
      "workflow_id": "wf_002",
      "from_index": 1,
      "to_index": 2
    }
  ]
}
```

### Order Unchanged

```json
{
  "project_id": "proj_abc123",
  "applied": false,
  "message": "Order unchanged"
}
```

### Validation Error

```json
{
  "error": "new_order must contain exactly the same workflow IDs",
  "expected": ["wf_001", "wf_002", "wf_003"],
  "received": ["wf_001", "wf_002"]
}
```

### Frontend Implementation

```typescript
interface ApplyReorderOptions {
  newOrder: string[];
  suggestionIndex?: number;
  reason?: 'user_choice' | `suggestion_${number}` | string;
}

interface ApplyReorderResponse {
  project_id: string;
  applied: boolean;
  previous_order?: string[];
  new_order?: string[];
  changes?: Array<{
    workflow_id: string;
    from_index: number;
    to_index: number;
  }>;
  message?: string;
  error?: string;
}

async function applyReorder(
  projectId: string,
  options: ApplyReorderOptions
): Promise<ApplyReorderResponse> {
  const response = await fetch(
    `${API_BASE}/v1/autoedit/project/${projectId}/narrative/apply-reorder`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY
      },
      body: JSON.stringify({
        new_order: options.newOrder,
        suggestion_index: options.suggestionIndex,
        reason: options.reason
      })
    }
  );

  return response.json();
}
```

---

## UI/UX Recommendations

### Narrative Dashboard Component

```tsx
import React, { useState, useEffect } from 'react';

function NarrativeDashboard({ projectId }: { projectId: string }) {
  const [narrative, setNarrative] = useState<NarrativeStructureResponse | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  useEffect(() => {
    loadNarrative();
  }, [projectId]);

  const loadNarrative = async () => {
    const result = await getNarrativeStructure(projectId);
    setNarrative(result);
  };

  const handleAnalyze = async () => {
    setIsAnalyzing(true);
    await analyzeNarrativeStructure(projectId);
    await loadNarrative();
    setIsAnalyzing(false);
  };

  if (!narrative || narrative.status === 'not_analyzed') {
    return (
      <div className="narrative-empty">
        <h3>Narrative Analysis</h3>
        <p>Analyze your project's narrative structure, pacing, and emotional arc.</p>
        <button onClick={handleAnalyze} disabled={isAnalyzing}>
          {isAnalyzing ? 'Analyzing...' : 'Analyze Narrative'}
        </button>
      </div>
    );
  }

  return (
    <div className="narrative-dashboard">
      <StructureCard structure={narrative.structure_analysis} />
      <EmotionalArcChart arc={narrative.emotional_arc} />
      <PacingOverview pacing={narrative.pacing_analysis} />
      <NarrativeGapsAlert gaps={narrative.narrative_gaps} />
    </div>
  );
}
```

### Structure Visualization

```tsx
function StructureCard({ structure }: { structure: any }) {
  const structureIcons = {
    three_act: '🎭',
    heros_journey: '🗡️',
    tutorial: '📚',
    documentary: '🎬',
    vlog: '📹'
  };

  const detected = structure?.detected_structure;
  if (!detected) return null;

  return (
    <div className="structure-card">
      <div className="header">
        <span className="icon">{structureIcons[detected.type] || '📊'}</span>
        <h4>{detected.type.replace('_', ' ').toUpperCase()}</h4>
        <span className="confidence">
          {Math.round(detected.confidence * 100)}% confidence
        </span>
      </div>

      <div className="elements">
        {Object.entries(detected.elements_found || {}).map(([key, element]: [string, any]) => (
          <div key={key} className="element">
            <strong>{key}</strong>
            <span>{element.videos.length} video(s)</span>
            <span>{Math.round(element.duration_ms / 1000)}s</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

### Emotional Arc Chart

```tsx
function EmotionalArcChart({ arc }: { arc: any }) {
  if (!arc) return null;

  const emotionColors = {
    curiosity: '#3498db',
    excitement: '#e74c3c',
    tension: '#e67e22',
    satisfaction: '#2ecc71',
    neutral: '#95a5a6'
  };

  return (
    <div className="emotional-arc-chart">
      <h4>Emotional Arc: {arc.overall_arc}</h4>
      <div className="arc-visualization">
        {arc.arc_points.map((point: EmotionalArcPoint, index: number) => (
          <div
            key={index}
            className="arc-point"
            style={{
              left: `${point.position_pct}%`,
              bottom: `${point.intensity * 100}%`,
              backgroundColor: emotionColors[point.emotion] || '#95a5a6'
            }}
            title={`${point.emotion}: ${Math.round(point.intensity * 100)}%`}
          >
            <span className="label">{point.emotion}</span>
          </div>
        ))}
        <svg className="arc-line">
          {/* Draw connecting line through points */}
        </svg>
      </div>
      <div className="consistency">
        Emotional Consistency: {Math.round(arc.emotional_consistency * 100)}%
      </div>
    </div>
  );
}
```

### Video Reorder Interface

```tsx
function VideoReorderPanel({ projectId }: { projectId: string }) {
  const [suggestions, setSuggestions] = useState<ReorderSuggestionsResponse | null>(null);
  const [currentOrder, setCurrentOrder] = useState<string[]>([]);
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    loadSuggestions();
  }, [projectId]);

  const loadSuggestions = async () => {
    const result = await getReorderSuggestions(projectId, 0.5);
    setSuggestions(result);
    setCurrentOrder(result.current_order);
  };

  const handleApplySuggestion = async (suggestion: ReorderSuggestion, index: number) => {
    const result = await applyReorder(projectId, {
      newOrder: suggestion.proposed_order,
      suggestionIndex: index,
      reason: `suggestion_${index}`
    });

    if (result.applied) {
      setCurrentOrder(suggestion.proposed_order);
      // Refresh suggestions after applying
      loadSuggestions();
    }
  };

  const handleManualReorder = async (newOrder: string[]) => {
    const result = await applyReorder(projectId, {
      newOrder,
      reason: 'user_choice'
    });

    if (result.applied) {
      setCurrentOrder(newOrder);
    }
  };

  return (
    <div className="reorder-panel">
      <h3>Video Order</h3>

      {/* Draggable video list */}
      <DraggableVideoList
        videos={currentOrder}
        onReorder={handleManualReorder}
      />

      {/* AI Suggestions */}
      {suggestions?.suggestions && suggestions.suggestions.length > 0 && (
        <div className="suggestions">
          <h4>AI Suggestions</h4>
          {suggestions.suggestions.map((suggestion, index) => (
            <div key={index} className="suggestion-card">
              <div className="confidence">
                {Math.round(suggestion.confidence * 100)}% confidence
              </div>
              <p className="rationale">{suggestion.rationale}</p>
              <div className="impact">
                <span>Flow: {suggestion.impact.narrative_flow}</span>
                <span>Retention: {suggestion.impact.viewer_retention_prediction}</span>
              </div>
              <button onClick={() => handleApplySuggestion(suggestion, index)}>
                Apply This Order
              </button>
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
| 400 | "Phase 5 agents not enabled" | Set `PHASE5_AGENTS_ENABLED=true` |
| 400 | "new_order must contain exactly the same workflow IDs" | Validate order before submitting |
| 404 | "Project not found" | Verify project ID |
| 503 | "Narrative analyzer not available" | Set `GEMINI_API_KEY` |

---

## Configuration

### Required Environment Variables

```bash
# Enable Phase 5 agents
PHASE5_AGENTS_ENABLED=true

# Gemini API for LLM analysis
GEMINI_API_KEY=your_gemini_api_key
```

### Optional Configuration

```bash
# Creator profile for personalized analysis
CREATOR_GLOBAL_PROFILE='{"name":"Creator","style":"educational","typical_content":["tutorials","reviews"]}'
```

---

## Workflow Integration

The Narrative API integrates at the **project level** after all videos are analyzed:

```
Videos Analyzed → [Narrative Analysis] → Structure Detection →
  ↓
[Pacing Analysis] → [Emotional Arc] → [Gap Detection] →
  ↓
[Reorder Suggestions] → [HITL: Review & Apply] →
  ↓
Continue to Visual Analysis...
```

### Recommended Trigger Points

1. **Auto-trigger**: When all videos in a project reach `analyzed` state
2. **Manual trigger**: When user clicks "Analyze Narrative" in project view
3. **Re-analyze**: When user reorders videos or adds new videos
