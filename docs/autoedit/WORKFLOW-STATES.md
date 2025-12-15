# AutoEdit Workflow States

Diagrama y descripción de los estados del workflow de edición automática.

---

## Diagrama de Estados

```
                              ┌─────────────┐
                              │   created   │
                              └──────┬──────┘
                                     │ POST /transcribe (externo)
                                     ▼
                              ┌─────────────┐
                              │transcribing │
                              └──────┬──────┘
                                     │ (automático)
                                     ▼
                              ┌─────────────┐
                              │ transcribed │
                              └──────┬──────┘
                                     │ POST /analyze (externo)
                                     ▼
                              ┌─────────────┐
                              │  analyzing  │
                              └──────┬──────┘
                                     │ (automático)
                                     ▼
┌────────────────────────────────────────────────────────────────┐
│                         HITL 1                                  │
│  ┌─────────────────┐                                           │
│  │pending_review_1 │◄──────────────────────────────────┐       │
│  └────────┬────────┘                                   │       │
│           │                                            │       │
│           │ PUT /analysis                              │       │
│           │ (usuario aprueba XML)                      │       │
│           ▼                                            │       │
│  ┌─────────────────┐                                   │       │
│  │  xml_approved   │                                   │       │
│  └────────┬────────┘                                   │       │
└───────────┼────────────────────────────────────────────┘       │
            │                                                     │
            │ POST /process                                       │
            ▼                                                     │
     ┌─────────────┐                                             │
     │ processing  │                                             │
     └──────┬──────┘                                             │
            │ (automático)                                        │
            ▼                                                     │
┌────────────────────────────────────────────────────────────────┐
│                         HITL 2                                  │
│                                                                 │
│  ┌───────────────────┐                                         │
│  │generating_preview │◄─────────────────────────┐              │
│  └─────────┬─────────┘                          │              │
│            │ (automático)                       │              │
│            ▼                                    │              │
│  ┌───────────────────┐    PATCH /blocks   ┌────┴────────┐     │
│  │ pending_review_2  │───────────────────►│modifying_   │     │
│  └─────────┬─────────┘                    │   blocks    │     │
│            │                              └──────┬──────┘     │
│            │                                     │             │
│            │                          POST /preview            │
│            │                                     │             │
│            │                              ┌──────▼──────┐     │
│            │                              │regenerating_│     │
│            │                              │   preview   │     │
│            │                              └──────┬──────┘     │
│            │                                     │             │
│            │◄────────────────────────────────────┘             │
│            │                                                   │
└────────────┼───────────────────────────────────────────────────┘
             │
             │ POST /render
             │ (usuario aprueba blocks)
             ▼
      ┌─────────────┐
      │  rendering  │
      └──────┬──────┘
             │ (automático)
             ▼
      ┌─────────────┐
      │  completed  │
      └─────────────┘


Estado de Error (puede ocurrir en cualquier punto):

      ┌─────────────┐
      │    error    │
      └─────────────┘
```

---

## Cloud Tasks Integration

El pipeline AutoEdit utiliza **Google Cloud Tasks** para manejar transiciones de estado automáticas de forma asíncrona y resiliente.

### Estados Gestionados por Cloud Tasks

Las transiciones marcadas con ☁️ son ejecutadas por Cloud Tasks en segundo plano:

| Transición | Cloud Task | Timeout | Descripción |
|------------|------------|---------|-------------|
| `transcribing` → `transcribed` | **transcribe** | 60s | Callback de ElevenLabs + actualización estado |
| `analyzing` → `pending_review_1` | **analyze** | 30s | Procesamiento Gemini + generación XML |
| `processing` → `generating_preview` | **process** | 30s | Mapeo XML a timestamps + validación |
| `generating_preview` → `pending_review_2` | **preview** | 120s | Composición FFmpeg preview 480p |
| `regenerating_preview` → `pending_review_2` | **preview** | 120s | Recomposición con blocks modificados |
| `rendering` → `completed` | **render** | 600s | Render final con profile seleccionado |

### Beneficios de Cloud Tasks

1. **Desacople HTTP**: Respuestas 202 inmediatas, procesamiento en background
2. **Escalabilidad**: Queue distribuida, no bloquea workers de Cloud Run
3. **Resiliencia**: Reintentos automáticos (3x) con backoff exponencial
4. **Monitoreo**: Visibilidad completa en Cloud Console
5. **Timeouts Configurables**: Ajustables por tipo de tarea

### Flujo de Ejemplo

