# Multi-Video Consolidation Guide

> **Guía para frontend:** Detección de redundancias y consolidación multi-video.

## Concepto

La **Consolidación Multi-Video** analiza todos los videos de un proyecto para:

1. Generar embeddings con TwelveLabs Marengo 3.0
2. Detectar redundancias (contenido similar entre videos)
3. Analizar narrativa global del proyecto
4. Generar recomendaciones de qué eliminar
5. Aplicar cambios automáticamente o con revisión humana (HITL 3)

## Estados de Consolidación

```
not_started → generating_embeddings → generating_summaries → detecting_redundancies
                                                                     ↓
                                                          analyzing_narrative
                                                                     ↓
                                                              consolidated
                                                                     ↓
                                    ┌────────────────────────────────────────┐
                                    ▼                                        ▼
                          review_consolidation                  consolidation_complete
                          (HITL 3 opcional)                      (auto-aplicado)
```

| Estado | Descripción |
|--------|-------------|
| `not_started` | No iniciada |
| `generating_embeddings` | Generando embeddings TwelveLabs |
| `generating_summaries` | Generando resúmenes Gemini |
| `detecting_redundancies` | Detectando contenido similar |
| `analyzing_narrative` | Analizando arco narrativo |
| `consolidated` | Listo para revisión |
| `consolidation_complete` | Proceso completado |
| `consolidation_failed` | Error |
| `invalidated` | Inválida (videos reordenados) |

## Flujo de Uso

```
PASO 1: Verificar que todos los videos estén en pending_review_1 o posterior
PASO 2: POST /v1/autoedit/project/{id}/consolidate
PASO 3: GET /v1/autoedit/project/{id}/consolidation-status (polling)
PASO 4: GET redundancies, narrative, recommendations
PASO 5: POST /v1/autoedit/project/{id}/apply-recommendations (HITL 3)
```

---

## Endpoints

### POST /project/{id}/consolidate - Iniciar Consolidación

```javascript
const response = await fetch(`/v1/autoedit/project/${projectId}/consolidate`, {
  method: 'POST',
  headers: { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' },
  body: JSON.stringify({
    force_regenerate: false,      // Regenerar embeddings
    redundancy_threshold: 0.85,   // 85% similitud = redundancia
    auto_apply: false             // Requiere revisión humana
  })
});
```

### GET /project/{id}/consolidation-status - Monitorear Estado

```javascript
const response = await fetch(`/v1/autoedit/project/${projectId}/consolidation-status`, {
  headers: { 'X-API-Key': API_KEY }
});
const { consolidation_state } = (await response.json()).response;
// Polling cada 5 segundos hasta: consolidated, consolidation_complete, o consolidation_failed
```

### GET /project/{id}/redundancies - Obtener Redundancias

```javascript
const response = await fetch(`/v1/autoedit/project/${projectId}/redundancies`, {
  headers: { 'X-API-Key': API_KEY }
});
```

**Respuesta:**
```json
{
  "redundancy_count": 5,
  "redundancy_score": 42.5,
  "interpretation": "Moderate redundancy",
  "redundancies": [{
    "id": "red_abc_def_0",
    "video_a": { "workflow_id": "wf_abc", "segment": { "start_sec": 30, "end_sec": 45 } },
    "video_b": { "workflow_id": "wf_def", "segment": { "start_sec": 60, "end_sec": 75 } },
    "similarity": 0.92,
    "severity": "high"
  }]
}
```

### GET /project/{id}/narrative - Análisis Narrativo

```javascript
const response = await fetch(`/v1/autoedit/project/${projectId}/narrative`, {
  headers: { 'X-API-Key': API_KEY }
});
```

**Respuesta:**
```json
{
  "arc_type": "complete",
  "narrative_functions": { "introduction": 1, "rising_action": 2, "climax": 1, "resolution": 1 },
  "tone_consistency": 0.85,
  "unique_tones": ["informativo", "entusiasta"],
  "video_sequence": [{ "index": 0, "function": "introduction", "tone": "informativo" }]
}
```

### GET /project/{id}/recommendations - Obtener Recomendaciones

```javascript
const response = await fetch(`/v1/autoedit/project/${projectId}/recommendations`, {
  headers: { 'X-API-Key': API_KEY }
});
```

**Respuesta:**
```json
{
  "recommendations": [{
    "id": "rec_red_abc_def_0",
    "type": "remove_redundant_segment",
    "priority": "high",
    "reason": "Similar content (92%) already in video 1",
    "estimated_savings_sec": 15,
    "action": { "workflow_id": "wf_def", "segment": { "start_sec": 60, "end_sec": 75 } }
  }],
  "total_savings_sec": 45
}
```

### POST /project/{id}/apply-recommendations - Aplicar Cambios

```javascript
await fetch(`/v1/autoedit/project/${projectId}/apply-recommendations`, {
  method: 'POST',
  headers: { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' },
  body: JSON.stringify({
    recommendation_ids: null  // null = todas, o array de IDs específicos
  })
});
```

---

## Updated Blocks (v1.5.0+)

La respuesta de consolidación incluye `updated_blocks` - bloques **pre-modificados** con redundancias marcadas para eliminación.

```json
{
  "status": "success",
  "redundancies_found": 10,
  "total_savings_sec": 120,
  "updated_blocks": {
    "wf_abc123": {
      "blocks": [...],
      "changes_applied": [{
        "block_index": 5,
        "change_type": "marked_for_removal",
        "reason": "Redundant with video 2",
        "original_action": "keep",
        "new_action": "remove",
        "similarity": 0.99
      }],
      "original_keep_count": 15,
      "new_keep_count": 12,
      "savings_sec": 45
    }
  }
}
```

**Ventajas:**
- Bloques ya tienen `action: "remove"` y `removal_reason` aplicados
- Mostrar todos los videos en una pantalla con cambios visuales
- Usuario puede aceptar todo con un click

---

## Integración UI

### Patrón de Polling

```javascript
function useConsolidationProgress(projectId) {
  const [status, setStatus] = useState(null);
  const [isComplete, setIsComplete] = useState(false);

  useEffect(() => {
    const poll = async () => {
      const res = await fetch(`/v1/autoedit/project/${projectId}/consolidation-status`, {
        headers: { 'X-API-Key': API_KEY }
      });
      const data = await res.json();
      setStatus(data.response);

      if (['consolidated', 'consolidation_complete', 'consolidation_failed']
          .includes(data.response.consolidation_state)) {
        setIsComplete(true);
      }
    };
    poll();
    const interval = setInterval(poll, 5000);
    return () => clearInterval(interval);
  }, [projectId]);

  return { status, isComplete };
}
```

### Elementos UI Recomendados

1. **Estado de consolidación** con spinner y estado actual
2. **Score de redundancia** (0-100) con interpretación
3. **Lista de redundancias** con comparación video A vs video B
4. **Lista de recomendaciones** con checkboxes para seleccionar
5. **Vista unificada** de updated_blocks (v1.5.0+) mostrando cambios propuestos

---

## Ver También

- [FRONTEND-GUIDE.md](./FRONTEND-GUIDE.md) - Guía principal
- [FRONTEND-PROJECTS.md](./FRONTEND-PROJECTS.md) - Multi-video projects
- [API-REFERENCE.md](./API-REFERENCE.md) - Documentación completa
