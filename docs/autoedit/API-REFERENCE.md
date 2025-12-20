# AutoEdit API Reference

Documentación completa de la API REST para el pipeline de edición automática de video con AI.

**Versión**: 1.4.0

---

## Quick Start - Flujo Simplificado (Nuevo)

> **Para el equipo Frontend**: El pipeline ahora es **automático**. Solo necesitan 3 interacciones:

```javascript
// 1. Crear workflow (auto-inicia transcripción + análisis)
const createRes = await fetch('/v1/autoedit/workflow', {
  method: 'POST',
  headers: { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' },
  body: JSON.stringify({
    video_url: 'https://...',
    options: { language: 'es', style: 'dynamic' }
  })
});
const { response: { workflow_id } } = await createRes.json();

// 2. Polling hasta status === 'pending_review_1' (automático ~1-3 min)
let status = 'created';
while (!['pending_review_1', 'error'].includes(status)) {
  await new Promise(r => setTimeout(r, 5000)); // esperar 5 segundos
  const res = await fetch(`/v1/autoedit/workflow/${workflow_id}`, {
    headers: { 'X-API-Key': API_KEY }
  });
  status = (await res.json()).status;
}

// 3. HITL 1: Revisar y aprobar XML (auto-genera preview)
const xmlRes = await fetch(`/v1/autoedit/workflow/${workflow_id}/analysis`, {
  headers: { 'X-API-Key': API_KEY }
});
const { combined_xml } = await xmlRes.json();
// ... UI muestra XML, usuario modifica ...
await fetch(`/v1/autoedit/workflow/${workflow_id}/analysis`, {
  method: 'PUT',
  headers: { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' },
  body: JSON.stringify({ updated_xml: modifiedXml })  // auto_continue=true por defecto
});

// 4. Polling hasta status === 'pending_review_2' (automático ~10-30 seg)
while (!['pending_review_2', 'error'].includes(status)) {
  await new Promise(r => setTimeout(r, 3000));
  const res = await fetch(`/v1/autoedit/workflow/${workflow_id}`, {
    headers: { 'X-API-Key': API_KEY }
  });
  status = (await res.json()).status;
}

// 5. HITL 2: Revisar preview y renderizar (async via Cloud Tasks)
const previewRes = await fetch(`/v1/autoedit/workflow/${workflow_id}/preview`, {
  headers: { 'X-API-Key': API_KEY }
});
const { preview_url, blocks } = await previewRes.json();
// ... UI muestra preview video y timeline ...
await fetch(`/v1/autoedit/workflow/${workflow_id}/render`, {
  method: 'POST',
  headers: { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' },
  body: JSON.stringify({ quality: 'high' })  // async_render=true por defecto
});

// 6. Polling hasta status === 'completed' (automático ~1-3 min)
while (!['completed', 'error'].includes(status)) {
  await new Promise(r => setTimeout(r, 5000));
  const res = await fetch(`/v1/autoedit/workflow/${workflow_id}`, {
    headers: { 'X-API-Key': API_KEY }
  });
  status = (await res.json()).status;
}

// 7. Obtener video final
const resultRes = await fetch(`/v1/autoedit/workflow/${workflow_id}/result`, {
  headers: { 'X-API-Key': API_KEY }
});
const { output_url } = await resultRes.json();
```

**Diagrama de Estados (Pipeline Automático via Cloud Tasks):**
```
POST /workflow (auto_start=true)
         ↓
      created
         ↓ [Cloud Tasks: transcribe]
    transcribing ───→ transcribed
                           ↓ [Cloud Tasks: analyze]
                      analyzing ───→ pending_review_1  ← HITL 1
                                           ↓
                                    PUT /analysis (auto_continue=true)
                                           ↓ [Cloud Tasks: process]
                                      processing
                                           ↓ [Cloud Tasks: preview]
                                  generating_preview
                                           ↓
                                    pending_review_2  ← HITL 2
                                           ↓
                                    POST /render (async_render=true)
                                           ↓ [Cloud Tasks: render]
                                       rendering
                                           ↓
                                       completed
```

---

## Arquitectura: Cloud Tasks Pipeline

El pipeline AutoEdit usa **Google Cloud Tasks** para procesamiento asíncrono automático con orquestación de tareas y almacenamiento persistente en Google Cloud Storage (GCS).

### Flujo Automático

| Paso | Endpoint | Cloud Tasks | Para en |
|------|----------|-------------|---------|
| 1 | POST /workflow | → enqueue transcribe | - |
| 2 | - | transcribe → analyze | - |
| 3 | - | analyze | **HITL 1** |
| 4 | PUT /analysis | → enqueue process | - |
| 5 | - | process → preview | - |
| 6 | - | preview | **HITL 2** |
| 7 | POST /render | → enqueue render | - |
| 8 | - | render | **completed** |

### Cómo Funciona Cloud Tasks

**1. Orquestación Asíncrona:**
- Cada endpoint puede encolar la tarea siguiente automáticamente
- Cloud Tasks garantiza entrega de tareas con retry automático
- Cada tarea se ejecuta de forma independiente y actualiza el workflow

**2. Flujo de Orquestación:**
```
POST /workflow (auto_start=true)
    ↓
    Crea workflow en GCS
    ↓
    Encola tarea: /workflow/{id}/transcribe
    ↓ [Cloud Tasks ejecuta en background]
    Transcribe → actualiza workflow
    ↓
    Encola tarea: /workflow/{id}/analyze
    ↓ [Cloud Tasks ejecuta en background]
    Analyze → actualiza workflow → status: pending_review_1

    ... usuario revisa XML ...

PUT /analysis (auto_continue=true)
    ↓
    Actualiza workflow con XML aprobado
    ↓
    Encola tarea: /workflow/{id}/process
    ↓ [Cloud Tasks ejecuta en background]
    Process → actualiza workflow
    ↓
    Encola tarea: /workflow/{id}/preview
    ↓ [Cloud Tasks ejecuta en background]
    Preview → actualiza workflow → status: pending_review_2

    ... usuario revisa preview ...

POST /render (async_render=true)
    ↓
    Encola tarea: /workflow/{id}/render
    ↓ [Cloud Tasks ejecuta en background]
    Render → actualiza workflow → status: completed
```

**3. Cada Tarea Encola la Siguiente:**
- `transcribe` automáticamente encola `analyze` al completar
- `analyze` NO encola (para en HITL 1)
- `process` automáticamente encola `preview` al completar
- `preview` NO encola (para en HITL 2)
- `render` es la tarea final (no encola nada)

### Almacenamiento: GCS en lugar de /tmp

**Workflows persistidos en GCS:**
- Bucket: `gs://{GCS_BUCKET}/workflows/{workflow_id}.json`
- **No se usa /tmp**: Los workflows se guardan en GCS para persistencia entre ejecuciones
- TTL de 24 horas: Workflows se auto-eliminan después de 24h

**Ventajas:**
- Workflows sobreviven reinicios de Cloud Run
- Múltiples workers pueden acceder al mismo workflow
- Archivos temporales en /tmp, datos de workflow en GCS

### Optimistic Locking

Para evitar race conditions cuando múltiples tareas intentan actualizar el mismo workflow:

**Conditional Updates:**
```python
# Cada update verifica la generación del objeto en GCS
# Si otro proceso ya actualizó, la escritura falla y se reintenta

update_workflow(workflow_id, data)
    ↓
    Read current workflow from GCS (get generation)
    ↓
    Modify data locally
    ↓
    Write to GCS IF generation matches
    ↓
    Success: workflow updated
    Failure: retry (eventual consistency)
```

**Retry Logic:**
- Máximo 3 reintentos para eventual consistency
- Espera exponencial: 100ms, 200ms, 400ms
- Previene pérdida de actualizaciones concurrentes

### file_url vs output_url Fix

**Problema Detectado:**
El render FFmpeg puede retornar dos formatos diferentes:

**Formato 1 (con file_url):**
```json
{
  "file_url": "https://storage.googleapis.com/...",
  "duration_ms": 13200
}
```

**Formato 2 (con output_url):**
```json
{
  "output_url": "https://storage.googleapis.com/...",
  "duration_ms": 13200
}
```

**Solución Implementada:**
```python
# Detectar ambos formatos
file_url = render_result.get('file_url') or render_result.get('output_url')
if not file_url:
    raise ValueError("Render failed: No file_url or output_url returned")
```

