# Guía de Integración Frontend para AutoEdit

Guía completa para desarrolladores frontend que integran con la API AutoEdit.

---

## Configuración Inicial

### Variables de Entorno (Frontend)

```javascript
// Cargar de .env o configuración de tu framework
const API_BASE_URL = process.env.NCA_TOOLKIT_URL;
const API_KEY = process.env.NCA_API_KEY;
```

> Ver archivo `.env.autoedit` en el repo del NCA Toolkit para los valores.

### Base URL

| Entorno | Base URL |
|---------|----------|
| **Producción** | `https://nca-toolkit-djwypu7xmq-uc.a.run.app` |
| Desarrollo local | `http://localhost:8080` |

### Headers Requeridos

Todas las peticiones deben incluir:

```javascript
const headers = {
  'X-API-Key': API_KEY,        // Variable de entorno API_KEY del servidor NCA
  'Content-Type': 'application/json'
};
```

---

## Subir Videos desde el Frontend

Para que el usuario pueda subir videos desde el navegador, usa URLs firmadas de GCS:

### Flujo de Upload

```
Frontend                         NCA Toolkit                      GCS
   │                                │                               │
   ├─── POST /v1/gcp/signed-upload-url ─►│                          │
   │    {filename, content_type}    │                               │
   │◄── {upload_url, public_url} ───┤                               │
   │                                                                │
   ├───────────── PUT file (directo) ───────────────────────────────►│
   │◄──────────── 200 OK ───────────────────────────────────────────┤
   │                                                                │
   ├─── POST /v1/autoedit/workflow ─►│                               │
   │    {video_url: public_url}     │                               │
```

### Ejemplo de Código

```javascript
/**
 * Sube un video a GCS y crea un workflow de AutoEdit
 */
async function uploadVideoAndCreateWorkflow(file) {
  // 1. Obtener URL firmada
  const signedUrlResponse = await fetch(`${API_BASE_URL}/v1/gcp/signed-upload-url`, {
    method: 'POST',
    headers: {
      'X-API-Key': API_KEY,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      filename: `${Date.now()}_${file.name}`,
      content_type: file.type || 'video/mp4',
      folder: 'autoedit/uploads'
    })
  });

  const { upload_url, public_url, headers_required } = await signedUrlResponse.json();

  // 2. Subir archivo directamente a GCS
  const uploadResponse = await fetch(upload_url, {
    method: 'PUT',
    headers: headers_required,
    body: file
  });

  if (!uploadResponse.ok) {
    throw new Error('Error al subir el video');
  }

  // 3. Crear workflow con la URL del video
  const workflowResponse = await fetch(`${API_BASE_URL}/v1/autoedit/workflow`, {
    method: 'POST',
    headers: {
      'X-API-Key': API_KEY,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      video_url: public_url
    })
  });

  const data = await workflowResponse.json();

  // ⚠️ IMPORTANTE: El workflow_id está en data.response.workflow_id
  // NO en data.workflow_id (que sería undefined)
  return {
    workflow_id: data.response.workflow_id,
    status: data.response.status,
    raw_response: data  // Por si necesitas acceso al response completo
  };
}
```

### Con Barra de Progreso

```javascript
function uploadWithProgress(file, uploadUrl, contentType, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) {
        const percent = (e.loaded / e.total) * 100;
        onProgress(percent);
      }
    });

    xhr.addEventListener('load', () => {
      xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`Upload failed: ${xhr.status}`));
    });

    xhr.addEventListener('error', () => reject(new Error('Upload failed')));

    xhr.open('PUT', uploadUrl);
    xhr.setRequestHeader('Content-Type', contentType);
    xhr.send(file);
  });
}
```

> Ver documentación completa en [docs/gcp/signed-url.md](../gcp/signed-url.md)

---

## Tabla de Contenidos

