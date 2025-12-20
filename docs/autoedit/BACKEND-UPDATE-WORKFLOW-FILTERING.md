# Backend Update: Workflow Filtering for Project Start

**Fecha:** 2025-12-19
**Version:** 1.4.1
**Estado:** Implementado y listo para usar

---

## Resumen

Se implemento la solicitud del equipo frontend para filtrado de workflows en el endpoint `/start`. Ahora el backend:

1. **Solo procesa workflows "startable"** (status = `created`)
2. **Acepta `workflow_ids`** para especificar exactamente que videos procesar
3. **Acepta `include_failed`** para reintentar videos fallidos
4. **Retorna `skipped_by_status`** para mostrar por que algunos videos fueron omitidos

---

## Nuevos Parametros en POST /v1/autoedit/project/{id}/start

| Parametro | Tipo | Default | Descripcion |
|-----------|------|---------|-------------|
| `workflow_ids` | array | null | IDs especificos a procesar (deben pertenecer al proyecto) |
| `include_failed` | boolean | false | Incluir workflows con status "error" para reintentar |

**Los parametros existentes (`parallel_limit`, `webhook_url`) siguen funcionando igual.**

---

## Ejemplos de Uso

### 1. Comportamiento por defecto (sin cambios)

```javascript
// Solo procesa videos con status="created"
const response = await fetch(`/v1/autoedit/project/${projectId}/start`, {
  method: 'POST',
  headers: { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' },
  body: JSON.stringify({ parallel_limit: 3 })
});
```

### 2. Procesar workflows especificos

```javascript
// Util cuando el usuario agrega videos nuevos a un proyecto existente
const newVideoIds = ['wf_abc123', 'wf_def456'];
const response = await fetch(`/v1/autoedit/project/${projectId}/start`, {
  method: 'POST',
  headers: { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' },
  body: JSON.stringify({
    parallel_limit: 3,
    workflow_ids: newVideoIds
  })
});
```

### 3. Reintentar videos fallidos

```javascript
// Procesa videos con status="created" Y status="error"
const response = await fetch(`/v1/autoedit/project/${projectId}/start`, {
  method: 'POST',
  headers: { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' },
  body: JSON.stringify({
    parallel_limit: 3,
    include_failed: true
  })
});
```

---

## Nueva Estructura de Respuesta

```json
{
  "status": "success",
  "message": "Started processing 2 video(s)",
  "project_id": "proj_abc123",
  "tasks_enqueued": 2,
  "total_workflows": 5,
  "pending_workflows": 2,
  "skipped_count": 3,
  "skipped_by_status": {
    "pending_review_1": ["wf_1"],
    "pending_review_2": ["wf_2", "wf_3"]
  },
  "invalid_workflow_ids": null,
  "tasks": [
    {"workflow_id": "wf_4", "task_name": "...", "delay_seconds": 0},
    {"workflow_id": "wf_5", "task_name": "...", "delay_seconds": 0}
  ]
}
```

### Nuevos Campos en Respuesta

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `skipped_count` | integer | Numero de workflows omitidos |
| `skipped_by_status` | object | Desglose por status: `{"pending_review_1": ["wf_1", "wf_2"]}` |
| `invalid_workflow_ids` | array | IDs que no pertenecen al proyecto (si se uso `workflow_ids`) |

---

## Logica de Filtrado

### Estados "Startable"

| Estado | Se procesa por defecto | Se procesa con `include_failed=true` |
|--------|------------------------|--------------------------------------|
| `created` | Si | Si |
| `error` | No | Si |
| `pending_review_1` | No | No |
| `pending_review_2` | No | No |
| `transcribing` | No | No |
| `analyzing` | No | No |
| `completed` | No | No |

### Validacion de workflow_ids

Si se especifica `workflow_ids`:
- Se valida que cada ID pertenezca al proyecto
- IDs invalidos se retornan en `invalid_workflow_ids`
- Solo se procesan IDs validos que esten en estado "startable"

---

## Uso Recomendado para Frontend

```javascript
async function startProjectProcessing(projectId, options = {}) {
  const response = await fetch(`/v1/autoedit/project/${projectId}/start`, {
    method: 'POST',
    headers: { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      parallel_limit: options.parallelLimit || 3,
      workflow_ids: options.workflowIds || undefined,
      include_failed: options.includeFailed || false
    })
  });

  const data = await response.json();

  // Mostrar mensaje al usuario basado en respuesta
  if (data.skipped_count > 0) {
    console.log(`${data.tasks_enqueued} videos iniciados, ${data.skipped_count} omitidos`);
    console.log('Omitidos por status:', data.skipped_by_status);
  }

  if (data.tasks_enqueued === 0) {
    // No hay videos pendientes para procesar
    showMessage('Todos los videos ya estan en proceso o completados');
  }

  return data;
}
```

---

## Backward Compatibility

**100% compatible hacia atras:**
- Si no se envian los nuevos parametros, el comportamiento es identico al anterior
- La respuesta mantiene todos los campos existentes
- Solo se agregan nuevos campos opcionales

---

## Tests

22 tests estructurales implementados en `tests/test_workflow_filtering.py`:
- Schema validation
- Function signature validation
- Response structure validation
- Backward compatibility validation

---

## Documentacion Actualizada

- `docs/autoedit/API-REFERENCE.md` - Documentacion completa del endpoint
- `docs/autoedit/CHANGELOG.md` - Entrada v1.4.1

---

*Implementado: 2025-12-19*
