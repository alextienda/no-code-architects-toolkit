# Phase 5: Intelligence API - Frontend Integration Guide

## Overview

The Intelligence API provides LLM-powered redundancy analysis that goes beyond simple "first occurrence wins" logic. Instead, it evaluates **quality** of each segment to recommend which version to keep when redundancies are detected.

**Feature Flag Required**: `PHASE5_AGENTS_ENABLED=true`

## Endpoints Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/autoedit/project/{id}/intelligence/analyze-redundancy-quality` | POST | Trigger LLM analysis |
| `/v1/autoedit/project/{id}/intelligence/redundancy-recommendations` | GET | Get recommendations |
| `/v1/autoedit/project/{id}/intelligence/apply-smart-recommendations` | POST | Apply selections (HITL) |

---

## 1. Analyze Redundancy Quality

Triggers LLM analysis of redundant segments using FAISS vector search + Gemini evaluation.

### Request

```http
POST /v1/autoedit/project/{project_id}/intelligence/analyze-redundancy-quality
Content-Type: application/json
X-API-Key: your_api_key
```

```json
{
  "similarity_threshold": 0.85,
  "max_groups": 20,
  "force_reanalyze": false
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `similarity_threshold` | number | 0.85 | Minimum similarity for redundancy detection (0.0-1.0) |
| `max_groups` | number | 20 | Maximum redundancy groups to analyze |
| `force_reanalyze` | boolean | false | Reanalyze even if cached results exist |

### Response (Synchronous - Small Projects)

```json
{
  "project_id": "proj_abc123",
  "status": "completed",
  "groups_analyzed": 5,
  "total_pairs": 12,
  "analyzed_at": "2025-01-15T10:30:00Z"
}
```

### Response (Async - Large Projects)

```json
{
  "project_id": "proj_abc123",
  "status": "analyzing",
  "message": "Analysis started asynchronously",
  "task_name": "projects/xxx/locations/xxx/queues/xxx/tasks/xxx"
}
```

**HTTP Status**: `202 Accepted` for async processing

### Response (Cached)

```json
{
  "project_id": "proj_abc123",
  "status": "cached",
  "message": "Analysis already exists. Use force_reanalyze=true to refresh.",
  "analyzed_at": "2025-01-15T10:30:00Z",
  "groups_analyzed": 5
}
```

### Frontend Implementation

```typescript
interface AnalyzeRedundancyOptions {
  similarityThreshold?: number;
  maxGroups?: number;
  forceReanalyze?: boolean;
}

interface AnalyzeRedundancyResponse {
  project_id: string;
  status: 'completed' | 'analyzing' | 'cached';
  groups_analyzed?: number;
  total_pairs?: number;
  analyzed_at?: string;
  task_name?: string;
  message?: string;
}

async function analyzeRedundancyQuality(
  projectId: string,
  options: AnalyzeRedundancyOptions = {}
): Promise<AnalyzeRedundancyResponse> {
  const response = await fetch(
    `${API_BASE}/v1/autoedit/project/${projectId}/intelligence/analyze-redundancy-quality`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY
      },
      body: JSON.stringify({
        similarity_threshold: options.similarityThreshold ?? 0.85,
        max_groups: options.maxGroups ?? 20,
        force_reanalyze: options.forceReanalyze ?? false
      })
    }
  );

  return response.json();
}
```

---

## 2. Get Redundancy Recommendations

Retrieves LLM-analyzed recommendations for which segments to keep.

### Request

```http
GET /v1/autoedit/project/{project_id}/intelligence/redundancy-recommendations?min_confidence=0.5&include_analysis=false
X-API-Key: your_api_key
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `min_confidence` | number | 0.5 | Minimum confidence score (0.0-1.0) |
| `include_analysis` | boolean | false | Include detailed LLM analysis |

### Response