```
Frontend → POST /transcribe → 202 Accepted (inmediato)
                                ↓
                          Cloud Task "transcribe" (asíncrono)
                                ↓
                          workflow.status = "transcribed"
                                ↓
Frontend → GET /workflow → status: "transcribed" (polling)
```

Ver sección **Cloud Tasks Configuration** más abajo para detalles de timeouts y comparativa con modo síncrono.

---

## Estados en Detalle

### Fase 1: Transcripción y Análisis

| Estado | Descripción | Transición | Cloud Task |
|--------|-------------|------------|------------|
| `created` | Workflow recién creado, esperando inicio | → `transcribing` vía POST /transcribe | - |
| `transcribing` | ElevenLabs procesando audio | → `transcribed` (automático) | ☁️ **transcribe** |
| `transcribed` | Transcripción lista con timestamps | → `analyzing` vía POST /analyze | - |
| `analyzing` | Gemini analizando contenido | → `pending_review_1` (automático) | ☁️ **analyze** |

### HITL 1: Revisión de XML

| Estado | Descripción | Transición |
|--------|-------------|------------|
| `pending_review_1` | XML de Gemini listo para revisión | → `xml_approved` vía PUT /analysis |
| `xml_approved` | Usuario aprobó el XML | → `processing` vía POST /process |

**Acciones del Frontend en HITL 1:**
1. GET /analysis → Obtener XML
2. Renderizar UI con toggle mantener/eliminar
3. PUT /analysis → Enviar XML modificado

### Fase 2: Procesamiento

| Estado | Descripción | Transición | Cloud Task |
|--------|-------------|------------|------------|
| `processing` | Unified processor mapeando XML a timestamps | → `generating_preview` (automático) | ☁️ **process** |

### HITL 2: Preview y Refinamiento

| Estado | Descripción | Transición | Cloud Task |
|--------|-------------|------------|------------|
| `generating_preview` | FFmpeg generando preview 480p | → `pending_review_2` (automático) | ☁️ **preview** |
| `pending_review_2` | Preview listo para revisión | → `modifying_blocks` o `rendering` | - |
| `modifying_blocks` | Usuario ajustando blocks | → `regenerating_preview` vía POST /preview | - |
| `regenerating_preview` | Regenerando preview con cambios | → `pending_review_2` (automático) | ☁️ **preview** |

**Ciclo de HITL 2:**
```
pending_review_2 ──► modifying_blocks ──► regenerating_preview ──┐
       ▲                                                         │
       └─────────────────────────────────────────────────────────┘
```

**Acciones del Frontend en HITL 2:**
1. GET /preview → Obtener URL del video y blocks
2. Reproducir preview, mostrar timeline
3. PATCH /blocks → Modificar blocks
4. POST /preview → Regenerar preview
5. Repetir hasta satisfecho
6. POST /render → Aprobar y renderizar final

### Fase 3: Render Final

| Estado | Descripción | Transición | Cloud Task |
|--------|-------------|------------|------------|
| `rendering` | FFmpeg procesando video final | → `completed` (automático) | ☁️ **render** |
| `completed` | Video final disponible | (estado final) | - |

### Estado de Error

| Estado | Descripción | Recuperación |
|--------|-------------|--------------|
| `error` | Error en algún paso del proceso | Ver sección "Error Recovery" abajo |

**Estructura del Error:**
```json
{
  "status": "error",
  "error": "Error message description",
  "error_details": {
    "stage": "transcribing|analyzing|processing|generating_preview|rendering",
    "timestamp": "2024-01-15T10:30:00Z",
    "traceback": "Full Python traceback (if available)"
  }
}
```

---

## Transiciones Válidas

```python
VALID_TRANSITIONS = {
    "created": ["transcribing"],
    "transcribing": ["transcribed", "error"],
    "transcribed": ["analyzing"],
    "analyzing": ["pending_review_1", "error"],
    "pending_review_1": ["xml_approved"],
    "xml_approved": ["processing"],
    "processing": ["generating_preview", "error"],
    "generating_preview": ["pending_review_2", "error"],
    "pending_review_2": ["modifying_blocks", "rendering"],
    "modifying_blocks": ["regenerating_preview", "rendering"],
    "regenerating_preview": ["pending_review_2", "error"],
    "rendering": ["completed", "error"],
    "completed": ["rendering"],  # Para re-render
    "error": []  # Estado terminal (requiere nuevo workflow)
}
```

---

## Estados y Endpoints Disponibles