### Beneficios

- Frontend solo hace **3 POST** (crear, aprobar XML, aprobar render)
- Backend ejecuta pasos intermedios automáticamente
- Fallback a ejecución síncrona si Cloud Tasks falla
- **Workflows persistentes en GCS** (no /tmp volátil)
- **Optimistic locking** previene race conditions
- **Retry automático** para robustez

### Parámetros de Control

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `auto_start` | `true` | POST /workflow auto-inicia pipeline |
| `auto_continue` | `true` | PUT /analysis auto-continúa a process→preview |
| `async_render` | `true` | POST /render usa Cloud Tasks |

Para **modo manual** (sin automático), pasar estos como `false`.

### Fallback Síncrono

**Si Cloud Tasks no está configurado:**
- Variables de entorno: `GCP_PROJECT_ID`, `GCP_QUEUE_LOCATION`, `GCP_QUEUE_NAME`
- Si faltan, el sistema ejecuta las tareas **síncronamente**
- Mismo flujo, pero bloquea la petición HTTP hasta completar
- Útil para desarrollo local sin infraestructura GCP

**Ejemplo:**
```python
# Con Cloud Tasks (producción)
POST /workflow → 201 Created (inmediato)
  → Cloud Tasks ejecuta transcribe en background
  → Frontend hace polling hasta pending_review_1

# Sin Cloud Tasks (local/fallback)
POST /workflow → 201 Created (después de transcribe+analyze completos)
  → Ejecución síncrona
  → Frontend recibe respuesta cuando llega a pending_review_1
```

### Cloud Tasks Limits y Quotas

**Google Cloud Tasks Quotas (default):**
- **Dispatch rate**: 500 tasks/second por cola
- **Max concurrent dispatches**: 1000 tareas concurrentes
- **Max task size**: 1 MB payload
- **Max task retention**: 31 días
- **Max queues per project**: 1000

**AutoEdit Pipeline Configuración:**
- Queue: `autoedit-pipeline`
- Location: `us-central1`
- Max concurrent: 100 (configurable)
- Retry config: Max 3 attempts, exponential backoff

**Monitoreo:**
```bash
# Ver tareas en cola
gcloud tasks queues describe autoedit-pipeline --location=us-central1

# Ver tareas ejecutándose
gcloud tasks list --queue=autoedit-pipeline --location=us-central1
```

### Webhook Pattern con Cloud Tasks

**Para notificaciones de completado:**

El sistema soporta webhooks opcionales que se ejecutan **después** de cada paso:

**Request con webhook_url:**
```json
{
  "video_url": "https://...",
  "webhook_url": "https://mi-backend.com/notify",
  "auto_start": true
}
```

**Comportamiento:**
1. POST /workflow → encola transcribe
2. Transcribe completa → POST a webhook_url con status
3. Analyze completa → POST a webhook_url con status
4. ... etc para cada paso

**Payload del webhook:**
```json
{
  "workflow_id": "550e8400-...",
  "status": "pending_review_1",
  "event": "analyze_complete",
  "timestamp": "2025-01-15T10:35:00Z",
  "data": {
    "status_message": "HITL 1: Esperando revisión de XML"
  }
}
```

**Ventajas:**
- Frontend no necesita hacer polling
- Notificaciones push en tiempo real
- Reduce carga del servidor (menos requests)

**Retry en webhooks:**
- Máximo 3 reintentos si falla
- Exponential backoff: 5s, 15s, 45s
- Timeout: 30 segundos por intento

---

## Configuración

### Base URL

**Producción (GCP Cloud Run):**
```
https://nca-toolkit-djwypu7xmq-uc.a.run.app
```

**Desarrollo local:**
```
http://localhost:8080
```

### Variables de Entorno

**Requeridas para Cloud Tasks (Producción):**
```bash
# Cloud Tasks
GCP_PROJECT_ID=autoedit-at
GCP_QUEUE_LOCATION=us-central1
GCP_QUEUE_NAME=autoedit-pipeline

# GCS Workflow Storage
GCS_BUCKET=your-bucket-name
GCP_SA_CREDENTIALS={"type": "service_account", ...}

# API Authentication
API_KEY=your_api_key
```

**Opcionales para desarrollo local (sin Cloud Tasks):**
- Si faltan `GCP_PROJECT_ID`, `GCP_QUEUE_LOCATION`, `GCP_QUEUE_NAME`:
  - El sistema ejecuta tareas **síncronamente** (fallback)
  - Workflows se almacenan en `/tmp` en lugar de GCS
  - Útil para desarrollo y testing local

### Autenticación

Todos los endpoints requieren el header `X-API-Key`:

```http
X-API-Key: ${NCA_API_KEY}
```

Ejemplo de petición completa:

```bash
curl -X POST "${NCA_TOOLKIT_URL}/v1/autoedit/workflow" \
  -H "X-API-Key: ${NCA_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"video_url": "https://storage.example.com/video.mp4"}'
```

> Ver archivo `.env.autoedit` para los valores de las variables de entorno.

---

## Formato de Respuesta

### Endpoints con Wrapper (POST, PUT, PATCH con `@queue_task_wrapper`)

Los endpoints que modifican datos retornan una respuesta envuelta (wrapped):

```json
{
  "code": 201,
  "id": null,
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "response": {
    "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "created",
    "status_message": "Workflow creado",
    "message": "Workflow created successfully"
  },
  "message": "success",
  "run_time": 0.045,
  "queue_time": 0,
  "total_time": 0.045,
  "endpoint": "/v1/autoedit/workflow",
  "pid": 12345,
  "queue_id": 140234567890,
  "queue_length": 0,
  "build_number": "219"
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `code` | integer | HTTP status code |
| `id` | string \| null | ID proporcionado en el request |
| `job_id` | string | UUID único del job |
| `response` | object | **Datos del endpoint (aquí está el workflow_id)** |
| `message` | string | "success" o detalles del error |
| `run_time` | float | Tiempo de ejecución en segundos |
| `queue_time` | float | Tiempo en cola |
| `total_time` | float | Tiempo total |
| `endpoint` | string | Path del endpoint |

> **⚠️ IMPORTANTE para Frontend**: El `workflow_id` está en `response.workflow_id`, NO en el nivel raíz.

### Endpoints sin Wrapper (GET, DELETE)

Los endpoints de lectura retornan directamente el objeto sin wrapper:

```json
{
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending_review_1",
  "created_at": "2025-01-15T10:30:00Z",
  ...
}
```

### Extracción de workflow_id (JavaScript)

```javascript
// ✅ CORRECTO - POST /v1/autoedit/workflow
const createResponse = await fetch('/v1/autoedit/workflow', {...});
const createData = await createResponse.json();
const workflowId = createData.response.workflow_id;  // ← En response.workflow_id

// ✅ CORRECTO - GET /v1/autoedit/workflow/{id}
const statusResponse = await fetch(`/v1/autoedit/workflow/${workflowId}`, {...});
const statusData = await statusResponse.json();
const status = statusData.status;  // ← Directo, sin wrapper