```json
{
  "project_id": "proj_abc123",
  "status": "completed",
  "recommendations": [
    {
      "group_id": "group_0",
      "keep_segment_id": "wf_001_45000",
      "remove_segment_ids": ["wf_002_120000"],
      "confidence": 0.92,
      "primary_reason": "Better delivery quality and clearer articulation"
    },
    {
      "group_id": "group_1",
      "keep_segment_id": "wf_003_30000",
      "remove_segment_ids": ["wf_001_180000", "wf_002_60000"],
      "confidence": 0.78,
      "primary_reason": "More comprehensive explanation with visual context"
    }
  ],
  "summary": {
    "total_groups": 5,
    "filtered_groups": 4,
    "high_confidence": 3,
    "segments_to_remove": 7
  },
  "analyzed_at": "2025-01-15T10:30:00Z"
}
```

### Response with Detailed Analysis

When `include_analysis=true`:

```json
{
  "recommendations": [
    {
      "group_id": "group_0",
      "keep_segment_id": "wf_001_45000",
      "remove_segment_ids": ["wf_002_120000"],
      "confidence": 0.92,
      "primary_reason": "Better delivery quality",
      "detailed_analysis": {
        "quality_scores": {
          "wf_001_45000": {
            "delivery": 0.9,
            "clarity": 0.88,
            "completeness": 0.85,
            "overall": 0.88
          },
          "wf_002_120000": {
            "delivery": 0.7,
            "clarity": 0.72,
            "completeness": 0.80,
            "overall": 0.74
          }
        },
        "comparison_notes": "Segment wf_001_45000 has better audio quality and more confident delivery"
      }
    }
  ]
}
```

### Frontend Implementation

```typescript
interface RedundancyRecommendation {
  group_id: string;
  keep_segment_id: string;
  remove_segment_ids: string[];
  confidence: number;
  primary_reason: string;
  detailed_analysis?: {
    quality_scores: Record<string, {
      delivery: number;
      clarity: number;
      completeness: number;
      overall: number;
    }>;
    comparison_notes: string;
  };
}

interface RedundancyRecommendationsResponse {
  project_id: string;
  status: 'completed' | 'analyzing' | 'not_analyzed';
  recommendations: RedundancyRecommendation[];
  summary: {
    total_groups: number;
    filtered_groups: number;
    high_confidence: number;
    segments_to_remove: number;
  };
  analyzed_at?: string;
  message?: string;
}

async function getRedundancyRecommendations(
  projectId: string,
  minConfidence: number = 0.5,
  includeAnalysis: boolean = false
): Promise<RedundancyRecommendationsResponse> {
  const params = new URLSearchParams({
    min_confidence: minConfidence.toString(),
    include_analysis: includeAnalysis.toString()
  });

  const response = await fetch(
    `${API_BASE}/v1/autoedit/project/${projectId}/intelligence/redundancy-recommendations?${params}`,
    {
      headers: { 'X-API-Key': API_KEY }
    }
  );

  return response.json();
}
```

---

## 3. Apply Smart Recommendations (HITL Point)

This is a **Human-in-the-Loop** endpoint. The user reviews recommendations and selects which to apply.

### Request

```http
POST /v1/autoedit/project/{project_id}/intelligence/apply-smart-recommendations
Content-Type: application/json
X-API-Key: your_api_key
```

```json
{
  "group_ids": ["group_0", "group_1"],
  "min_confidence": 0.7,
  "dry_run": false
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `group_ids` | string[] | null | Specific groups to apply (null = all) |
| `min_confidence` | number | 0.7 | Only apply high-confidence recommendations |
| `dry_run` | boolean | false | Preview changes without applying |

### Response

```json
{
  "project_id": "proj_abc123",
  "applied": true,
  "dry_run": false,
  "changes": [
    {
      "workflow_id": "wf_002",
      "segment_id": "wf_002_120000",
      "reason": "Better delivery quality"
    },
    {
      "workflow_id": "wf_001",
      "segment_id": "wf_001_180000",
      "reason": "More comprehensive explanation"
    }
  ],
  "summary": {
    "segments_marked_remove": 5,
    "workflows_affected": 2
  }
}
```

### Dry Run Response

When `dry_run: true`:

```json
{
  "project_id": "proj_abc123",
  "applied": false,
  "dry_run": true,
  "changes": [...],
  "summary": {
    "segments_marked_remove": 5,
    "workflows_affected": 2
  }
}
```

### Frontend Implementation

```typescript
interface ApplyRecommendationsOptions {
  groupIds?: string[];
  minConfidence?: number;
  dryRun?: boolean;
}