| Estado | GET status | GET analysis | PUT analysis | POST process | POST preview | GET preview | PATCH blocks | POST render | GET render |
|--------|------------|--------------|--------------|--------------|--------------|-------------|--------------|-------------|------------|
| created | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| transcribing | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| transcribed | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| analyzing | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| pending_review_1 | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| xml_approved | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| generating_preview | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| pending_review_2 | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ |
| modifying_blocks | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ |
| regenerating_preview | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| rendering | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| completed | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |

---

## Cloud Tasks Configuration

### Timeouts por Estado

| Estado | Cloud Task | Timeout | Descripción |
|--------|------------|---------|-------------|
| `transcribing` | **transcribe** | 60s | Procesamiento ElevenLabs + callback |
| `analyzing` | **analyze** | 30s | Análisis Gemini + generación XML |
| `processing` | **process** | 30s | Mapeo XML → timestamps |
| `generating_preview` | **preview** | 120s | Composición FFmpeg preview 480p |
| `rendering` | **render** | 600s | Render final (depende de profile) |

**Notas:**
- Los timeouts son configurables por Cloud Task en GCP
- Si un Cloud Task excede el timeout, el workflow pasa a estado `error`
- Los Cloud Tasks tienen retry automático (3 intentos por defecto)

### Tiempos Típicos por Estado

| Estado | Tiempo Típico | Cloud Task Timeout | Modo Síncrono | Factores |
|--------|---------------|-------------------|---------------|----------|
| transcribing | 30-120s | 60s | 120s | Duración del video |
| analyzing | 10-60s | 30s | 60s | Cantidad de texto |
| processing | 2-10s | 30s | 30s | Complejidad del XML |
| generating_preview | 5-15s | 120s | 120s | Número de cuts, duración |
| regenerating_preview | 5-15s | 120s | 120s | Número de cuts, duración |
| rendering (standard) | 30-120s | 600s | 600s | Duración resultado |
| rendering (high) | 60-180s | 600s | 600s | Duración resultado |
| rendering (4k) | 120-300s | 600s | 600s | Duración resultado |

### Comparativa: Cloud Tasks vs Síncrono

| Característica | Cloud Tasks (Asíncrono) | Síncrono |
|----------------|------------------------|----------|
| **Timeout HTTP** | No aplica (202 inmediato) | Límite Cloud Run (max 3600s) |
| **Escalabilidad** | Alta (cola distribuida) | Limitada (workers bloqueados) |
| **Reintentos** | Automáticos (3x) | Manual |
| **Monitoreo** | GCP Cloud Tasks UI | Logs únicamente |
| **Costo** | Task invocations ($0.40/million) | Incluido en Cloud Run |
| **Complejidad** | Media (configurar tasks) | Baja |
| **Recomendado para** | Producción, videos largos | Desarrollo, videos cortos |

**Cuándo usar Cloud Tasks:**
- Videos > 5 minutos
- Renderizado high/4k profile
- Tráfico concurrente alto
- Necesitas monitoreo detallado

**Cuándo usar Síncrono:**
- Desarrollo local
- Videos < 2 minutos
- Preview rápido
- Configuración simplificada

---

## Error Recovery

### Procedimientos de Recuperación

Cuando un workflow entra en estado `error`, el sistema proporciona información detallada para diagnosticar y recuperarse:

#### 1. Identificar el Error

```bash
GET /v1/autoedit/workflow/{workflow_id}
```

**Response con error:**
```json
{
  "workflow_id": "wf_abc123",
  "status": "error",
  "error": "FFmpeg render failed: Invalid codec parameters",
  "error_details": {
    "stage": "rendering",
    "timestamp": "2024-01-15T10:30:00Z",
    "traceback": "Traceback (most recent call last):\n  File..."
  },
  "metadata": {
    "video_url": "https://...",
    "profile": "high"
  }
}
```

#### 2. Reintentar Según el Estado

| Estado de Error | Estrategia de Recuperación | Endpoint |
|----------------|---------------------------|----------|
| `transcribing` | Crear nuevo workflow con mismo video | `POST /v1/autoedit/workflow` |
| `analyzing` | Volver a analizar si transcripción OK | `POST /v1/autoedit/workflow/{id}/analyze` |
| `processing` | Modificar XML y volver a procesar | `PUT /v1/autoedit/workflow/{id}/analysis` + `POST /process` |
| `generating_preview` | Reintentar preview con mismo workflow | `POST /v1/autoedit/workflow/{id}/preview` |
| `rendering` | Cambiar profile o reintentar | `POST /v1/autoedit/workflow/{id}/render` |

#### 3. Errores Comunes y Soluciones

