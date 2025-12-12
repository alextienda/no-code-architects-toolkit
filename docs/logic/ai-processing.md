# Logic Endpoints - AI Processing

Endpoints para procesar y transformar datos para pipelines de edición de video con AI.

---

## POST /v1/logic/prepare-prompt

Convierte transcripciones de Whisper en un formato de prompt estructurado para análisis con AI (Gemini, ChatGPT, etc.).

### Request

```json
{
  "whisper_data": {
    "text": "Full transcription text...",
    "segments": [
      {
        "start": 0.0,
        "end": 2.5,
        "text": "Hola bienvenidos"
      },
      {
        "start": 2.5,
        "end": 5.0,
        "text": "al video de hoy"
      }
    ]
  }
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| whisper_data | object | ✅ | Output de transcripción de Whisper |
| whisper_data.text | string | ❌ | Texto completo de la transcripción |
| whisper_data.segments | array | ❌ | Segmentos con timestamps |
| whisper_data.srt | string | ❌ | Subtítulos en formato SRT |

### Response

```json
{
  "system_prompt_context": "[0.00-2.50]: Hola bienvenidos\n[2.50-5.00]: al video de hoy",
  "has_timestamps": true,
  "total_segments": 2,
  "total_duration_seconds": 5.0
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| system_prompt_context | string | Texto formateado para incluir en el prompt de AI |
| has_timestamps | boolean | Si el output incluye timestamps |
| total_segments | integer | Número de segmentos procesados |
| total_duration_seconds | float | Duración total del contenido |

### Uso

Este endpoint es útil para:
- Preparar transcripciones para análisis con Gemini/GPT
- Formatear segmentos con timestamps para decisiones de edición
- Normalizar diferentes formatos de transcripción

### Ejemplo cURL

```bash
curl -X POST https://api.example.com/v1/logic/prepare-prompt \
  -H "X-API-Key: tu_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "whisper_data": {
      "segments": [
        {"start": 0.0, "end": 2.5, "text": "Hola"},
        {"start": 2.5, "end": 5.0, "text": "mundo"}
      ]
    }
  }'
```

---

## POST /v1/logic/parse-ai-decision

Parsea la respuesta de un modelo AI (Gemini, GPT) y extrae segmentos de video para mantener/cortar.

### Request

```json
{
  "ai_response_text": "```json\n{\"segments\": [{\"start\": 0.0, \"end\": 5.0}, {\"start\": 10.0, \"end\": 15.0}]}\n```",
  "original_transcript": {
    "segments": [
      {"start": 0.0, "end": 20.0, "text": "..."}
    ]
  }
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| ai_response_text | string | ✅ | Respuesta cruda del modelo AI (puede incluir markdown) |
| original_transcript | object | ❌ | Transcripción original para calcular duración |

### Response

```json
{
  "video_segments": [
    {"start": 0.0, "end": 5.0},
    {"start": 10.0, "end": 15.0}
  ],
  "cuts": [
    {"start": "5.0", "end": "10.0"}
  ],
  "total_segments": 2,
  "total_kept_duration_seconds": 10.0,
  "segments_to_remove": 1
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| video_segments | array | Segmentos a MANTENER (referencia) |
| cuts | array | Segmentos a REMOVER (para `/v1/video/cut`) |
| total_segments | integer | Número de segmentos a mantener |
| total_kept_duration_seconds | float | Duración total del contenido mantenido |
| segments_to_remove | integer | Número de segmentos a remover |

### Formatos de AI Soportados

El endpoint maneja múltiples formatos de respuesta AI:

```javascript
// Formato 1: Lista directa
[{"start": 0, "end": 5}, {"start": 10, "end": 15}]

// Formato 2: Con clave "segments"
{"segments": [{"start": 0, "end": 5}]}

// Formato 3: Con clave "video_segments"
{"video_segments": [{"start": 0, "end": 5}]}

// Formato 4: Con clave "cuts"
{"cuts": [{"start": 0, "end": 5}]}

// Formato 5: Con clave "keep"
{"keep": [{"start": 0, "end": 5}]}

// Formato 6: Con markdown code blocks
"```json\n{\"segments\": [...]}\n```"
```

### Importante: Inversión de Segmentos

El endpoint `/v1/video/cut` **REMUEVE** los segmentos especificados. Por lo tanto:

- **video_segments**: Segmentos que el AI quiere MANTENER
- **cuts**: Segmentos INVERTIDOS (los gaps entre lo que se mantiene) para enviar a `/v1/video/cut`

```
Original:    |--KEEP--|----CUT----|--KEEP--|
             0s      5s          10s      15s

AI devuelve: [{start: 0, end: 5}, {start: 10, end: 15}]  (a mantener)
cuts result: [{start: "5.0", end: "10.0"}]                (a remover)
```

### Ejemplo cURL

```bash
curl -X POST https://api.example.com/v1/logic/parse-ai-decision \
  -H "X-API-Key: tu_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "ai_response_text": "{\"segments\": [{\"start\": 0, \"end\": 5}, {\"start\": 10, \"end\": 15}]}"
  }'
```

---

## Flujo de Uso Típico

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Transcribir video                                            │
│    POST /v1/media/transcribe → whisper_data                     │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Preparar prompt                                              │
│    POST /v1/logic/prepare-prompt                                │
│    Input: whisper_data                                          │
│    Output: system_prompt_context                                │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Enviar a AI (Gemini/GPT)                                     │
│    "Analiza esta transcripción y decide qué mantener:"          │
│    + system_prompt_context                                      │
│    → ai_response_text                                           │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Parsear decisión                                             │
│    POST /v1/logic/parse-ai-decision                             │
│    Input: ai_response_text                                      │
│    Output: cuts (para video/cut)                                │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Cortar video                                                 │
│    POST /v1/video/cut                                           │
│    Input: video_url + cuts                                      │
│    Output: video editado                                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Integración con AutoEdit

Estos endpoints son componentes internos del pipeline AutoEdit. Para un flujo más completo con Human-in-the-Loop, ver:

- [AutoEdit API Reference](../autoedit/API-REFERENCE.md)
- [AutoEdit Frontend Guide](../autoedit/FRONTEND-GUIDE.md)