interface ApplyRecommendationsResponse {
  project_id: string;
  applied: boolean;
  dry_run: boolean;
  changes: Array<{
    workflow_id: string;
    segment_id: string;
    reason: string;
  }>;
  summary: {
    segments_marked_remove: number;
    workflows_affected: number;
  };
}

async function applySmartRecommendations(
  projectId: string,
  options: ApplyRecommendationsOptions = {}
): Promise<ApplyRecommendationsResponse> {
  const response = await fetch(
    `${API_BASE}/v1/autoedit/project/${projectId}/intelligence/apply-smart-recommendations`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY
      },
      body: JSON.stringify({
        group_ids: options.groupIds,
        min_confidence: options.minConfidence ?? 0.7,
        dry_run: options.dryRun ?? false
      })
    }
  );

  return response.json();
}
```

---

## UI/UX Recommendations

### Redundancy Review Interface

```tsx
import React, { useState, useEffect } from 'react';

interface RedundancyGroup {
  group_id: string;
  keep_segment_id: string;
  remove_segment_ids: string[];
  confidence: number;
  primary_reason: string;
}

function RedundancyReviewPanel({ projectId }: { projectId: string }) {
  const [recommendations, setRecommendations] = useState<RedundancyGroup[]>([]);
  const [selectedGroups, setSelectedGroups] = useState<Set<string>>(new Set());
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [status, setStatus] = useState<string>('');

  // Trigger analysis
  const handleAnalyze = async () => {
    setIsAnalyzing(true);
    const result = await analyzeRedundancyQuality(projectId, {
      similarityThreshold: 0.85
    });

    if (result.status === 'analyzing') {
      // Poll for completion
      pollForCompletion(projectId);
    } else if (result.status === 'completed') {
      loadRecommendations();
    }
    setIsAnalyzing(false);
  };

  // Load recommendations
  const loadRecommendations = async () => {
    const result = await getRedundancyRecommendations(projectId, 0.5, true);
    setRecommendations(result.recommendations);
    setStatus(result.status);
  };

  // Toggle group selection
  const toggleGroup = (groupId: string) => {
    const newSelected = new Set(selectedGroups);
    if (newSelected.has(groupId)) {
      newSelected.delete(groupId);
    } else {
      newSelected.add(groupId);
    }
    setSelectedGroups(newSelected);
  };

  // Apply selected recommendations
  const handleApply = async (dryRun: boolean = false) => {
    const result = await applySmartRecommendations(projectId, {
      groupIds: Array.from(selectedGroups),
      minConfidence: 0.5,
      dryRun
    });

    if (!dryRun && result.applied) {
      // Refresh the page or update state
      loadRecommendations();
    }

    return result;
  };

  return (
    <div className="redundancy-review">
      <header>
        <h2>Intelligent Redundancy Analysis</h2>
        <button onClick={handleAnalyze} disabled={isAnalyzing}>
          {isAnalyzing ? 'Analyzing...' : 'Analyze Redundancies'}
        </button>
      </header>

      {status === 'not_analyzed' && (
        <div className="empty-state">
          <p>No analysis available. Click "Analyze Redundancies" to start.</p>
        </div>
      )}

      {recommendations.length > 0 && (
        <>
          <div className="recommendations-list">
            {recommendations.map(rec => (
              <RedundancyGroupCard
                key={rec.group_id}
                recommendation={rec}
                isSelected={selectedGroups.has(rec.group_id)}
                onToggle={() => toggleGroup(rec.group_id)}
              />
            ))}
          </div>

          <footer className="actions">
            <button onClick={() => handleApply(true)}>
              Preview Changes
            </button>
            <button
              onClick={() => handleApply(false)}
              disabled={selectedGroups.size === 0}
              className="primary"
            >
              Apply {selectedGroups.size} Selection(s)
            </button>
          </footer>
        </>
      )}
    </div>
  );
}

