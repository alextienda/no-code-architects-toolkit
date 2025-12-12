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

## Estados en Detalle

### Fase 1: Transcripción y Análisis

| Estado | Descripción | Transición |
|--------|-------------|------------|
| `created` | Workflow recién creado, esperando inicio | → `transcribing` vía POST /transcribe |
| `transcribing` | ElevenLabs procesando audio | → `transcribed` (automático) |
| `transcribed` | Transcripción lista con timestamps | → `analyzing` vía POST /analyze |
| `analyzing` | Gemini analizando contenido | → `pending_review_1` (automático) |

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

| Estado | Descripción | Transición |
|--------|-------------|------------|
| `processing` | Unified processor mapeando XML a timestamps | → `generating_preview` (automático) |

### HITL 2: Preview y Refinamiento

| Estado | Descripción | Transición |
|--------|-------------|------------|
| `generating_preview` | FFmpeg generando preview 480p | → `pending_review_2` (automático) |
| `pending_review_2` | Preview listo para revisión | → `modifying_blocks` o `rendering` |
| `modifying_blocks` | Usuario ajustando blocks | → `regenerating_preview` vía POST /preview |
| `regenerating_preview` | Regenerando preview con cambios | → `pending_review_2` (automático) |

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

| Estado | Descripción | Transición |
|--------|-------------|------------|
| `rendering` | FFmpeg procesando video final | → `completed` (automático) |
| `completed` | Video final disponible | (estado final) |

### Estado de Error

| Estado | Descripción | Recuperación |
|--------|-------------|--------------|
| `error` | Error en algún paso del proceso | Ver `error` y `error_details` en response |

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

## Tiempos Típicos por Estado

| Estado | Tiempo Típico | Factores |
|--------|---------------|----------|
| transcribing | 30-120s | Duración del video |
| analyzing | 10-60s | Cantidad de texto |
| processing | 2-10s | Complejidad del XML |
| generating_preview | 5-15s | Número de cuts, duración |
| regenerating_preview | 5-15s | Número de cuts, duración |
| rendering (standard) | 30-120s | Duración resultado |
| rendering (high) | 60-180s | Duración resultado |
| rendering (4k) | 120-300s | Duración resultado |

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
