# AutoEdit API Reference

Documentación completa de la API REST para el pipeline de edición automática de video con AI.

**Versión**: 1.0.0

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

Todas las respuestas siguen el formato estándar del NCA Toolkit:

```json
{
  "code": 200,
  "id": "user_provided_id",
  "job_id": "uuid-generado",
  "response": { ... },
  "message": "success",
  "run_time": 1.234,
  "queue_time": 0.567,
  "total_time": 1.801
}
```

---

## Endpoints Overview

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/v1/autoedit/workflow` | Crear nuevo workflow |
| GET | `/v1/autoedit/workflow/{id}` | Obtener estado del workflow |
| DELETE | `/v1/autoedit/workflow/{id}` | Eliminar workflow |
| GET | `/v1/autoedit/workflows` | Listar todos los workflows |
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

Crear un nuevo workflow de edición automática.

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
  "id": "mi-id-personalizado"
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `video_url` | string (uri) | Sí | URL del video a procesar |
| `options.language` | string | No | Código de idioma (default: "es") |
| `options.style` | string | No | Estilo de edición: "dynamic", "conservative", "aggressive" |
| `options.skip_hitl_1` | boolean | No | Saltar revisión de XML (default: false) |
| `options.skip_hitl_2` | boolean | No | Saltar revisión de preview (default: false) |
| `id` | string | No | ID personalizado para el request |

**Response (201 Created):**

```json
{
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "created",
  "status_message": "Workflow creado",
  "message": "Workflow created successfully"
}
```

**cURL Example:**

```bash
curl -X POST https://api.example.com/v1/autoedit/workflow \
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

Enviar el XML revisado/modificado por el usuario.

**Request Body:**

```json
{
  "updated_xml": "<resultado><mantener>Hola bienvenidos eh um al video de hoy</mantener></resultado>"
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `updated_xml` | string | Sí | XML con cambios del usuario |

**Response (200 OK):**

```json
{
  "workflow_id": "550e8400-...",
  "status": "xml_approved",
  "message": "XML approved. Ready for processing to blocks."
}
```

**Validación:**
- El XML debe contener `<resultado>` como elemento raíz
- Solo se permiten tags `<mantener>` y `<eliminar>`

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

Aprobar blocks e iniciar render final de alta calidad.

**Request Body:**

```json
{
  "quality": "high",
  "crossfade_duration": 0.025
}
```

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `quality` | string | "high" | Calidad: "standard", "high", "4k" |
| `crossfade_duration` | number | 0.025 | Duración del crossfade (0.01-0.5s) |

**Calidades Disponibles:**

| Quality | CRF | Preset | Descripción |
|---------|-----|--------|-------------|
| standard | 23 | medium | Buena calidad, rápido |
| high | 18 | slow | Alta calidad |
| 4k | 16 | slow | Máxima calidad |

**Response (200 OK):**

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

| Estado | Descripción | Siguiente Paso |
|--------|-------------|----------------|
| `created` | Workflow recién creado | Transcribir |
| `transcribing` | Transcribiendo con ElevenLabs | Esperar |
| `transcribed` | Transcripción completa | Analizar |
| `analyzing` | Analizando con Gemini | Esperar |
| `pending_review_1` | HITL 1: Esperando revisión de XML | GET/PUT analysis |
| `xml_approved` | XML aprobado | POST process |
| `processing` | Mapeando XML a timestamps | Esperar |
| `generating_preview` | Generando preview low-res | Esperar |
| `pending_review_2` | HITL 2: Preview listo | PATCH blocks o POST render |
| `modifying_blocks` | Usuario modificando blocks | POST preview |
| `regenerating_preview` | Regenerando preview | Esperar |
| `rendering` | Procesando video final | GET render |
| `completed` | Video final listo | GET result |
| `error` | Error en algún paso | Ver detalles |

---

## Rate Limits

- **Requests por minuto**: 60
- **Workflows concurrentes**: 10
- **Tamaño máximo de video**: 2GB
- **Duración máxima de video**: 60 minutos

---

## Changelog

### v1.0.0 (2025-01)
- Release inicial con workflow completo
- HITL 1 (XML review) y HITL 2 (preview + blocks)
- Render profiles: preview, standard, high, 4k