**Transcripción:**
```json
{
  "error": "ElevenLabs API timeout",
  "stage": "transcribing"
}
```
**Solución:** Crear nuevo workflow. ElevenLabs no permite reintentar parcialmente.

**Análisis:**
```json
{
  "error": "Gemini quota exceeded",
  "stage": "analyzing"
}
```
**Solución:** Esperar límite de rate (1-60 minutos) y llamar `POST /analyze` nuevamente.

**Preview/Render:**
```json
{
  "error": "FFmpeg error: Invalid duration",
  "stage": "generating_preview"
}
```
**Solución:**
1. Verificar blocks en `GET /preview` → revisar timestamps
2. Ajustar blocks con `PATCH /blocks`
3. Reintentar `POST /preview`

#### 4. Ejemplo de Flujo de Recuperación

```javascript
async function handleWorkflowError(workflowId) {
  // 1. Obtener detalles del error
  const workflow = await fetch(`/v1/autoedit/workflow/${workflowId}`);
  const data = await workflow.json();

  if (data.status !== 'error') {
    return; // No hay error
  }

  // 2. Decidir estrategia según stage
  switch (data.error_details.stage) {
    case 'transcribing':
      console.log('Transcription failed, create new workflow');
      // Crear nuevo workflow con mismo video_url
      break;

    case 'analyzing':
      console.log('Analysis failed, retrying...');
      await fetch(`/v1/autoedit/workflow/${workflowId}/analyze`, {
        method: 'POST',
        headers: { 'X-API-Key': apiKey }
      });
      break;

    case 'generating_preview':
    case 'regenerating_preview':
      console.log('Preview failed, checking blocks...');
      const preview = await fetch(`/v1/autoedit/workflow/${workflowId}/preview`);
      const previewData = await preview.json();

      // Validar blocks antes de reintentar
      if (validateBlocks(previewData.blocks)) {
        await fetch(`/v1/autoedit/workflow/${workflowId}/preview`, {
          method: 'POST',
          headers: { 'X-API-Key': apiKey }
        });
      }
      break;

    case 'rendering':
      console.log('Render failed, trying lower profile...');
      await fetch(`/v1/autoedit/workflow/${workflowId}/render`, {
        method: 'POST',
        headers: {
          'X-API-Key': apiKey,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ profile: 'standard' }) // Bajar de 'high' a 'standard'
      });
      break;

    default:
      console.error('Unknown error stage:', data.error_details.stage);
  }
}

function validateBlocks(blocks) {
  return blocks.every(block => {
    return block.start_time < block.end_time &&
           block.start_time >= 0 &&
           block.end_time > 0;
  });
}
```

#### 5. Cloud Tasks Retries

Los Cloud Tasks tienen reintentos automáticos:

| Intento | Delay | Total Tiempo |
|---------|-------|--------------|
| 1 (original) | 0s | 0s |
| 2 (retry 1) | 60s | 60s |
| 3 (retry 2) | 120s | 180s |
| 4 (retry 3) | 240s | 420s |

Después de 3 reintentos fallidos, el workflow pasa a estado `error` permanente.

**Monitoreo de Reintentos:**
- Cloud Console → Cloud Tasks → {queue_name} → Ver task details
- Logs de Cloud Run muestran cada intento

#### 6. Estados No Recuperables

Algunos errores requieren crear un nuevo workflow:

- `transcribing` fallido → ElevenLabs no guarda estado parcial
- Workflow con TTL expirado (>24h) → Archivos temporales eliminados
- Corrupción del workflow JSON → Estado inconsistente

En estos casos:
1. Guardar `error_details` para debugging
2. Crear nuevo workflow desde cero
3. Reportar a soporte si el error es recurrente

---

## Polling Strategy

Para estados de espera, implementar polling:

```javascript
async function waitForState(workflowId, targetStates, maxWaitMs = 300000) {
  const pollIntervalMs = 2000;
  const startTime = Date.now();

  while (Date.now() - startTime < maxWaitMs) {
    const response = await fetch(`/v1/autoedit/workflow/${workflowId}`, {
      headers: { 'X-API-Key': apiKey }
    });
    const data = await response.json();

    if (targetStates.includes(data.status)) {
      return data;
    }

    if (data.status === 'error') {
      throw new Error(data.error);
    }

    await new Promise(resolve => setTimeout(resolve, pollIntervalMs));
  }

  throw new Error('Timeout waiting for state');
}

// Uso:
const result = await waitForState(workflowId, ['pending_review_1']);
```