// ❌ INCORRECTO
const workflowId = createData.workflow_id;  // undefined!
```

### Tabla Resumen de Formatos

| Método | Endpoint | Wrapper | Ubicación de workflow_id |
|--------|----------|---------|--------------------------|
| POST | `/workflow` | Sí | `response.workflow_id` |
| GET | `/workflow/{id}` | No | `workflow_id` |
| DELETE | `/workflow/{id}` | No | `workflow_id` |
| GET | `/workflows` | No | `workflows[].workflow_id` |
| POST | `/workflow/{id}/transcribe` | Sí | `response.workflow_id` |
| POST | `/workflow/{id}/analyze` | Sí | `response.workflow_id` |
| GET | `/workflow/{id}/analysis` | No | `workflow_id` |
| PUT | `/workflow/{id}/analysis` | Sí | `response.workflow_id` |
| POST | `/workflow/{id}/process` | Sí | `response.workflow_id` |
| POST | `/workflow/{id}/preview` | Sí | `response.workflow_id` |
| GET | `/workflow/{id}/preview` | No | `workflow_id` |
| PATCH | `/workflow/{id}/blocks` | Sí | `response.workflow_id` |
| POST | `/workflow/{id}/render` | Sí | `response.workflow_id` |
| GET | `/workflow/{id}/render` | No | `workflow_id` |
| GET | `/workflow/{id}/result` | No | `workflow_id` |
| POST | `/workflow/{id}/rerender` | Sí | `response.workflow_id` |
| GET | `/workflow/{id}/estimate` | No | `workflow_id` |

---

## Endpoints Overview

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/v1/autoedit/workflow` | Crear nuevo workflow |
| GET | `/v1/autoedit/workflow/{id}` | Obtener estado del workflow |
| DELETE | `/v1/autoedit/workflow/{id}` | Eliminar workflow |
| GET | `/v1/autoedit/workflows` | Listar todos los workflows |
| POST | `/v1/autoedit/workflow/{id}/transcribe` | **Transcribir video con ElevenLabs** |
| POST | `/v1/autoedit/workflow/{id}/analyze` | **Analizar transcripción con Gemini** |
| GET | `/v1/autoedit/workflow/{id}/analysis` | Obtener XML para HITL 1 |
| PUT | `/v1/autoedit/workflow/{id}/analysis` | Enviar XML revisado |
| POST | `/v1/autoedit/workflow/{id}/process` | Procesar XML a blocks |
| POST | `/v1/autoedit/workflow/{id}/preview` | Generar preview low-res |
| GET | `/v1/autoedit/workflow/{id}/preview` | Obtener preview y blocks |
| PATCH | `/v1/autoedit/workflow/{id}/blocks` | Modificar blocks |
| POST | `/v1/autoedit/workflow/{id}/render` | Iniciar render final |
| GET | `/v1/autoedit/workflow/{id}/render` | Estado del render |
| GET | `/v1/autoedit/workflow/{id}/result` | Obtener video final |
| POST | `/v1/autoedit/workflow/{id}/rerender` | Re-renderizar con nueva calidad |
| GET | `/v1/autoedit/workflow/{id}/estimate` | Estimar tiempo de render |

---

## Workflow Lifecycle

### POST /v1/autoedit/workflow

Crear un nuevo workflow de edición automática. **Por defecto, inicia automáticamente el pipeline de transcripción y análisis via Cloud Tasks.**

**Request Body:**

```json
{
  "video_url": "https://storage.example.com/video.mp4",
  "options": {
    "language": "es",
    "style": "dynamic",
    "skip_hitl_1": false,
    "skip_hitl_2": false
  },
  "auto_start": true,
  "id": "mi-id-personalizado"
}
```

| Campo | Tipo | Requerido | Default | Descripción |
|-------|------|-----------|---------|-------------|
| `video_url` | string (uri) | Sí | - | URL del video a procesar |
| `auto_start` | boolean | No | **true** | **Iniciar pipeline automáticamente** (transcribe → analyze) |
| `options.language` | string | No | "es" | Código de idioma para transcripción |
| `options.style` | string | No | "dynamic" | Estilo de edición: "dynamic", "conservative", "aggressive" |
| `options.skip_hitl_1` | boolean | No | false | Saltar revisión de XML |
| `options.skip_hitl_2` | boolean | No | false | Saltar revisión de preview |
| `id` | string | No | - | ID personalizado para el request |

**Comportamiento con `auto_start=true` (default):**
1. Crea el workflow
2. Encola tarea de transcripción en Cloud Tasks
3. Cuando transcripción termina, encola análisis automáticamente
4. Pipeline para en `pending_review_1` esperando HITL 1

**Comportamiento con `auto_start=false`:**
- Solo crea el workflow
- Debe llamar manualmente a `/transcribe` y `/analyze`

**Response (201 Created):**

```json
{
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "created",
  "status_message": "Workflow creado",
  "message": "Workflow created. Pipeline started automatically.",
  "pipeline_started": true,
  "task_enqueued": {
    "success": true,
    "task_type": "transcribe",
    "task_name": "projects/autoedit-at/locations/us-central1/queues/autoedit-pipeline/tasks/..."
  }
}
```

**cURL Example:**

```bash
curl -X POST https://nca-toolkit-djwypu7xmq-uc.a.run.app/v1/autoedit/workflow \
  -H "X-API-Key: tu_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "video_url": "https://storage.example.com/mi-video.mp4",
    "options": {
      "language": "es",
      "style": "dynamic"
    }
  }'
```

> **Nota:** Después de crear, hacer polling en `GET /workflow/{id}` hasta `status === "pending_review_1"` (~1-3 minutos)

---

### GET /v1/autoedit/workflow/{workflow_id}

Obtener el estado actual y datos de un workflow.

**Path Parameters:**

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `workflow_id` | string | ID del workflow |

**Response (200 OK):**

```json
{
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending_review_2",
  "status_message": "HITL 2: Preview listo, esperando aprobación",
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T10:35:00Z",
  "video_url": "https://storage.example.com/video.mp4",
  "options": {
    "language": "es",
    "style": "dynamic"
  },
  "has_transcript": true,
  "has_xml": true,
  "has_blocks": true,
  "block_count": 15,
  "preview_url": "https://storage.example.com/preview_550e8400.mp4",
  "preview_duration_ms": 27340,
  "stats": {
    "original_duration_ms": 45000,
    "result_duration_ms": 27340,
    "removal_percentage": 39.2
  }
}
```

**cURL Example:**

```bash
curl -X GET https://api.example.com/v1/autoedit/workflow/550e8400-e29b-41d4-a716-446655440000 \
  -H "X-API-Key: tu_api_key"
```

---

### DELETE /v1/autoedit/workflow/{workflow_id}

Eliminar un workflow y sus datos asociados.

**Response (200 OK):**

```json
{
  "message": "Workflow deleted successfully",
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

### GET /v1/autoedit/workflows

Listar todos los workflows, opcionalmente filtrados por estado.

**Query Parameters:**

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `status` | string | Filtrar por estado (opcional) |

**Response (200 OK):**

```json
{
  "workflows": [
    {
      "workflow_id": "550e8400-...",
      "status": "completed",
      "video_url": "https://...",
      "created_at": "2025-01-15T10:30:00Z"
    }
  ],
  "total": 5,
  "filter": {"status": "completed"}
}
```

---

## Transcripción y Análisis

> **IMPORTANTE**: Después de crear un workflow, DEBE llamar a `/transcribe` y luego a `/analyze` para que el workflow avance al estado `pending_review_1`.

### POST /v1/autoedit/workflow/{workflow_id}/transcribe

Transcribir el video usando ElevenLabs. Este paso es **obligatorio** después de crear el workflow.

**Path Parameters:**

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `workflow_id` | string | ID del workflow |

**Request Body:**

```json
{
  "language": "es"
}
```

| Campo | Tipo | Requerido | Default | Descripción |
|-------|------|-----------|---------|-------------|
| `language` | string | No | "es" | Código de idioma para la transcripción |

**Response (200 OK):**

```json
{
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "transcribed",
  "status_message": "Transcripción completa",
  "transcript_word_count": 450,
  "transcript_duration_ms": 45000,
  "message": "Transcription complete. Ready for analysis."
}
```

**Estados del Workflow:**
- Antes: `created`
- Durante: `transcribing`
- Después: `transcribed`

**cURL Example:**

```bash
curl -X POST "https://nca-toolkit-djwypu7xmq-uc.a.run.app/v1/autoedit/workflow/550e8400-e29b-41d4-a716-446655440000/transcribe" \
  -H "X-API-Key: tu_api_key" \
  -H "Content-Type: application/json" \
  -d '{"language": "es"}'
