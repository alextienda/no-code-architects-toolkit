# Multi-Video Projects Guide

> **Guía para frontend:** Procesamiento batch de múltiples videos en un proyecto.

## Concepto

Los **proyectos** permiten agrupar múltiples videos para procesamiento batch:

1. Crear un proyecto con configuración compartida
2. Agregar múltiples videos al proyecto
3. Iniciar el procesamiento en paralelo
4. Monitorear el progreso agregado

## Estados del Proyecto

```
created → ready → processing → completed
                      ↓
               partial_complete (algunos fallaron)
                      ↓
                   failed (todos fallaron)
```

| Estado | Descripción |
|--------|-------------|
| `created` | Proyecto creado, sin videos |
| `ready` | Tiene videos, listo para procesar |
| `processing` | Procesamiento batch en curso |
| `completed` | Todos los videos completados |
| `partial_complete` | Algunos videos fallaron |
| `failed` | Todos los videos fallaron |

## Flujo de Uso

```
PASO 1: POST /v1/autoedit/project           → Crear proyecto
PASO 2: POST /v1/autoedit/project/{id}/videos → Agregar videos
PASO 3: POST /v1/autoedit/project/{id}/start  → Iniciar batch
PASO 4: GET /v1/autoedit/project/{id}/stats   → Monitorear progreso
```

---

## Endpoints

### POST /v1/autoedit/project - Crear Proyecto

```javascript
const response = await fetch('/v1/autoedit/project', {
  method: 'POST',
  headers: { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' },
  body: JSON.stringify({
    name: 'Mi Proyecto',
    description: 'Descripción opcional',
    options: { language: 'es', style: 'dynamic' },
    // v1.5.0: Contexto opcional para personalización
    project_context: {
      sponsor: 'Nombre Sponsor',
      specific_audience: 'Audiencia específica',
      tone_override: 'más técnico',  // enum: más técnico|casual|formal|energético
      keywords_to_keep: ['término1', 'término2']
    }
  })
});
const { project_id } = (await response.json()).response;
```

**Campos de project_context (v1.5.0):**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `campaign` | string | Nombre de campaña |
| `sponsor` | string | Sponsor a preservar |
| `specific_audience` | string | Audiencia específica |
| `tone_override` | enum | "más técnico", "más casual", "más formal", "más energético" |
| `focus` | string | Enfoque del análisis |
| `keywords_to_keep` | string[] | Palabras a NO eliminar |
| `keywords_to_avoid` | string[] | Palabras a eliminar |

### POST /v1/autoedit/project/{id}/videos - Agregar Videos

```javascript
// 1. Crear workflows para cada video
const workflowIds = [];
for (const videoUrl of videoUrls) {
  const wf = await fetch('/v1/autoedit/workflow', {
    method: 'POST',
    headers: { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({ video_url: videoUrl, options: { project_id } })
  });
  workflowIds.push((await wf.json()).response.workflow_id);
}

// 2. Asociar al proyecto
await fetch(`/v1/autoedit/project/${projectId}/videos`, {
  method: 'POST',
  headers: { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' },
  body: JSON.stringify({ workflow_ids: workflowIds })
});
```

### POST /v1/autoedit/project/{id}/start - Iniciar Batch

```javascript
const response = await fetch(`/v1/autoedit/project/${projectId}/start`, {
  method: 'POST',
  headers: { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' },
  body: JSON.stringify({
    parallel_limit: 3,           // 1-10, videos simultáneos
    webhook_url: null,           // Opcional
    workflow_ids: undefined,     // v1.4.1: IDs específicos a procesar
    include_failed: false        // v1.4.1: Reintentar fallidos
  })
});
```

**Respuesta (v1.4.1+):**

```json
{
  "status": "success",
  "tasks_enqueued": 2,
  "total_workflows": 5,
  "skipped_count": 3,
  "skipped_by_status": {
    "pending_review_1": ["wf_1"],
    "pending_review_2": ["wf_2", "wf_3"]
  }
}
```

### GET /v1/autoedit/project/{id}/stats - Monitorear Progreso

```javascript
const response = await fetch(`/v1/autoedit/project/${projectId}/stats`, {
  headers: { 'X-API-Key': API_KEY }
});
const { stats, state } = (await response.json()).response;
// stats: { total_videos, completed, pending, processing, failed }
```

**Polling recomendado:** cada 5-10 segundos hasta que `state` sea `completed`, `partial_complete`, o `failed`.

### GET /v1/autoedit/project/{id}/videos - Listar Videos

```javascript
const response = await fetch(`/v1/autoedit/project/${projectId}/videos`, {
  headers: { 'X-API-Key': API_KEY }
});
// Retorna array de workflows con estado actual
```

---

## Integración UI

### Patrón de Polling

```javascript
function useProjectProgress(projectId, pollInterval = 5000) {
  const [stats, setStats] = useState(null);
  const [isComplete, setIsComplete] = useState(false);

  useEffect(() => {
    const poll = async () => {
      const res = await fetch(`/v1/autoedit/project/${projectId}/stats`, {
        headers: { 'X-API-Key': API_KEY }
      });
      const data = await res.json();
      setStats(data.response.stats);

      if (['completed', 'partial_complete', 'failed'].includes(data.response.state)) {
        setIsComplete(true);
      }
    };

    poll();
    const interval = setInterval(poll, pollInterval);
    return () => clearInterval(interval);
  }, [projectId]);

  return { stats, isComplete };
}
```

### Elementos UI Recomendados

1. **Progress bar** con `completed / total_videos`
2. **Stats grid** mostrando: completados, en proceso, pendientes, fallidos
3. **Tabla de videos** con estado y acciones (Revisar XML, Revisar Preview)
4. **Indicador de skipped** cuando `start` omite videos ya procesados

---

## Ver También

- [FRONTEND-GUIDE.md](./FRONTEND-GUIDE.md) - Guía principal
- [FRONTEND-CONSOLIDATION.md](./FRONTEND-CONSOLIDATION.md) - Consolidación multi-video
- [API-REFERENCE.md](./API-REFERENCE.md) - Documentación completa de endpoints