function RedundancyGroupCard({
  recommendation,
  isSelected,
  onToggle
}: {
  recommendation: RedundancyGroup;
  isSelected: boolean;
  onToggle: () => void;
}) {
  const confidenceColor = recommendation.confidence >= 0.8
    ? 'green'
    : recommendation.confidence >= 0.6
      ? 'yellow'
      : 'red';

  return (
    <div className={`group-card ${isSelected ? 'selected' : ''}`}>
      <div className="header">
        <input
          type="checkbox"
          checked={isSelected}
          onChange={onToggle}
        />
        <span className={`confidence ${confidenceColor}`}>
          {Math.round(recommendation.confidence * 100)}% confidence
        </span>
      </div>

      <div className="content">
        <div className="keep">
          <span className="label">Keep:</span>
          <span className="segment-id">{recommendation.keep_segment_id}</span>
        </div>

        <div className="remove">
          <span className="label">Remove:</span>
          {recommendation.remove_segment_ids.map(id => (
            <span key={id} className="segment-id strikethrough">{id}</span>
          ))}
        </div>

        <p className="reason">{recommendation.primary_reason}</p>
      </div>
    </div>
  );
}
```

### Confidence Thresholds

| Confidence | Color | Action |
|------------|-------|--------|
| >= 0.8 | Green | Auto-apply recommended |
| 0.6 - 0.8 | Yellow | Review recommended |
| < 0.6 | Red | Manual review required |

---

## Error Handling

### Common Errors

| Status Code | Error | Solution |
|-------------|-------|----------|
| 400 | "Phase 5 agents not enabled" | Set `PHASE5_AGENTS_ENABLED=true` |
| 404 | "Project not found" | Verify project ID |
| 503 | "Intelligence analyzer not available" | Set `GEMINI_API_KEY` |
| 503 | "FAISS not available" | Set `USE_FAISS_SEARCH=true` |

### Error Response Format

```json
{
  "error": "Phase 5 agents not enabled",
  "hint": "Set PHASE5_AGENTS_ENABLED=true"
}
```

---

## Configuration

### Required Environment Variables

```bash
# Enable Phase 5 agents
PHASE5_AGENTS_ENABLED=true

# Gemini API for LLM analysis
GEMINI_API_KEY=your_gemini_api_key

# FAISS vector search (required for similarity detection)
USE_FAISS_SEARCH=true
```

### Optional Configuration

```bash
# TwelveLabs for video embeddings
TWELVELABS_API_KEY=your_twelvelabs_api_key

# Creator profile for context
CREATOR_GLOBAL_PROFILE='{"name":"Creator Name","style":"educational"}'
```

---

## Workflow Integration

The Intelligence API integrates with the AutoEdit pipeline at the **post-analysis** stage:

```
Video Upload → Transcription → AI Analysis →
  ↓
[FAISS Indexing] → [Similarity Detection] →
  ↓
[LLM Quality Analysis] → [HITL: Redundancy Review] →
  ↓
Continue to Preview...
```

### Recommended UI Flow

1. **Automatic Trigger**: After transcription completes, optionally auto-trigger redundancy analysis
2. **Review Panel**: Show recommendations in a dedicated review panel
3. **Batch Apply**: Allow users to accept/reject recommendations in batch
4. **Preview Impact**: Show "dry run" results before final application
5. **Undo Support**: Track applied changes for potential rollback