```

**Notas:**
- Este proceso puede tardar 30-120 segundos dependiendo de la duración del video
- Usa ElevenLabs para transcripción con timestamps por palabra
- El resultado se almacena internamente para el siguiente paso

---

### POST /v1/autoedit/workflow/{workflow_id}/analyze

Analizar la transcripción con Gemini AI para identificar contenido a mantener/eliminar. Este paso es **obligatorio** después de transcribir.

**Path Parameters:**

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `workflow_id` | string | ID del workflow |

**Request Body:**

```json
{
  "style": "dynamic",
  "custom_prompt": null
}
```

| Campo | Tipo | Requerido | Default | Descripción |
|-------|------|-----------|---------|-------------|
| `style` | string | No | "dynamic" | Estilo de edición: "dynamic", "conservative", "aggressive" |
| `custom_prompt` | string | No | null | Prompt personalizado para Gemini (opcional) |

**Estilos de Edición:**

| Estilo | Descripción |
|--------|-------------|
| `dynamic` | Balance entre mantener contenido y eliminar relleno |
| `conservative` | Mantiene más contenido, menos agresivo |
| `aggressive` | Elimina más agresivamente muletillas y pausas |

**Response (200 OK):**

```json
{
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending_review_1",
  "status_message": "HITL 1: Esperando revisión de XML",
  "gemini_blocks_count": 12,
  "analysis_summary": {
    "total_words": 450,
    "words_to_keep": 380,
    "words_to_remove": 70,
    "removal_percentage": 15.5
  },
  "message": "Analysis complete. Ready for HITL 1 review."
}
```

**Estados del Workflow:**
- Antes: `transcribed`
- Durante: `analyzing`
- Después: `pending_review_1`

**cURL Example:**

```bash
curl -X POST "https://nca-toolkit-djwypu7xmq-uc.a.run.app/v1/autoedit/workflow/550e8400-e29b-41d4-a716-446655440000/analyze" \
  -H "X-API-Key: tu_api_key" \
  -H "Content-Type: application/json" \
  -d '{"style": "dynamic"}'