1. [Subir Videos desde el Frontend](#subir-videos-desde-el-frontend)
2. [Formato de Respuestas](#formato-de-respuestas)
3. [Flujo Completo del Usuario](#flujo-completo-del-usuario)
4. [Estados del Workflow](#estados-del-workflow)
5. [HITL 1: Editor de XML](#hitl-1-editor-de-xml)
6. [HITL 2: Editor de Timeline](#hitl-2-editor-de-timeline)
7. [Ejemplos de Código](#ejemplos-de-código)
8. [Manejo de Errores](#manejo-de-errores)
9. [Cloud Tasks Integration](#cloud-tasks-integration)
10. [Best Practices](#best-practices)

---

## Formato de Respuestas

### ⚠️ IMPORTANTE: Response Wrapper

Los endpoints POST/PUT/PATCH del NCA Toolkit envuelven la respuesta en un objeto wrapper.
**El `workflow_id` NO está en el nivel raíz**, sino dentro de `response`.

### Ejemplo de Response Wrapped (POST /v1/autoedit/workflow)

```json
{
  "code": 201,
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "response": {
    "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "created",
    "message": "Workflow created successfully"
  },
  "message": "success",
  "run_time": 0.045,
  "endpoint": "/v1/autoedit/workflow"
}
```

### Extracción Correcta del workflow_id

```javascript
// ✅ CORRECTO
const data = await response.json();
const workflowId = data.response.workflow_id;

// ❌ INCORRECTO - Retorna undefined
const workflowId = data.workflow_id;
```

### Función Helper Recomendada

```javascript
/**
 * Extrae datos de respuestas wrapped del NCA Toolkit
 * @param {Response} response - Fetch response
 * @returns {Object} - Datos extraídos
 */
async function parseNCAResponse(response) {
  const data = await response.json();

  // Verificar si es respuesta wrapped o directa
  if (data.response && data.code !== undefined) {
    // Response wrapped (POST, PUT, PATCH)
    if (data.code >= 400) {
      throw new Error(data.message?.error || data.message || 'Request failed');
    }
    return data.response;
  }

  // Response directa (GET, DELETE)
  if (data.error) {
    throw new Error(data.error);
  }
  return data;
}

// Uso:
const workflowData = await parseNCAResponse(response);
console.log(workflowData.workflow_id);  // Funciona para ambos tipos
```

### Tabla de Formatos por Endpoint

| Endpoint | Método | Wrapper | Cómo extraer workflow_id |
|----------|--------|---------|--------------------------|
| `/v1/autoedit/workflow` | POST | ✅ Sí | `data.response.workflow_id` |
| `/v1/autoedit/workflow/{id}` | GET | ❌ No | `data.workflow_id` |
| `/v1/autoedit/workflow/{id}` | DELETE | ❌ No | `data.workflow_id` |
| `/v1/autoedit/workflow/{id}/analysis` | GET | ❌ No | `data.workflow_id` |
| `/v1/autoedit/workflow/{id}/analysis` | PUT | ✅ Sí | `data.response.workflow_id` |
| `/v1/autoedit/workflow/{id}/process` | POST | ✅ Sí | `data.response.workflow_id` |
| `/v1/autoedit/workflow/{id}/preview` | POST | ✅ Sí | `data.response.workflow_id` |
| `/v1/autoedit/workflow/{id}/preview` | GET | ❌ No | `data.workflow_id` |
| `/v1/autoedit/workflow/{id}/blocks` | PATCH | ✅ Sí | `data.response.workflow_id` |
| `/v1/autoedit/workflow/{id}/render` | POST | ✅ Sí | `data.response.workflow_id` |
| `/v1/autoedit/workflow/{id}/result` | GET | ❌ No | `data.workflow_id` |

---

## Flujo Completo del Usuario

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  PASO 1: INICIO                                                             │
│  - Usuario sube video (URL)                                                 │
│  - Frontend llama POST /v1/autoedit/workflow                                │
│  - Obtiene workflow_id                                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PASO 2: TRANSCRIPCIÓN + ANÁLISIS                                           │
│  - Esperar estado 'pending_review_1'                                        │
│  - Polling: GET /v1/autoedit/workflow/{id}                                  │
│  - ~60-120 segundos dependiendo del video                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PASO 3: HITL 1 - REVISIÓN DE TEXTO                                         │
│  - GET /v1/autoedit/workflow/{id}/analysis                                  │
│  - Mostrar UI con texto: <mantener> normal, <eliminar> tachado/rojo         │
│  - Usuario togglea palabras/frases                                          │
│  - PUT /v1/autoedit/workflow/{id}/analysis con XML actualizado              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PASO 4: PROCESAMIENTO                                                      │
│  - POST /v1/autoedit/workflow/{id}/process                                  │
│  - Mapea decisiones a timestamps                                            │
│  - ~2-10 segundos                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PASO 5: PREVIEW                                                            │
│  - POST /v1/autoedit/workflow/{id}/preview                                  │
│  - Genera video preview low-res (480p)                                      │
│  - ~5-15 segundos                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PASO 6: HITL 2 - REFINAMIENTO CON PREVIEW                                  │
│  - GET /v1/autoedit/workflow/{id}/preview                                   │
│  - Mostrar: video player + timeline + script                                │
│  - Usuario puede:                                                           │
│    • Ajustar inicio/fin de blocks                                           │
│    • Dividir blocks                                                         │
│    • Unir blocks adyacentes                                                 │
│    • Eliminar blocks                                                        │
│    • Restaurar gaps eliminados                                              │
│  - PATCH /v1/autoedit/workflow/{id}/blocks → regenerar preview              │
│  - Repetir hasta satisfecho                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  PASO 7: RENDER FINAL                                                       │
│  - POST /v1/autoedit/workflow/{id}/render                                   │
│  - Renderiza video en alta calidad                                          │
│  - ~30-180 segundos según calidad                                           │
│  - GET /v1/autoedit/workflow/{id}/result para obtener video final           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Estados del Workflow

### Diagrama de Transiciones

```
created → transcribing → transcribed → analyzing → pending_review_1
                                                          │
                                                          ▼
                                                    xml_approved
                                                          │
                                                          ▼
                                                     processing
                                                          │
                                                          ▼
                                                generating_preview
                                                          │
                                                          ▼
              ┌────────────────────────────── pending_review_2 ◄───────────┐
              │                                       │                    │
              │                                       ▼                    │
              │                               modifying_blocks             │
              │                                       │                    │
              │                                       ▼                    │
              │                             regenerating_preview ──────────┘
              │
              ▼
          rendering → completed
```

### Acciones Disponibles por Estado

| Estado | Endpoints Habilitados | Acción del Frontend |
|--------|----------------------|---------------------|
| `created` | GET status | Iniciar transcripción |
| `transcribing` | GET status | Mostrar spinner |
| `transcribed` | GET status | Iniciar análisis |
| `analyzing` | GET status | Mostrar spinner |
| `pending_review_1` | GET/PUT analysis, POST process | **HITL 1** |
| `xml_approved` | POST process | Continuar a proceso |
| `processing` | GET status | Mostrar spinner |
| `generating_preview` | GET status | Mostrar spinner |
| `pending_review_2` | GET preview, PATCH blocks, POST preview, POST render | **HITL 2** |
| `modifying_blocks` | GET preview, PATCH blocks, POST preview, POST render | **HITL 2** |
| `regenerating_preview` | GET status | Mostrar spinner |
| `rendering` | GET render | Mostrar progreso |
| `completed` | GET result, POST rerender | Mostrar resultado |
| `error` | GET status | Mostrar error |

---

## HITL 1: Editor de XML

### Obtener XML para Revisión

```javascript
const response = await fetch(`/v1/autoedit/workflow/${workflowId}/analysis`, {
  headers: { 'X-API-Key': apiKey }
});
const data = await response.json();

// data.combined_xml contiene:
// "<resultado><mantener>hola bienvenidos</mantener><eliminar>eh um</eliminar>..."
```

### Estructura del XML

```xml
<resultado>
  <mantener>hola bienvenidos al video de hoy</mantener>
  <eliminar>eh bueno um</eliminar>
  <mantener>vamos a ver este tema interesante</mantener>
  <eliminar>este</eliminar>
  <mantener>que es muy importante</mantener>
</resultado>
```

### Renderizado de UI Recomendado

```jsx
// Componente React de ejemplo
function XMLReviewEditor({ xml, onSubmit }) {
  const [segments, setSegments] = useState([]);

  useEffect(() => {
    // Parsear XML a segmentos
    const parsed = parseXMLToSegments(xml);
    setSegments(parsed);
  }, [xml]);

  const toggleSegment = (index) => {
    setSegments(prev => prev.map((seg, i) => {
      if (i === index) {
        return {
          ...seg,
          type: seg.type === 'mantener' ? 'eliminar' : 'mantener'
        };
      }
      return seg;
    }));
  };

  return (
    <div className="xml-editor">
      {segments.map((segment, index) => (
        <span
          key={index}
          onClick={() => toggleSegment(index)}
          className={segment.type === 'eliminar' ? 'strikethrough red' : 'normal'}
          title={`Click para ${segment.type === 'mantener' ? 'eliminar' : 'mantener'}`}
        >
          {segment.text}
        </span>
      ))}

      <button onClick={() => onSubmit(segmentsToXML(segments))}>
        Aprobar y Continuar
      </button>
    </div>
  );
}
```

### Estilos CSS Recomendados

```css
.xml-editor span {
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 3px;
  transition: all 0.2s;
}

.xml-editor span.normal {
  background: transparent;
}

.xml-editor span.strikethrough {
  text-decoration: line-through;
  color: #dc3545;
  background: rgba(220, 53, 69, 0.1);
}

.xml-editor span:hover {
  background: rgba(0, 123, 255, 0.1);
}
```

### Funciones de Parseo

```javascript
function parseXMLToSegments(xmlString) {
  const segments = [];
  const regex = /<(mantener|eliminar)>([\s\S]*?)<\/\1>/g;
  let match;

  while ((match = regex.exec(xmlString)) !== null) {
    segments.push({
      type: match[1],
      text: match[2]
    });
  }

  return segments;
}

function segmentsToXML(segments) {
  const content = segments
    .map(seg => `<${seg.type}>${seg.text}</${seg.type}>`)
    .join('');
  return `<resultado>${content}</resultado>`;
}
```

### Enviar XML Actualizado

```javascript
const submitReviewedXML = async (workflowId, updatedXML) => {
  const response = await fetch(`/v1/autoedit/workflow/${workflowId}/analysis`, {
    method: 'PUT',
    headers: {
      'X-API-Key': apiKey,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ updated_xml: updatedXML })
  });

  if (response.ok) {
    // Continuar a processing
    await processToBlocks(workflowId);
  }
};
```

---

## HITL 2: Editor de Timeline

### Obtener Preview y Datos

```javascript
const getPreviewData = async (workflowId) => {
  const response = await fetch(`/v1/autoedit/workflow/${workflowId}/preview`, {
    headers: { 'X-API-Key': apiKey }
  });
  return await response.json();
};

// Response:
// {
//   "preview_url": "https://storage.../preview_480p.mp4",
//   "preview_duration_ms": 27340,
//   "blocks": [
//     {
//       "id": "b1",
//       "inMs": 300,
//       "outMs": 5720,
//       "text": "hola bienvenidos al video de hoy",
//       "preview_inMs": 0
//     },
//     ...
//   ],
//   "gaps": [
//     {
//       "id": "g1",
//       "inMs": 0,
//       "outMs": 300,
//       "reason": "silence",
//       "text": null
//     },
//     {
//       "id": "g2",
//       "inMs": 5720,
//       "outMs": 7220,
//       "reason": "filler_words",
//       "text": "eh bueno um"
//     },
//     ...
//   ],
//   "video_duration_ms": 180000,
//   "stats": {
//     "original_duration_ms": 180000,
//     "result_duration_ms": 27340,
//     "removed_duration_ms": 152660,
//     "removal_percentage": 84.8
//   }
// }
```

### Componente de Timeline

```jsx
function TimelineEditor({ blocks, gaps, videoDuration, onModify }) {
  const timelineRef = useRef(null);

  const getPositionPercent = (ms) => (ms / videoDuration) * 100;

  return (
    <div className="timeline" ref={timelineRef}>
      {/* Blocks (segmentos a mantener) */}
      {blocks.map(block => (
        <div
          key={block.id}
          className="timeline-block keep"
          style={{
            left: `${getPositionPercent(block.inMs)}%`,
            width: `${getPositionPercent(block.outMs - block.inMs)}%`
          }}
          onClick={() => goToTime(block.inMs)}
        >
          <DraggableHandle
            position="left"
            onDrag={(newMs) => onModify({
              action: 'adjust',
              block_id: block.id,
              new_inMs: newMs,
              new_outMs: block.outMs
            })}
          />
          <span className="block-text">{block.text.substring(0, 30)}...</span>
          <DraggableHandle
            position="right"
            onDrag={(newMs) => onModify({
              action: 'adjust',
              block_id: block.id,
              new_inMs: block.inMs,
              new_outMs: newMs
            })}
          />
        </div>
      ))}

      {/* Gaps (segmentos eliminados) */}
      {gaps.map(gap => (
        <div
          key={gap.id}
          className="timeline-block gap"
          style={{
            left: `${getPositionPercent(gap.inMs)}%`,
            width: `${getPositionPercent(gap.outMs - gap.inMs)}%`
          }}
          onClick={() => onModify({
            action: 'restore_gap',
            gap_id: gap.id
          })}
          title={`Click para restaurar: "${gap.text || gap.reason}"`}
        />
      ))}

      {/* Playhead */}
      <div
        className="playhead"
        style={{ left: `${getPositionPercent(currentTime)}%` }}
      />
    </div>
  );
}
```

### Estilos de Timeline

```css
.timeline {
  position: relative;
  height: 60px;
  background: #2d2d2d;
  border-radius: 4px;
  overflow: hidden;
}

.timeline-block {
  position: absolute;
  height: 100%;
  cursor: pointer;
  transition: opacity 0.2s;
}

.timeline-block.keep {
  background: linear-gradient(180deg, #4CAF50 0%, #388E3C 100%);
  border: 1px solid #2E7D32;
}

.timeline-block.gap {
  background: repeating-linear-gradient(
    45deg,
    #f44336,
    #f44336 10px,
    #d32f2f 10px,
    #d32f2f 20px
  );
  opacity: 0.5;
}

.timeline-block.gap:hover {
  opacity: 0.8;
}

.timeline-block .block-text {
  position: absolute;
  bottom: 4px;
  left: 4px;
  right: 4px;
  font-size: 10px;
  color: white;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.playhead {
  position: absolute;
  width: 2px;
  height: 100%;
  background: #FFC107;
  pointer-events: none;
  z-index: 10;
}

/* Handles para arrastrar */
.drag-handle {
  position: absolute;
  width: 8px;
  height: 100%;
  background: rgba(255,255,255,0.3);
  cursor: ew-resize;
}

.drag-handle.left { left: 0; }
.drag-handle.right { right: 0; }
```

### Acciones de Modificación

```javascript
const modifyBlocks = async (workflowId, modifications) => {
  const response = await fetch(`/v1/autoedit/workflow/${workflowId}/blocks`, {
    method: 'PATCH',
    headers: {
      'X-API-Key': apiKey,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ modifications })
  });

  const result = await response.json();

  if (result.needs_preview_regeneration) {
    // Regenerar preview para ver cambios
    await regeneratePreview(workflowId);
  }

  return result;
};

// Ejemplos de modificaciones:

// Ajustar timestamps de un block
{ action: 'adjust', block_id: 'b1', new_inMs: 350, new_outMs: 5800 }

// Dividir un block en dos
{ action: 'split', block_id: 'b2', split_at_ms: 3000 }

// Unir dos blocks adyacentes
{ action: 'merge', block_ids: ['b3', 'b4'] }

// Eliminar un block
{ action: 'delete', block_id: 'b5' }

// Restaurar un gap (convertirlo en block)
{ action: 'restore_gap', gap_id: 'g2' }
```

### Sincronización Video-Timeline

```javascript
function useVideoTimelineSync(videoRef, blocks) {
  const [currentBlockId, setCurrentBlockId] = useState(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const handleTimeUpdate = () => {
      const currentTimeMs = video.currentTime * 1000;

      // Encontrar block actual basado en preview_inMs
      const currentBlock = blocks.find(block => {
        const blockDuration = block.outMs - block.inMs;
        return currentTimeMs >= block.preview_inMs &&
               currentTimeMs < (block.preview_inMs + blockDuration);
      });

      if (currentBlock && currentBlock.id !== currentBlockId) {
        setCurrentBlockId(currentBlock.id);
        // Resaltar block en timeline y script
        highlightBlock(currentBlock.id);
      }
    };

    video.addEventListener('timeupdate', handleTimeUpdate);
    return () => video.removeEventListener('timeupdate', handleTimeUpdate);
  }, [videoRef, blocks, currentBlockId]);

  const goToBlock = (blockId) => {
    const block = blocks.find(b => b.id === blockId);
    if (block && videoRef.current) {
      videoRef.current.currentTime = block.preview_inMs / 1000;
    }
  };

  return { currentBlockId, goToBlock };
}
```

### Panel de Script Sincronizado

```jsx
function ScriptPanel({ blocks, gaps, currentBlockId, onBlockClick }) {
  return (
    <div className="script-panel">
      {blocks.map((block, index) => (
        <React.Fragment key={block.id}>
          {/* Mostrar gap anterior si existe */}
          {index > 0 && gaps.find(g =>
            g.inMs >= blocks[index - 1].outMs && g.outMs <= block.inMs
          ) && (
            <div className="gap-indicator">
              --- CORTE ({formatDuration(gap.outMs - gap.inMs)} removido) ---
            </div>
          )}

          <div
            className={`script-block ${currentBlockId === block.id ? 'active' : ''}`}
            onClick={() => onBlockClick(block.id)}
          >
            <span className="timestamp">
              [{formatTime(block.inMs)} - {formatTime(block.outMs)}]
            </span>
            <span className="text">{block.text}</span>
          </div>
        </React.Fragment>
      ))}
    </div>
  );
}
```

---

## Ejemplos de Código

### Flujo Completo (React Hook)

```javascript
function useAutoEditWorkflow(apiKey, baseUrl = '') {
  const [workflow, setWorkflow] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const headers = {
    'X-API-Key': apiKey,
    'Content-Type': 'application/json'
  };

  // 1. Crear workflow
  const createWorkflow = async (videoUrl, options = {}) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${baseUrl}/v1/autoedit/workflow`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ video_url: videoUrl, options })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      setWorkflow(data);
      return data;
    } catch (e) {
      setError(e.message);
      throw e;
    } finally {
      setLoading(false);
    }
  };

  // 2. Obtener estado
  const getStatus = async (workflowId) => {
    const response = await fetch(`${baseUrl}/v1/autoedit/workflow/${workflowId}`, {
      headers
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    setWorkflow(data);
    return data;
  };

  // 3. Polling hasta estado deseado
  const waitForStatus = async (workflowId, targetStatuses, maxWaitMs = 300000) => {
    const pollInterval = 2000;
    const startTime = Date.now();

    while (Date.now() - startTime < maxWaitMs) {
      const status = await getStatus(workflowId);

      if (targetStatuses.includes(status.status)) {
        return status;
      }

      if (status.status === 'error') {
        throw new Error(status.error || 'Workflow failed');
      }

      await new Promise(r => setTimeout(r, pollInterval));
    }

    throw new Error('Timeout waiting for status');
  };

  // 4. HITL 1 - Obtener análisis
  const getAnalysis = async (workflowId) => {
    const response = await fetch(`${baseUrl}/v1/autoedit/workflow/${workflowId}/analysis`, {
      headers
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    return data;
  };

  // 5. HITL 1 - Enviar XML revisado
  const submitAnalysis = async (workflowId, updatedXml) => {
    const response = await fetch(`${baseUrl}/v1/autoedit/workflow/${workflowId}/analysis`, {
      method: 'PUT',
      headers,
      body: JSON.stringify({ updated_xml: updatedXml })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    return data;
  };

  // 6. Procesar XML a blocks
  const processToBlocks = async (workflowId, config = {}) => {
    const response = await fetch(`${baseUrl}/v1/autoedit/workflow/${workflowId}/process`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ config })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    return data;
  };

  // 7. Generar preview
  const generatePreview = async (workflowId, quality = '480p') => {
    const response = await fetch(`${baseUrl}/v1/autoedit/workflow/${workflowId}/preview`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ quality })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    return data;
  };

  // 8. Obtener preview
  const getPreview = async (workflowId) => {
    const response = await fetch(`${baseUrl}/v1/autoedit/workflow/${workflowId}/preview`, {
      headers
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    return data;
  };

  // 9. Modificar blocks
  const modifyBlocks = async (workflowId, modifications) => {
    const response = await fetch(`${baseUrl}/v1/autoedit/workflow/${workflowId}/blocks`, {
      method: 'PATCH',
      headers,
      body: JSON.stringify({ modifications })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    return data;
  };

  // 10. Render final
  const renderFinal = async (workflowId, quality = 'high') => {
    const response = await fetch(`${baseUrl}/v1/autoedit/workflow/${workflowId}/render`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ quality })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    return data;
  };

  // 11. Obtener resultado
  const getResult = async (workflowId) => {
    const response = await fetch(`${baseUrl}/v1/autoedit/workflow/${workflowId}/result`, {
      headers
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    return data;
  };

  return {
    workflow,
    loading,
    error,
    createWorkflow,
    getStatus,
    waitForStatus,
    getAnalysis,
    submitAnalysis,
    processToBlocks,
    generatePreview,
    getPreview,
    modifyBlocks,
    renderFinal,
    getResult
  };
}
```

### Uso del Hook

```jsx
function AutoEditPage() {
  const {
    workflow,
    loading,
    error,
    createWorkflow,
    waitForStatus,
    getAnalysis,
    submitAnalysis,
    processToBlocks,
    generatePreview,
    getPreview,
    modifyBlocks,
    renderFinal,
    getResult
  } = useAutoEditWorkflow(API_KEY);

  const [step, setStep] = useState('upload');
  const [analysisXml, setAnalysisXml] = useState(null);
  const [previewData, setPreviewData] = useState(null);

  // Paso 1: Crear workflow
  const handleUpload = async (videoUrl) => {
    const wf = await createWorkflow(videoUrl);
    setStep('processing');

    // Esperar análisis
    await waitForStatus(wf.workflow_id, ['pending_review_1']);
    const analysis = await getAnalysis(wf.workflow_id);
    setAnalysisXml(analysis.combined_xml);
    setStep('hitl1');
  };

  // Paso 2: HITL 1 completado
  const handleXmlApproved = async (updatedXml) => {
    await submitAnalysis(workflow.workflow_id, updatedXml);
    setStep('processing');

    await processToBlocks(workflow.workflow_id);
    const preview = await generatePreview(workflow.workflow_id);
    setPreviewData(preview);
    setStep('hitl2');
  };

  // Paso 3: Modificar blocks
  const handleModifyBlock = async (modification) => {
    const result = await modifyBlocks(workflow.workflow_id, [modification]);
    if (result.needs_preview_regeneration) {
      const newPreview = await generatePreview(workflow.workflow_id);
      setPreviewData(newPreview);
    }
  };

  // Paso 4: Render final
  const handleApprove = async () => {
    setStep('rendering');
    await renderFinal(workflow.workflow_id, 'high');
    await waitForStatus(workflow.workflow_id, ['completed']);
    const result = await getResult(workflow.workflow_id);
    setStep('completed');
    // Mostrar video final
  };

  return (
    <div>
      {step === 'upload' && <UploadForm onUpload={handleUpload} />}
      {step === 'processing' && <LoadingSpinner message="Procesando..." />}
      {step === 'hitl1' && (
        <XMLReviewEditor
          xml={analysisXml}
          onSubmit={handleXmlApproved}
        />
      )}
      {step === 'hitl2' && previewData && (
        <PreviewEditor
          previewUrl={previewData.preview_url}
          blocks={previewData.blocks}
          gaps={previewData.gaps}
          stats={previewData.stats}
          onModify={handleModifyBlock}
          onApprove={handleApprove}
        />
      )}
      {step === 'rendering' && <LoadingSpinner message="Renderizando..." />}
      {step === 'completed' && <ResultViewer workflowId={workflow.workflow_id} />}
      {error && <ErrorMessage message={error} />}
    </div>
  );
}
```

---

## Manejo de Errores

### Códigos de Error Comunes

| Código | Significado | Acción Recomendada |
|--------|-------------|-------------------|
| 400 | Request inválido o estado incorrecto | Verificar payload y estado del workflow |
| 401 | API Key inválida | Verificar X-API-Key header |
| 404 | Workflow no encontrado | Verificar workflow_id |
| 500 | Error interno del servidor | Reintentar o contactar soporte |

### Patrón de Retry

```javascript
async function withRetry(fn, maxRetries = 3, delayMs = 1000) {
  let lastError;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;

      // No reintentar errores 4xx (excepto 429)
      if (error.status >= 400 && error.status < 500 && error.status !== 429) {
        throw error;
      }

      if (attempt < maxRetries) {
        await new Promise(r => setTimeout(r, delayMs * attempt));
      }
    }
  }

  throw lastError;
}

// Uso
const result = await withRetry(() => generatePreview(workflowId));
```

### Manejo de Estado Error

```javascript
const handleWorkflowError = (workflow) => {
  if (workflow.status === 'error') {
    // Mostrar error al usuario
    showErrorModal({
      title: 'Error en el procesamiento',
      message: workflow.error,
      details: workflow.error_details,
      actions: [
        { label: 'Reintentar', onClick: () => retryFromLastStep(workflow) },
        { label: 'Nuevo video', onClick: () => resetWorkflow() }
      ]
    });
  }
};
```

---

## Cloud Tasks Integration

### Overview

AutoEdit usa Google Cloud Tasks para procesamiento asíncrono de operaciones pesadas. Cuando el backend encola un task, el frontend debe hacer polling del estado del workflow para detectar cuándo el task ha completado.

### Task Lifecycle

```
POST /v1/autoedit/workflow/{id}/process
    │
    ├─► Backend retorna 202 con estado "task_enqueued"
    │
    ├─► Cloud Tasks ejecuta el task en background
    │
    └─► Frontend hace polling de GET /v1/autoedit/workflow/{id}
            │
            ├─► Mientras processing: continuar polling
            │
            └─► Cuando generating_preview: task completado
```

### Timeouts Recomendados por Operación

```javascript
const OPERATION_TIMEOUTS = {
  // Tiempo máximo de polling antes de mostrar error
  transcribe: 60000,      // 60s - Transcripción de audio
  analyze: 30000,         // 30s - Análisis con LLM
  process: 30000,         // 30s - Mapeo de XML a blocks
  preview: 120000,        // 120s - Generación de preview video
  render: 600000          // 600s (10min) - Render final
};

const POLLING_INTERVALS = {
  // Intervalo entre polls por operación
  transcribe: 3000,       // 3s
  analyze: 2000,          // 2s
  process: 2000,          // 2s
  preview: 3000,          // 3s
  render: 5000            // 5s
};
```

### Eventual Consistency

Después de que un Cloud Task modifica el estado del workflow, puede haber una latencia de ~2 segundos antes de que GET refleje los cambios debido a:

1. Propagación de escritura a disco
2. Caché del filesystem
3. Latencia de red en GCP

**Solución: Esperar estado específico, no solo polling inmediato**

```javascript
// ❌ INCORRECTO - Puede leer estado antiguo
await processToBlocks(workflowId);
const status = await getStatus(workflowId);  // Puede ser "processing" todavía

// ✅ CORRECTO - Esperar estado deseado con retry
await processToBlocks(workflowId);
await waitForStatus(workflowId, ['generating_preview', 'error'], {
  timeout: OPERATION_TIMEOUTS.process,
  interval: POLLING_INTERVALS.process,
  minWaitMs: 2000  // Esperar mínimo 2s antes del primer poll
});
```

### Manejo de Errores de Cloud Tasks

#### Errores Comunes

```javascript
// 1. Task encolado pero falló en ejecución
{
  "status": "error",
  "error": "Task execution failed: FFmpeg error",
  "error_details": {
    "task_id": "12345",
    "timestamp": "2025-12-12T10:30:00Z"
  }
}

// 2. Task no pudo encolarse (problema de infraestructura)
{
  "code": 500,
  "message": "Failed to enqueue task",
  "response": {
    "error": "Cloud Tasks queue unavailable"
  }
}

// 3. Task timeout (excedió tiempo máximo de ejecución)
{
  "status": "error",
  "error": "Task execution timeout",
  "error_details": {
    "max_execution_time": 600
  }
}
```

#### Detectar si un Task Falló

```javascript
/**
 * Verifica si el workflow está en estado de error
 */
function isWorkflowFailed(workflow) {
  return workflow.status === 'error';
}

/**
 * Extrae información del error
 */
function getErrorInfo(workflow) {
  if (!isWorkflowFailed(workflow)) return null;

  return {
    message: workflow.error || 'Unknown error',
    details: workflow.error_details || {},
    recoverable: isRecoverableError(workflow.error),
    suggestedAction: getSuggestedAction(workflow.error)
  };
}

function isRecoverableError(errorMessage) {
  const recoverablePatterns = [
    /timeout/i,
    /temporary/i,
    /network/i,
    /queue unavailable/i
  ];
  return recoverablePatterns.some(pattern => pattern.test(errorMessage));
}

function getSuggestedAction(errorMessage) {
  if (/timeout/i.test(errorMessage)) {
    return 'retry';
  }
  if (/invalid video/i.test(errorMessage)) {
    return 'new_video';
  }
  if (/queue unavailable/i.test(errorMessage)) {
    return 'wait_and_retry';
  }
  return 'contact_support';
}
```

#### Recovery Procedures

```javascript
/**
 * Intenta recuperar un workflow fallido
 */
async function recoverWorkflow(workflowId, currentState) {
  const errorInfo = getErrorInfo(currentState);

  switch (errorInfo.suggestedAction) {
    case 'retry':
      // Reintentar la misma operación
      return await retryLastOperation(workflowId, currentState);

    case 'wait_and_retry':
      // Esperar y reintentar (para errores de infraestructura)
      await new Promise(r => setTimeout(r, 5000));
      return await retryLastOperation(workflowId, currentState);

    case 'new_video':
      // Error irrecuperable del video, pedir nuevo upload
      throw new Error('El video no puede procesarse. Por favor sube otro video.');

    case 'contact_support':
      // Error desconocido
      throw new Error('Error del sistema. Contacta al soporte.');
  }
}

/**
 * Reintenta la última operación según el estado
 */
async function retryLastOperation(workflowId, workflow) {
  // Determinar qué operación reintentar basado en el último estado válido
  const lastState = workflow.previous_status || workflow.status;

  if (lastState === 'xml_approved') {
    return await processToBlocks(workflowId);
  }
  if (lastState === 'processing') {
    return await generatePreview(workflowId);
  }
  if (lastState === 'pending_review_2' || lastState === 'modifying_blocks') {
    return await generatePreview(workflowId);
  }
  if (lastState === 'regenerating_preview') {
    return await renderFinal(workflowId);
  }

  throw new Error('No se puede determinar la operación a reintentar');
}
```

### Webhook Integration (Opcional)

Para evitar polling constante, puedes configurar un webhook que reciba notificaciones cuando un task complete.

#### Configurar Webhook

```javascript
// Al crear el workflow, incluir webhook_url
const createWorkflowWithWebhook = async (videoUrl, webhookUrl) => {
  const response = await fetch(`${API_BASE_URL}/v1/autoedit/workflow`, {
    method: 'POST',
    headers: {
      'X-API-Key': API_KEY,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      video_url: videoUrl,
      webhook_url: webhookUrl  // Tu endpoint para recibir notificaciones
    })
  });

  return await response.json();
};
```

#### Formato del Payload del Webhook

Cuando un task completa (exitoso o fallido), el backend envía un POST a tu webhook_url:

```javascript
// POST a tu webhook_url
{
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "generating_preview",  // Nuevo estado
  "previous_status": "processing",
  "operation": "process",           // Qué operación completó
  "success": true,                  // true si exitoso, false si error
  "timestamp": "2025-12-12T10:30:45Z",
  "data": {
    // Datos específicos de la operación
    "blocks_count": 45,
    "total_duration_ms": 180000
  },
  "error": null  // Si success=false, contiene mensaje de error
}
```

#### Implementar Endpoint de Webhook

```javascript
// Backend de tu aplicación (Node.js/Express ejemplo)
app.post('/api/webhooks/autoedit', async (req, res) => {
  const { workflow_id, status, success, error, data } = req.body;

  // 1. Validar firma (opcional pero recomendado)
  // validateWebhookSignature(req);

  // 2. Actualizar estado en tu DB
  await db.workflows.update(workflow_id, {
    status,
    last_update: new Date(),
    error: error || null
  });

  // 3. Notificar al frontend vía WebSocket/SSE
  wsServer.send(workflow_id, {
    type: 'workflow_update',
    status,
    success,
    data
  });

  // 4. Responder 200 OK
  res.status(200).json({ received: true });
});
```

#### Frontend con Webhook (WebSocket)

```javascript
function useAutoEditWithWebhook(workflowId) {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Conectar a WebSocket de tu backend
    const ws = new WebSocket(`wss://yourapp.com/ws/${workflowId}`);

    ws.onmessage = (event) => {
      const update = JSON.parse(event.data);

      if (update.type === 'workflow_update') {
        setStatus(update.status);

        if (!update.success) {
          setError(update.error);
        }

        // Actualizar UI según el nuevo estado
        handleStatusChange(update.status);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      // Fallback a polling
      startPolling(workflowId);
    };

    return () => ws.close();
  }, [workflowId]);

  return { status, error };
}
```

#### Ventajas del Webhook

- Reduce carga del servidor (menos GET requests)
- Notificaciones en tiempo real
- Mejor experiencia de usuario (UX más responsive)

#### Desventajas del Webhook

- Requiere endpoint público accesible desde GCP
- Mayor complejidad de implementación
- Necesita manejo de reconexión/fallback

**Recomendación: Usar polling para MVP, migrar a webhooks en producción si el volumen de usuarios es alto.**

### Ejemplo Completo con Manejo de Errores

```javascript
/**
 * Espera a que el workflow alcance un estado deseado
 * con manejo robusto de errores y eventual consistency
 */
async function waitForStatus(workflowId, targetStatuses, options = {}) {
  const {
    timeout = 60000,
    interval = 2000,
    minWaitMs = 2000,  // Esperar mínimo antes del primer poll
    onProgress = null
  } = options;

  const startTime = Date.now();

  // Esperar mínimo antes del primer poll (eventual consistency)
  if (minWaitMs > 0) {
    await new Promise(r => setTimeout(r, minWaitMs));
  }

  let attempts = 0;
  while (Date.now() - startTime < timeout) {
    attempts++;

    try {
      const workflow = await getStatus(workflowId);

      // Verificar si alcanzó estado deseado
      if (targetStatuses.includes(workflow.status)) {
        return workflow;
      }

      // Verificar si falló
      if (workflow.status === 'error') {
        const errorInfo = getErrorInfo(workflow);

        if (errorInfo.recoverable && attempts <= 3) {
          // Reintentar operación recuperable
          console.warn(`Retrying after error: ${errorInfo.message}`);
          await recoverWorkflow(workflowId, workflow);
          // Continuar polling
        } else {
          // Error no recuperable
          throw new Error(errorInfo.message);
        }
      }

      // Callback de progreso
      if (onProgress) {
        onProgress({
          status: workflow.status,
          attempt: attempts,
          elapsedMs: Date.now() - startTime
        });
      }

    } catch (error) {
      // Error de red o parsing
      if (attempts >= 5) {
        throw new Error(`Failed to get workflow status after ${attempts} attempts: ${error.message}`);
      }
      console.warn(`Network error on attempt ${attempts}, retrying...`);
    }

    // Esperar antes del siguiente poll
    await new Promise(r => setTimeout(r, interval));
  }

  throw new Error(`Timeout waiting for status. Expected: ${targetStatuses.join(', ')}`);
}

// Uso
try {
  await processToBlocks(workflowId);

  const result = await waitForStatus(
    workflowId,
    ['generating_preview', 'error'],
    {
      timeout: OPERATION_TIMEOUTS.process,
      interval: POLLING_INTERVALS.process,
      minWaitMs: 2000,
      onProgress: ({ status, attempt, elapsedMs }) => {
        console.log(`[${attempt}] Status: ${status} (${elapsedMs}ms elapsed)`);
        updateProgressBar(elapsedMs / OPERATION_TIMEOUTS.process);
      }
    }
  );

  console.log('Process completed:', result);
} catch (error) {
  console.error('Process failed:', error);
  showErrorToUser(error.message);
}
```

## Best Practices

### 1. Polling Eficiente

```javascript
// Usar intervalos progresivos con límites por operación
const pollWithBackoff = async (fn, condition, options = {}) => {
  const { initialInterval = 1000, maxInterval = 5000, timeout = 300000 } = options;
  let interval = initialInterval;
  const startTime = Date.now();

  while (Date.now() - startTime < timeout) {
    const result = await fn();
    if (condition(result)) return result;

    await new Promise(r => setTimeout(r, interval));
    interval = Math.min(interval * 1.5, maxInterval);
  }

  throw new Error('Polling timeout');
};
```

### 2. Caché de Datos

```javascript
// Cachear preview URL para evitar re-fetches
const previewCache = new Map();

const getCachedPreview = async (workflowId) => {
  if (previewCache.has(workflowId)) {
    const cached = previewCache.get(workflowId);
    // Invalidar después de 1 hora
    if (Date.now() - cached.timestamp < 3600000) {
      return cached.data;
    }
  }

  const data = await getPreview(workflowId);
  previewCache.set(workflowId, { data, timestamp: Date.now() });
  return data;
};
```

### 3. Optimistic Updates

```javascript
// Actualizar UI inmediatamente mientras la API procesa
const handleAdjustBlock = async (blockId, newInMs, newOutMs) => {
  // Update UI immediately
  setBlocks(prev => prev.map(b =>
    b.id === blockId ? { ...b, inMs: newInMs, outMs: newOutMs } : b
  ));

  try {
    // Then sync with server
    await modifyBlocks(workflowId, [{
      action: 'adjust',
      block_id: blockId,
      new_inMs: newInMs,
      new_outMs: newOutMs
    }]);
  } catch (error) {
    // Revert on error
    setBlocks(originalBlocks);
    showError('Error al guardar cambios');
  }
};
```

### 4. Precargar Video

```javascript
// Precargar preview video mientras el usuario revisa XML
useEffect(() => {
  if (workflow?.status === 'pending_review_1') {
    // Cuando termine HITL 1, el preview ya estará listo
    prefetchVideo(`${baseUrl}/v1/autoedit/workflow/${workflow.workflow_id}/preview`);
  }
}, [workflow?.status]);
```

### 5. Accesibilidad

```jsx
// Asegurar navegación por teclado en timeline
<div
  role="slider"
  aria-label={`Block: ${block.text.substring(0, 50)}`}
  aria-valuemin={0}
  aria-valuemax={videoDuration}
  aria-valuenow={block.inMs}
  tabIndex={0}
  onKeyDown={(e) => {
    if (e.key === 'ArrowLeft') adjustBlockStart(-100);
    if (e.key === 'ArrowRight') adjustBlockStart(100);
  }}
>
  {/* Block content */}
</div>
```

---

## Recursos Adicionales

- [API Reference](./API-REFERENCE.md) - Documentación completa de endpoints
- [Workflow States](./WORKFLOW-STATES.md) - Diagrama de estados
- [MCP Integration](./MCP-INTEGRATION.md) - Integración con agentes AI