```

**Notas:**
- Este proceso puede tardar 20-60 segundos
- Usa Gemini (Vertex AI) para análisis semántico del contenido
- Genera XML con tags `<mantener>` y `<eliminar>`
- Después de este paso, el workflow está listo para HITL 1 (revisión de XML)

---

## HITL 1: XML Review

### GET /v1/autoedit/workflow/{workflow_id}/analysis

Obtener el XML de análisis de Gemini para revisión del usuario.

**Response (200 OK):**

```json
{
  "workflow_id": "550e8400-...",
  "status": "pending_review_1",
  "combined_xml": "<resultado><mantener>Hola bienvenidos</mantener><eliminar>eh um</eliminar><mantener>al video de hoy</mantener></resultado>",
  "transcript_text": "Hola bienvenidos eh um al video de hoy...",
  "message": "Review the XML and submit modifications via PUT"
}
```

**Notas:**
- El XML contiene tags `<mantener>` y `<eliminar>`
- El frontend debe renderizar el XML y permitir toggle de palabras
- NO incluye timestamps (solo texto)

---

### PUT /v1/autoedit/workflow/{workflow_id}/analysis

Enviar el XML revisado/modificado por el usuario. **Por defecto, continúa automáticamente a process y preview via Cloud Tasks.**

**Request Body:**

```json
{
  "updated_xml": "<resultado><mantener>Hola bienvenidos eh um al video de hoy</mantener></resultado>",
  "auto_continue": true,
  "config": {
    "padding_before_ms": 90,
    "padding_after_ms": 130,
    "silence_threshold_ms": 50,
    "merge_threshold_ms": 100
  }
}
```

| Campo | Tipo | Requerido | Default | Descripción |
|-------|------|-----------|---------|-------------|
| `updated_xml` | string | Sí | - | XML con cambios del usuario |
| `auto_continue` | boolean | No | **true** | **Continuar pipeline automáticamente** (process → preview) |
| `config.padding_before_ms` | number | No | 90 | Padding antes de cada corte (0-500ms) |
| `config.padding_after_ms` | number | No | 130 | Padding después de cada corte (0-500ms) |
| `config.silence_threshold_ms` | number | No | 50 | Umbral para detectar silencios (0-500ms) |
| `config.merge_threshold_ms` | number | No | 100 | Umbral para fusionar blocks cercanos (0-1000ms) |

**Comportamiento con `auto_continue=true` (default):**
1. Guarda el XML aprobado
2. Encola tarea de process en Cloud Tasks
3. Cuando process termina, encola preview automáticamente
4. Pipeline para en `pending_review_2` esperando HITL 2

**Comportamiento con `auto_continue=false`:**
- Solo guarda el XML
- Debe llamar manualmente a `/process` y `/preview`

**Response (200 OK):**

```json
{
  "workflow_id": "550e8400-...",
  "status": "xml_approved",
  "message": "XML approved. Pipeline continuing automatically.",
  "pipeline_continuing": true,
  "task_enqueued": {
    "success": true,
    "task_type": "process",
    "task_name": "projects/autoedit-at/locations/us-central1/queues/autoedit-pipeline/tasks/..."
  }
}
```

**Validación:**
- El XML debe contener `<resultado>` como elemento raíz
- Solo se permiten tags `<mantener>` y `<eliminar>`

> **Nota:** Después de aprobar, hacer polling en `GET /workflow/{id}` hasta `status === "pending_review_2"` (~10-30 segundos)

---

## HITL 2: Preview & Blocks

### POST /v1/autoedit/workflow/{workflow_id}/process

Procesar el XML aprobado para generar blocks con timestamps.

**Request Body:**

```json
{
  "config": {
    "padding_before_ms": 90,
    "padding_after_ms": 130,
    "silence_threshold_ms": 50,
    "merge_threshold_ms": 100
  }
}
```

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `padding_before_ms` | number | 90 | Padding antes de cada corte (0-500ms) |
| `padding_after_ms` | number | 130 | Padding después de cada corte (0-500ms) |
| `silence_threshold_ms` | number | 50 | Umbral para detectar silencios (0-500ms) |
| `merge_threshold_ms` | number | 100 | Umbral para fusionar blocks cercanos (0-1000ms) |

**Response (200 OK):**

```json
{
  "workflow_id": "550e8400-...",
  "status": "generating_preview",
  "blocks": [
    {
      "id": "b1",
      "inMs": 300,
      "outMs": 5720,
      "text": "Hola bienvenidos al video de hoy"
    },
    {
      "id": "b2",
      "inMs": 7220,
      "outMs": 15000,
      "text": "Vamos a ver este tema interesante"
    }
  ],
  "gaps": [
    {
      "id": "g0",
      "inMs": 0,
      "outMs": 300,
      "reason": "silence",
      "text": ""
    },
    {
      "id": "g1",
      "inMs": 5720,
      "outMs": 7220,
      "reason": "filler_words",
      "text": "eh um bueno"
    }
  ],
  "stats": {
    "original_duration_ms": 45000,
    "result_duration_ms": 13200,
    "removal_percentage": 70.6
  },
  "message": "Blocks ready. Generate preview to continue."
}
```

---

### POST /v1/autoedit/workflow/{workflow_id}/preview

Generar video preview de baja resolución.

**Request Body:**

```json
{
  "quality": "480p",
  "fade_duration": 0.025
}
```

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `quality` | string | "480p" | Calidad del preview: "480p" o "720p" |
| `fade_duration` | number | 0.025 | Duración del crossfade en segundos (0.01-0.5) |

**Response (200 OK):**

```json
{
  "workflow_id": "550e8400-...",
  "status": "pending_review_2",
  "preview_url": "https://storage.example.com/preview_550e8400.mp4",
  "preview_duration_ms": 13200,
  "blocks": [
    {
      "id": "b1",
      "inMs": 300,
      "outMs": 5720,
      "text": "Hola bienvenidos al video de hoy",
      "preview_inMs": 0
    },
    {
      "id": "b2",
      "inMs": 7220,
      "outMs": 15000,
      "text": "Vamos a ver este tema interesante",
      "preview_inMs": 5420
    }
  ],
  "gaps": [...],
  "video_duration_ms": 45000,
  "stats": {
    "original_duration_ms": 45000,
    "result_duration_ms": 13200,
    "removal_percentage": 70.6,
    "render_time_sec": 8.5
  },
  "message": "Preview ready. Review and approve or modify blocks."
}
```

**Notas:**
- `preview_inMs` indica la posición del block en el video preview (para sincronizar timeline)
- El preview incluye crossfades aplicados
- Tiempo de generación típico: 5-15 segundos

---

### GET /v1/autoedit/workflow/{workflow_id}/preview

Obtener el preview y datos de blocks/gaps actuales.

**Response (200 OK):**

```json
{
  "workflow_id": "550e8400-...",
  "status": "pending_review_2",
  "preview_url": "https://storage.example.com/preview_550e8400.mp4",
  "preview_duration_ms": 13200,
  "blocks": [...],
  "gaps": [...],
  "video_duration_ms": 45000,
  "stats": {...}
}
```

---

### PATCH /v1/autoedit/workflow/{workflow_id}/blocks

Modificar blocks (ajustar timestamps, split, merge, delete, restore).

**Request Body:**

```json
{
  "modifications": [
    {
      "action": "adjust",
      "block_id": "b1",
      "new_inMs": 250,
      "new_outMs": 5800
    },
    {
      "action": "split",
      "block_id": "b2",
      "split_at_ms": 10000
    },
    {
      "action": "merge",
      "block_ids": ["b3", "b4"]
    },
    {
      "action": "delete",
      "block_id": "b5"
    },
    {
      "action": "restore_gap",
      "gap_id": "g2"
    }
  ]
}
```

**Acciones Disponibles:**

| Acción | Campos Requeridos | Descripción |
|--------|-------------------|-------------|
| `adjust` | `block_id`, `new_inMs`, `new_outMs` | Ajustar timestamps de un block |
| `split` | `block_id`, `split_at_ms` | Dividir un block en dos |
| `merge` | `block_ids` (array) | Fusionar blocks adyacentes |
| `delete` | `block_id` | Eliminar un block |
| `restore_gap` | `gap_id` o `gap_index` | Recuperar un segmento eliminado |

**Response (200 OK):**

```json
{
  "workflow_id": "550e8400-...",
  "blocks": [...],
  "gaps": [...],
  "stats": {...},
  "needs_preview_regeneration": true,
  "errors": null,
  "message": "Blocks modified. Regenerate preview to see changes."
}
```

**Notas:**
- Después de modificar, llamar a POST `/preview` para regenerar
- `errors` contiene lista de errores si alguna modificación falló

---

## Final Render

### POST /v1/autoedit/workflow/{workflow_id}/render

Aprobar blocks e iniciar render final de alta calidad. **Por defecto, el render se ejecuta asíncronamente via Cloud Tasks.**

**Request Body:**

```json
{
  "quality": "high",
  "crossfade_duration": 0.025,
  "async_render": true
}
```

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `quality` | string | "high" | Calidad: "standard", "high", "4k" |
| `crossfade_duration` | number | 0.025 | Duración del crossfade (0.01-0.5s) |
| `async_render` | boolean | **true** | **Ejecutar render via Cloud Tasks (asíncrono)** |

**Comportamiento con `async_render=true` (default):**
1. Encola tarea de render en Cloud Tasks
2. Retorna inmediatamente con status 202
3. Render se ejecuta en background
4. Hacer polling hasta `status === "completed"`

**Comportamiento con `async_render=false`:**
- Ejecuta render síncronamente
- Bloquea hasta que el render termine (~1-3 minutos)
- Retorna directamente el resultado

**Calidades Disponibles:**

| Quality | CRF | Preset | Descripción |
|---------|-----|--------|-------------|
| standard | 23 | medium | Buena calidad, rápido |
| high | 18 | slow | Alta calidad |
| 4k | 16 | slow | Máxima calidad |

**Response con `async_render=true` (202 Accepted):**

```json
{
  "workflow_id": "550e8400-...",
  "status": "rendering",
  "message": "Render started. Poll GET /workflow/{id}/render for status.",
  "task_enqueued": {
    "success": true,
    "task_type": "render",
    "task_name": "projects/autoedit-at/locations/us-central1/queues/autoedit-pipeline/tasks/..."
  }
}
```

**Response con `async_render=false` (200 OK):**

```json
{
  "workflow_id": "550e8400-...",
  "status": "completed",
  "output_url": "https://storage.example.com/final_550e8400.mp4",
  "output_duration_ms": 13200,
  "stats": {
    "original_duration_ms": 45000,
    "result_duration_ms": 13200,
    "removal_percentage": 70.6,
    "render_time_sec": 45.2,
    "output_quality": "high"
  },
  "message": "Final render complete"
}
```

> **Nota:** Con `async_render=true`, hacer polling en `GET /workflow/{id}/render` hasta `status === "completed"` (~1-3 minutos)

---

### GET /v1/autoedit/workflow/{workflow_id}/render

Obtener estado del render en progreso.

**Response (200 OK):**

```json
{
  "workflow_id": "550e8400-...",
  "status": "rendering",
  "progress_percent": 45,
  "message": "Rendering in progress..."
}
```

O si está completado:

```json
{
  "workflow_id": "550e8400-...",
  "status": "completed",
  "output_url": "https://storage.example.com/final_550e8400.mp4",
  "output_duration_ms": 13200,
  "stats": {...},
  "message": "Render complete"
}
```

---

### GET /v1/autoedit/workflow/{workflow_id}/result

Obtener el video final renderizado.

**Response (200 OK):**

```json
{
  "workflow_id": "550e8400-...",
  "status": "completed",
  "output_url": "https://storage.example.com/final_550e8400.mp4",
  "output_duration_ms": 13200,
  "video_url": "https://storage.example.com/original.mp4",
  "stats": {...},
  "cuts": [
    {"start": "0.300", "end": "5.720"},
    {"start": "7.220", "end": "15.000"}
  ],
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T10:45:00Z"
}
```

---

### POST /v1/autoedit/workflow/{workflow_id}/rerender

Re-renderizar con diferente calidad (sin volver a HITL).

**Request Body:**

```json
{
  "quality": "4k",
  "crossfade_duration": 0.025
}
```

**Response (200 OK):**

```json
{
  "workflow_id": "550e8400-...",
  "status": "completed",
  "output_url": "https://storage.example.com/final_550e8400_4k.mp4",
  "output_duration_ms": 13200,
  "stats": {...},
  "message": "Re-render complete at 4k quality"
}
```

---

### GET /v1/autoedit/workflow/{workflow_id}/estimate

Estimar tiempo de render para el workflow.

**Query Parameters:**

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `quality` | string | "high" | Calidad para estimar |

**Response (200 OK):**

```json
{
  "workflow_id": "550e8400-...",
  "block_count": 15,
  "estimated_preview_seconds": 8.5,
  "estimated_render_seconds": {
    "standard": 25.0,
    "high": 45.0,
    "4k": 120.0
  },
  "recommended_quality": "high"
}
```

---

## Multi-Video Projects (Fase 3)

### Overview

Los proyectos permiten agrupar múltiples videos para procesamiento batch. Cada proyecto contiene workflows (videos) que se procesan en paralelo.

**Flujo típico:**
1. Crear proyecto con nombre y opciones
2. Agregar videos (crea workflows automáticamente)
3. Iniciar batch processing
4. Monitorear progreso con stats

### POST /v1/autoedit/project

Crear un nuevo proyecto multi-video.

**Request Body:**

```json
{
  "name": "Mi Proyecto de Videos",
  "description": "Videos del evento 2025",
  "options": {
    "language": "es",
    "style": "dynamic",
    "auto_broll": true
  }
}
```

| Campo | Tipo | Requerido | Default | Descripción |
|-------|------|-----------|---------|-------------|
| `name` | string | Sí | - | Nombre del proyecto |
| `description` | string | No | "" | Descripción |
| `options.language` | string | No | "es" | Idioma para transcripción |
| `options.style` | string | No | "dynamic" | Estilo de análisis |
| `options.auto_broll` | boolean | No | false | Ejecutar análisis B-Roll |

**Response (201 Created):**

```json
{
  "status": "success",
  "project_id": "proj_550e8400-...",
  "name": "Mi Proyecto de Videos",
  "state": "created",
  "workflow_ids": [],
  "stats": {
    "total_videos": 0,
    "completed": 0,
    "pending": 0,
    "failed": 0
  }
}
```

---

### GET /v1/autoedit/project/{project_id}

Obtener datos de un proyecto.

**Response (200 OK):**

```json
{
  "project_id": "proj_550e8400-...",
  "name": "Mi Proyecto",
  "description": "...",
  "state": "processing",
  "workflow_ids": ["wf_1", "wf_2", "wf_3"],
  "options": {...},
  "stats": {
    "total_videos": 3,
    "completed": 1,
    "pending": 2,
    "failed": 0,
    "total_original_duration_ms": 180000,
    "total_result_duration_ms": 108000,
    "avg_removal_percentage": 40.0
  },
  "created_at": "2025-12-15T10:00:00Z",
  "updated_at": "2025-12-15T11:30:00Z"
}
```

---

### GET /v1/autoedit/projects

Listar todos los proyectos.

**Query Parameters:**

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `state` | string | Filtrar por estado (opcional) |
| `limit` | integer | Máximo resultados (default: 100) |

**Response (200 OK):**

```json
{
  "projects": [
    {
      "project_id": "proj_...",
      "name": "Proyecto 1",
      "state": "completed",
      "total_videos": 5,
      "created_at": "..."
    }
  ],
  "total": 3
}
```

---

### DELETE /v1/autoedit/project/{project_id}

Eliminar un proyecto. **No elimina los workflows asociados.**

**Query Parameters:**

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `delete_workflows` | boolean | false | También eliminar workflows |

**Response (200 OK):**

```json
{
  "status": "success",
  "message": "Project deleted",
  "project_id": "proj_...",
  "workflows_deleted": false
}
```

---

### POST /v1/autoedit/project/{project_id}/videos

Agregar videos al proyecto. Crea workflows automáticamente.

**Request Body:**

```json
{
  "videos": [
    {"video_url": "https://storage.example.com/video1.mp4"},
    {"video_url": "https://storage.example.com/video2.mp4"}
  ]
}
```

**Response (201 Created):**

```json
{
  "status": "success",
  "workflows_created": [
    {"workflow_id": "wf_1", "video_url": "https://..."},
    {"workflow_id": "wf_2", "video_url": "https://..."}
  ],
  "total_videos": 5
}
```

---

### DELETE /v1/autoedit/project/{project_id}/videos/{workflow_id}

Remover un video del proyecto. **No elimina el workflow.**

**Response (200 OK):**

```json
{
  "status": "success",
  "message": "Video removed from project",
  "workflow_id": "wf_...",
  "note": "Workflow was NOT deleted"
}
```

---

### POST /v1/autoedit/project/{project_id}/start

Iniciar batch processing para videos pendientes del proyecto.

**Request Body:**

```json
{
  "parallel_limit": 3,
  "webhook_url": "https://mi-backend.com/project-complete",
  "workflow_ids": ["wf_abc", "wf_def"],
  "include_failed": false
}
```

| Campo | Tipo | Default | Descripcion |
|-------|------|---------|-------------|
| `parallel_limit` | integer | 3 | Videos a procesar en paralelo (1-10) |
| `webhook_url` | string | null | Webhook para notificaciones |
| `workflow_ids` | array | null | **Nuevo v1.4.1:** IDs especificos a procesar (deben pertenecer al proyecto) |
| `include_failed` | boolean | false | **Nuevo v1.4.1:** Incluir workflows con status "error" (reintentar fallidos) |

**Comportamiento de Filtrado:**

- **Sin `workflow_ids`:** Procesa todos los workflows del proyecto con status "created"
- **Con `workflow_ids`:** Solo procesa los IDs especificados (si tienen status "startable")
- **Estados "startable":** `created` (y `error` si `include_failed=true`)
- **Estados que se omiten:** `pending_review_1`, `pending_review_2`, `transcribing`, `analyzing`, `completed`, etc.

**Response (202 Accepted):**

```json
{
  "status": "success",
  "message": "Started processing 2 video(s)",
  "project_id": "proj_...",
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

| Campo Response | Descripcion |
|----------------|-------------|
| `tasks_enqueued` | Numero de tareas encoladas exitosamente |
| `total_workflows` | Total de workflows en el proyecto |
| `pending_workflows` | Workflows en estado "startable" |
| `skipped_count` | Workflows omitidos (no en estado startable) |
| `skipped_by_status` | Desglose de workflows omitidos por status |
| `invalid_workflow_ids` | IDs de `workflow_ids` que no pertenecen al proyecto |

**Casos de Uso:**

1. **Procesar solo videos nuevos (comportamiento por defecto):**
   ```json
   {"parallel_limit": 3}
   ```
   Solo procesa workflows con status="created", omite los ya procesados.

2. **Procesar workflows especificos:**
   ```json
   {"workflow_ids": ["wf_nuevo_1", "wf_nuevo_2"]}
   ```
   Util cuando el frontend sabe exactamente que videos procesar.

3. **Reintentar videos fallidos:**
   ```json
   {"include_failed": true}
   ```
   Procesa workflows con status="created" y status="error".

**Notas:**
- Los videos se procesan en batches segun `parallel_limit`
- Cada batch tiene un delay de 5 segundos para evitar saturacion
- Hacer polling en `GET /project/{id}/stats` para monitorear progreso
- La respuesta `skipped_by_status` permite al frontend mostrar por que algunos videos no se procesaron

---

### GET /v1/autoedit/project/{project_id}/stats

Obtener estadísticas agregadas actualizadas.

**Response (200 OK):**

```json
{
  "status": "success",
  "project_id": "proj_...",
  "state": "processing",
  "stats": {
    "total_videos": 5,
    "completed": 2,
    "pending": 2,
    "failed": 1,
    "total_original_duration_ms": 300000,
    "total_result_duration_ms": 180000,
    "avg_removal_percentage": 40.0
  }
}
```

---

## B-Roll Analysis (Fase 3)

### Overview

El análisis B-Roll utiliza Gemini Vision para identificar segmentos de video que **no contienen diálogo** (footage de apoyo visual).

**Características:**
- Extracción de frames (1 cada 2 segundos)
- Análisis visual con Gemini 2.5 Pro Vision
- Categorización automática (establishing, detail, transition, etc.)
- Scoring de calidad técnica y utilidad

**Flujo:**
1. Se extraen frames del video con FFmpeg
2. Frames se envían a Gemini Vision via Vertex AI
3. Gemini identifica segmentos B-Roll
4. Resultados se almacenan en el workflow

### B-Roll Segment Structure

```json
{
  "segment_id": "broll_001",
  "inMs": 5720,
  "outMs": 12450,
  "duration_ms": 6730,
  "type": "B-Roll",
  "category": "establishing_shot",
  "description": "Toma aérea de la ciudad al atardecer",
  "scores": {
    "technical_quality": 4,
    "visual_appeal": 5,
    "usefulness": 4,
    "overall": 4
  },
  "potential_use": ["Establecimiento", "Intro"],
  "has_motion": true,
  "has_text_overlay": false,
  "is_timelapse": false,
  "confidence": 0.92
}
```

### Categorías B-Roll

| Categoría | Descripción | Ejemplos |
|-----------|-------------|----------|
| `establishing_shot` | Tomas amplias de ubicación | Fachadas, paisajes, vistas aéreas |
| `detail_shot` | Close-ups de objetos | Manos, productos, pantallas |
| `transition_shot` | Tomas para transiciones | Cielos, movimiento blur |
| `ambient_shot` | Ambiente y contexto | Calles, gente caminando |
| `action_shot` | Actividades sin diálogo | Escribiendo, cocinando |
| `nature_shot` | Elementos naturales | Plantas, agua, animales |

### Cloud Task: analyze-broll

Este endpoint es llamado por Cloud Tasks (no directamente por el frontend).

**Endpoint:** `POST /v1/autoedit/tasks/analyze-broll`

**Request Body:**

```json
{
  "workflow_id": "550e8400-..."
}
```

**Response (200 OK):**

```json
{
  "status": "broll_analyzed",
  "workflow_id": "550e8400-...",
  "segments_count": 5,
  "total_broll_duration_ms": 24500,
  "broll_percentage": 13.6,
  "message": "B-Roll analysis complete."
}
```

---

## Multi-Video Context & Consolidation (Fase 4B)

### Overview

El sistema de contexto multi-video permite:
- **Embeddings de Video**: Usando TwelveLabs Marengo 3.0 para similitud visual
- **Contexto Progresivo**: Pasar contexto de videos analizados a videos posteriores
- **Detección de Redundancias**: Identificar contenido similar entre videos
- **Consolidación**: Análisis global de narrativa y recomendaciones de corte

**Flujo típico:**
1. Analizar todos los videos del proyecto (transcripción + Gemini)
2. Ejecutar consolidación para generar embeddings y detectar redundancias
3. Revisar recomendaciones (opcional HITL 3)
4. Aplicar recomendaciones seleccionadas

### POST /v1/autoedit/project/{project_id}/consolidate

Ejecutar el pipeline de consolidación completo.

**Request Body:**

```json
{
  "force_regenerate": false,
  "redundancy_threshold": 0.85,
  "auto_apply": false,
  "webhook_url": "https://mi-backend.com/consolidation-complete"
}
```

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `force_regenerate` | boolean | false | Regenerar embeddings/summaries aunque existan |
| `redundancy_threshold` | float | 0.85 | Umbral de similitud para redundancia (0.5-1.0) |
| `auto_apply` | boolean | false | Aplicar recomendaciones automáticamente (skip HITL 3) |
| `webhook_url` | string | null | Webhook para notificación al completar |

**Response (200 OK):**

```json
{
  "success": true,
  "project_id": "proj_...",
  "consolidation": {
    "status": "success",
    "started_at": "2025-12-19T10:00:00Z",
    "completed_at": "2025-12-19T10:02:30Z",
    "workflow_count": 5,
    "steps": {
      "embeddings": {
        "status": "success",
        "generated": 3,
        "existing": 2,
        "failed": []
      },
      "summaries": {
        "status": "success",
        "generated": 5,
        "existing": 0
      },
      "redundancies": {
        "status": "success",
        "redundancies_found": 4,
        "recommendations_generated": 3,
        "redundancy_score": 35.5
      },
      "narrative": {
        "status": "success",
        "arc_type": "complete",
        "tone_consistency": 0.8
      }
    },
    "recommendations": [...]
  }
}
```

---

### GET /v1/autoedit/project/{project_id}/consolidation-status

Obtener estado actual de consolidación.

**Response (200 OK):**

```json
{
  "success": true,
  "project_id": "proj_...",
  "consolidation_state": "consolidated",
  "consolidation_updated_at": "2025-12-19T10:02:30Z",
  "has_redundancy_analysis": true,
  "has_project_context": true,
  "redundancy_count": 4,
  "topics_covered": 12
}
```

---

### GET /v1/autoedit/project/{project_id}/redundancies

Obtener análisis de redundancias entre videos.

**Query Parameters:**

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `include_segments` | boolean | Incluir detalles de segmentos (default: false) |
| `min_severity` | string | Filtrar por severidad mínima: high, medium, low |

**Response (200 OK):**

```json
{
  "success": true,
  "project_id": "proj_...",
  "redundancy_count": 4,
  "redundancy_score": 35.5,
  "interpretation": "Moderate redundancy - some repeated content detected",
  "removable_duration_sec": 45.3,
  "analyzed_at": "2025-12-19T10:02:00Z",
  "redundancies_summary": [
    {
      "id": "red_abc123_def456_0",
      "severity": "high",
      "similarity": 0.95,
      "video_a_index": 0,
      "video_b_index": 2
    }
  ],
  "recommendations": [...]
}
```

---

### GET /v1/autoedit/project/{project_id}/narrative

Obtener análisis narrativo global del proyecto.

**Response (200 OK):**

```json
{
  "success": true,
  "project_id": "proj_...",
  "arc_type": "complete",
  "narrative_functions": {
    "introduction": 1,
    "rising_action": 2,
    "climax": 1,
    "resolution": 1
  },
  "tone_consistency": 0.8,
  "unique_tones": ["informativo", "entusiasta"],
  "video_sequence": [
    {
      "index": 0,
      "function": "introduction",
      "tone": "informativo",
      "summary": "Introducción al tema principal..."
    }
  ],
  "analyzed_at": "2025-12-19T10:02:30Z"
}
```

---

### GET /v1/autoedit/project/{project_id}/recommendations

Obtener recomendaciones de corte basadas en redundancias.

**Query Parameters:**

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `priority` | string | Filtrar por prioridad: high, medium, low |

**Response (200 OK):**

```json
{
  "success": true,
  "project_id": "proj_...",
  "recommendation_count": 3,
  "total_savings_sec": 45.3,
  "recommendations": [
    {
      "id": "rec_red_abc123_0",
      "type": "remove_redundant_segment",
      "priority": "high",
      "action": {
        "workflow_id": "wf_...",
        "segment": {
          "start_sec": 120.5,
          "end_sec": 135.8,
          "index": 5
        }
      },
      "reason": "Similar content (95%) already in video 1",
      "similarity": 0.95,
      "estimated_savings_sec": 15.3,
      "keep_reference": {
        "workflow_id": "wf_first...",
        "segment": {...}
      }
    }
  ]
}
```

---

### POST /v1/autoedit/project/{project_id}/apply-recommendations

Aplicar recomendaciones de corte a los workflows.

**Request Body:**

```json
{
  "recommendation_ids": ["rec_1", "rec_2"],
  "webhook_url": "https://..."
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `recommendation_ids` | array | IDs específicos a aplicar (vacío = todos) |
| `webhook_url` | string | Webhook para notificación |

**Response (200 OK):**

```json
{
  "success": true,
  "project_id": "proj_...",
  "status": "success",
  "applied_count": 2,
  "failed_count": 0,
  "applied": ["rec_1", "rec_2"],
  "failed": []
}
```

---

### PUT /v1/autoedit/project/{project_id}/videos/reorder

Reordenar videos en la secuencia del proyecto.

**Request Body:**

```json
{
  "workflow_ids": ["wf_3", "wf_1", "wf_2"]
}
```

**Response (200 OK):**

```json
{
  "success": true,
  "project_id": "proj_...",
  "workflow_ids": ["wf_3", "wf_1", "wf_2"],
  "message": "Videos reordered successfully"
}
```

**Nota:** Reordenar invalida la consolidación existente (requiere re-consolidar).

---

### GET /v1/autoedit/project/{project_id}/context

Obtener contexto acumulado del proyecto.

**Response (200 OK):**

```json
{
  "success": true,
  "project_id": "proj_...",
  "covered_topics": ["tema1", "tema2", "tema3"],
  "entities_introduced": ["lugar1", "persona1"],
  "narrative_functions": {
    "introduction": 1,
    "rising_action": 2
  },
  "total_videos": 5,
  "updated_at": "2025-12-19T10:02:30Z"
}
```

---

### GET /v1/autoedit/project/{project_id}/summaries

Obtener resúmenes de todos los videos del proyecto.

**Response (200 OK):**

```json
{
  "success": true,
  "project_id": "proj_...",
  "summary_count": 5,
  "summaries": [
    {
      "workflow_id": "wf_...",
      "sequence_index": 0,
      "summary": "Resumen del video...",
      "key_points": ["punto1", "punto2"],
      "entities_mentioned": ["entidad1"],
      "topics_covered": ["tema1"],
      "narrative_function": "introduction",
      "emotional_tone": "informativo",
      "created_at": "2025-12-19T10:01:00Z"
    }
  ]
}
```

---

### Consolidation States

| Estado | Descripción |
|--------|-------------|
| `not_started` | Consolidación no iniciada |
| `generating_embeddings` | Generando embeddings con TwelveLabs |
| `generating_summaries` | Generando resúmenes con Gemini |
| `detecting_redundancies` | Detectando redundancias cross-video |
| `analyzing_narrative` | Analizando estructura narrativa |
| `consolidating` | Ejecutando pipeline completo |
| `consolidated` | Consolidación completa, lista para revisión |
| `review_consolidation` | Usuario revisando recomendaciones |
| `applying_recommendations` | Aplicando cortes recomendados |
| `consolidation_complete` | Recomendaciones aplicadas |
| `consolidation_failed` | Proceso falló |
| `invalidated` | Consolidación invalidada (videos reordenados/agregados) |

---

## Schemas

### Block

```json
{
  "id": "string",
  "inMs": "integer (timestamp inicio en video original)",
  "outMs": "integer (timestamp fin en video original)",
  "text": "string (texto del segmento)",
  "preview_inMs": "integer (posición en preview, opcional)"
}
```

### Gap

```json
{
  "id": "string",
  "inMs": "integer",
  "outMs": "integer",
  "reason": "string (silence | filler_words | user_deleted)",
  "text": "string (texto eliminado, opcional)"
}
```

### Stats

```json
{
  "original_duration_ms": "integer",
  "result_duration_ms": "integer",
  "removal_percentage": "float",
  "render_time_sec": "float (opcional)",
  "output_quality": "string (opcional)"
}
```

### Modification

```json
{
  "action": "string (adjust | split | merge | delete | restore_gap)",
  "block_id": "string (para adjust, split, delete)",
  "block_ids": ["string"] (para merge),
  "gap_id": "string (para restore_gap)",
  "gap_index": "integer (alternativa a gap_id)",
  "new_inMs": "integer (para adjust)",
  "new_outMs": "integer (para adjust)",
  "split_at_ms": "integer (para split)"
}
```

---

## Códigos de Error

### 400 Bad Request

```json
{
  "error": "Invalid XML format. Expected <resultado> root element.",
  "workflow_id": "550e8400-..."
}
```

Causas comunes:
- JSON inválido en request body
- Campos requeridos faltantes
- Valores fuera de rango permitido
- XML mal formado

### 404 Not Found

```json
{
  "error": "Workflow not found",
  "workflow_id": "550e8400-..."
}
```

### 500 Internal Server Error

```json
{
  "error": "FFmpeg compose failed: ...",
  "workflow_id": "550e8400-..."
}
```

---

## Workflow States

| Estado | Descripción | Acción Requerida | Endpoint |
|--------|-------------|------------------|----------|
| `created` | Workflow recién creado | **Transcribir el video** | `POST /workflow/{id}/transcribe` |
| `transcribing` | Transcribiendo con ElevenLabs | Esperar... | (polling con GET) |
| `transcribed` | Transcripción completa | **Analizar con Gemini** | `POST /workflow/{id}/analyze` |
| `analyzing` | Analizando con Gemini | Esperar... | (polling con GET) |
| `pending_review_1` | HITL 1: XML listo para revisión | Revisar y aprobar XML | `GET/PUT /workflow/{id}/analysis` |
| `xml_approved` | XML aprobado por usuario | **Procesar a blocks** | `POST /workflow/{id}/process` |
| `processing` | Mapeando XML a timestamps | Esperar... | (polling con GET) |
| `generating_preview` | Generando preview low-res | Esperar... | (polling con GET) |
| `pending_review_2` | HITL 2: Preview listo | Revisar preview y aprobar | `GET /workflow/{id}/preview`, `POST /render` |
| `modifying_blocks` | Usuario modificando blocks | Regenerar preview | `PATCH /blocks`, `POST /preview` |
| `regenerating_preview` | Regenerando preview | Esperar... | (polling con GET) |
| `rendering` | Procesando video final | Esperar... | `GET /workflow/{id}/render` |
| `completed` | Video final listo | Obtener resultado | `GET /workflow/{id}/result` |
| `error` | Error en algún paso | Ver detalles del error | `GET /workflow/{id}` |

### Flujo Típico de Llamadas

```
1. POST /workflow                          → status: created
2. POST /workflow/{id}/transcribe          → status: transcribing → transcribed
3. POST /workflow/{id}/analyze             → status: analyzing → pending_review_1
4. GET  /workflow/{id}/analysis            → obtener XML para UI
5. PUT  /workflow/{id}/analysis            → status: xml_approved
6. POST /workflow/{id}/process             → status: processing → generating_preview
7. POST /workflow/{id}/preview             → status: pending_review_2
8. (opcional) PATCH /workflow/{id}/blocks  → modificar y volver a POST /preview
9. POST /workflow/{id}/render              → status: rendering → completed
10. GET /workflow/{id}/result              → obtener video final
```

---

## Rate Limits

- **Requests por minuto**: 60
- **Workflows concurrentes**: 10
- **Tamaño máximo de video**: 2GB
- **Duración máxima de video**: 60 minutos

---

## Changelog

### v1.4.0 (2025-12) - Fase 4B
- **Multi-Video Context**: Sistema de contexto progresivo entre videos
  - TwelveLabs Marengo 3.0 para video embeddings
  - Context Builder para resúmenes semánticos por video
  - Contexto acumulado mejora análisis de videos posteriores
- **Redundancy Detection**: Detección de contenido similar cross-video
  - Similitud coseno con umbral configurable (default 0.85)
  - Categorización de severidad: high (>0.9), medium (>0.8), low (>0.7)
  - Generación automática de recomendaciones de corte
- **Project Consolidation**: Pipeline completo de consolidación
  - Análisis narrativo global (arc type, tone consistency)
  - HITL 3 opcional para revisión de recomendaciones
- **Nuevos Endpoints**:
  - `POST /v1/autoedit/project/{id}/consolidate` - Ejecutar consolidación
  - `GET /v1/autoedit/project/{id}/consolidation-status` - Estado de consolidación
  - `GET /v1/autoedit/project/{id}/redundancies` - Obtener redundancias
  - `GET /v1/autoedit/project/{id}/narrative` - Análisis narrativo
  - `GET /v1/autoedit/project/{id}/recommendations` - Recomendaciones de corte
  - `POST /v1/autoedit/project/{id}/apply-recommendations` - Aplicar recomendaciones
  - `PUT /v1/autoedit/project/{id}/videos/reorder` - Reordenar videos
  - `GET /v1/autoedit/project/{id}/context` - Contexto acumulado
  - `GET /v1/autoedit/project/{id}/summaries` - Resúmenes de videos

### v1.3.0 (2025-12) - Fase 3
- **Multi-Video Projects**: Soporte para proyectos con múltiples videos
  - CRUD completo de proyectos
  - Batch processing con paralelización configurable
  - Estadísticas agregadas por proyecto
- **B-Roll Analysis**: Análisis visual con Gemini Vision
  - Extracción de frames con FFmpeg
  - Identificación automática de segmentos B-Roll
  - Categorización: establishing, detail, transition, ambient, action shots
  - Scoring de calidad técnica y utilidad (1-5)
- **Nuevos Endpoints**:
  - `POST /v1/autoedit/project` - Crear proyecto
  - `GET /v1/autoedit/project/{id}` - Obtener proyecto
  - `DELETE /v1/autoedit/project/{id}` - Eliminar proyecto
  - `GET /v1/autoedit/projects` - Listar proyectos
  - `POST /v1/autoedit/project/{id}/videos` - Agregar videos
  - `DELETE /v1/autoedit/project/{id}/videos/{wf}` - Remover video
  - `POST /v1/autoedit/project/{id}/start` - Iniciar batch processing
  - `GET /v1/autoedit/project/{id}/stats` - Estadísticas
  - `POST /v1/autoedit/tasks/analyze-broll` - Análisis B-Roll (Cloud Task)
- **Campos Workflow Nuevos**:
  - `project_id`: Asociación opcional con proyecto
  - `broll_segments`: Segmentos B-Roll identificados
  - `broll_analysis_complete`: Flag de análisis completado

### v1.2.0 (2025-01)
- **Cloud Tasks Integration**: Orquestación asíncrona completa
  - Cada tarea encola automáticamente la siguiente
  - `transcribe → analyze → (HITL 1) → process → preview → (HITL 2) → render`
  - Retry automático con exponential backoff
- **GCS Workflow Storage**: Persistencia en Google Cloud Storage
  - Workflows almacenados en GCS (no /tmp volátil)
  - TTL de 24 horas con auto-limpieza
  - Sobrevive reinicios y permite acceso multi-worker
- **Optimistic Locking**: Prevención de race conditions
  - Conditional updates con GCS generations
  - Retry logic para eventual consistency (max 3 intentos)
  - Previene pérdida de actualizaciones concurrentes
- **file_url vs output_url Fix**: Manejo de formatos FFmpeg
  - Detecta automáticamente `file_url` o `output_url` en respuesta de render
  - Previene errores cuando FFmpeg cambia formato de respuesta
- **Webhook Pattern**: Notificaciones push opcionales
  - POST a webhook_url después de cada paso completado
  - Retry con exponential backoff (3 intentos, 5s/15s/45s)
  - Reduce necesidad de polling desde frontend
- **Cloud Tasks Quotas**: Documentación de límites y monitoreo
  - 500 tasks/sec dispatch rate
  - 1000 tareas concurrentes máximo
  - Comandos gcloud para monitoreo de colas

### v1.1.0 (2025-01)
- **Cloud Tasks Pipeline**: Procesamiento automático asíncrono
  - `auto_start=true` por defecto en POST /workflow
  - `auto_continue=true` por defecto en PUT /analysis
  - `async_render=true` por defecto en POST /render
- Frontend simplificado: solo 3 interacciones necesarias
- Fallback automático a ejecución síncrona si Cloud Tasks falla
- Nueva documentación con diagramas de flujo automático

### v1.0.0 (2025-01)
- Release inicial con workflow completo
- HITL 1 (XML review) y HITL 2 (preview + blocks)
- Render profiles: preview, standard, high, 4k
