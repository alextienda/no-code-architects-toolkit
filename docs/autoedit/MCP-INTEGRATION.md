# Guía de Integración MCP para AutoEdit

Guía para integrar AutoEdit con Model Context Protocol (MCP), n8n, Make.com y otros sistemas de automatización.

---

## Tabla de Contenidos

1. [¿Qué es MCP?](#qué-es-mcp)
2. [Tools Disponibles](#tools-disponibles)
3. [JSON Schema por Tool](#json-schema-por-tool)
4. [Integración con n8n](#integración-con-n8n)
5. [Integración con Make.com](#integración-con-makecom)
6. [Cloud Tasks Async Processing](#cloud-tasks-async-processing)
   - [Overview](#overview)
   - [Respuesta Cloud Tasks](#respuesta-cloud-tasks)
   - [Workflow Storage en GCS](#workflow-storage-en-gcs)
   - [Polling con Cloud Tasks](#polling-con-cloud-tasks)
   - [Manejo de Errores Cloud Tasks](#manejo-de-errores-cloud-tasks)
   - [Monitoreo de Tasks](#monitoreo-de-tasks)
7. [Webhook Patterns](#webhook-patterns)
8. [Modo Automático (Skip HITL)](#modo-automático-skip-hitl)
9. [Ejemplos de Agentes](#ejemplos-de-agentes)
10. [Best Practices para Cloud Tasks](#best-practices-para-cloud-tasks)

---

## ¿Qué es MCP?

Model Context Protocol (MCP) es un protocolo que permite a los modelos de lenguaje (LLMs) interactuar con herramientas externas de forma estructurada. AutoEdit expone sus funcionalidades como MCP tools que pueden ser invocadas por:

- **AI Agents** (Google ADK, LangChain, etc.)
- **Workflow Automation** (n8n, Make.com, Zapier)
- **Custom Integrations**

Cada tool tiene un schema JSON que define sus inputs y outputs.

---

## Tools Disponibles

### Fase 1: Transcripción y Análisis

| Tool | Descripción | Input | Output |
|------|-------------|-------|--------|
| `transcribe_video` | Transcribe video con ElevenLabs | video_url, language | workflow_id, transcript |
| `analyze_with_gemini` | Analiza con Gemini para decisiones | workflow_id, style | combined_xml, gemini_blocks |

### HITL 1: Revisión de XML

| Tool | Descripción | Input | Output |
|------|-------------|-------|--------|
| `get_analysis_for_review` | Obtiene XML para revisión | workflow_id | combined_xml, transcript_text |
| `submit_reviewed_xml` | Envía XML modificado | workflow_id, updated_xml | status: xml_approved |

### Fase 2: Procesamiento

| Tool | Descripción | Input | Output |
|------|-------------|-------|--------|
| `process_to_blocks` | Mapea XML a blocks con timestamps | workflow_id, config | blocks[], gaps[], stats |

### HITL 2: Preview y Refinamiento

| Tool | Descripción | Input | Output |
|------|-------------|-------|--------|
| `generate_preview` | Genera video preview low-res | workflow_id, quality | preview_url, blocks, gaps |
| `modify_blocks` | Modifica blocks (adjust, split, merge) | workflow_id, modifications | blocks, gaps, needs_regeneration |
| `approve_and_render` | Aprueba y renderiza final | workflow_id, quality | status: rendering |

### Fase 3: Render y Resultado

| Tool | Descripción | Input | Output |
|------|-------------|-------|--------|
| `get_render_status` | Obtiene progreso del render | workflow_id | status, progress, output_url |
| `rerender_video` | Re-renderiza con otra calidad | workflow_id, quality | status: rendering |

---

## JSON Schema por Tool

### transcribe_video

```json
{
  "name": "transcribe_video",
  "description": "Transcribe video using ElevenLabs and initiate AutoEdit workflow",
  "input_schema": {
    "type": "object",
    "required": ["video_url"],
    "properties": {
      "video_url": {
        "type": "string",
        "format": "uri",
        "description": "URL del video a procesar (GCS signed URL, HTTPS)"
      },
      "language": {
        "type": "string",
        "default": "es",
        "description": "Código de idioma (es, en, pt, etc.)"
      },
      "options": {
        "type": "object",
        "properties": {
          "style": {
            "type": "string",
            "enum": ["dynamic", "conservative", "aggressive"],
            "default": "dynamic"
          },
          "skip_hitl_1": {
            "type": "boolean",
            "default": false
          },
          "skip_hitl_2": {
            "type": "boolean",
            "default": false
          }
        }
      }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "workflow_id": { "type": "string" },
      "status": { "type": "string" },
      "transcript": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "NumID": { "type": "integer" },
            "text": { "type": "string" },
            "inMs": { "type": "integer" },
            "outMs": { "type": "integer" },
            "speaker_id": { "type": "string" }
          }
        }
      },
      "task_enqueued": {
        "type": "object",
        "description": "Cloud Tasks information (if async processing enabled)",
        "properties": {
          "success": { "type": "boolean" },
          "task_name": { "type": "string" },
          "task_type": { "type": "string", "enum": ["transcribe", "analyze", "process", "preview", "render"] },
          "workflow_id": { "type": "string" }
        }
      }
    }
  }
}
```

### analyze_with_gemini

```json
{
  "name": "analyze_with_gemini",
  "description": "Analyze transcript with Gemini to identify content to keep/remove",
  "input_schema": {
    "type": "object",
    "required": ["workflow_id"],
    "properties": {
      "workflow_id": {
        "type": "string",
        "description": "ID del workflow"
      },
      "style": {
        "type": "string",
        "enum": ["dynamic", "conservative", "aggressive"],
        "default": "dynamic",
        "description": "Estilo de edición"
      },
      "custom_prompt": {
        "type": "string",
        "description": "Prompt personalizado para Gemini (opcional)"
      }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "workflow_id": { "type": "string" },
      "combined_xml": {
        "type": "string",
        "description": "XML con tags <mantener> y <eliminar>"
      },
      "gemini_blocks": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "blockID": { "type": "string" },
            "outputXML": { "type": "string" }
          }
        }
      },
      "task_enqueued": {
        "type": "object",
        "description": "Cloud Tasks information (if async processing enabled)",
        "properties": {
          "success": { "type": "boolean" },
          "task_name": { "type": "string" },
          "task_type": { "type": "string", "enum": ["transcribe", "analyze", "process", "preview", "render"] },
          "workflow_id": { "type": "string" }
        }
      }
    }
  }
}
```

### get_analysis_for_review

```json
{
  "name": "get_analysis_for_review",
  "description": "Get Gemini XML for frontend to render and allow user edits",
  "input_schema": {
    "type": "object",
    "required": ["workflow_id"],
    "properties": {
      "workflow_id": { "type": "string" }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "workflow_id": { "type": "string" },
      "status": { "type": "string" },
      "combined_xml": { "type": "string" },
      "transcript_text": { "type": "string" }
    }
  }
}
```

### submit_reviewed_xml

```json
{
  "name": "submit_reviewed_xml",
  "description": "User submits XML after making changes (toggle mantener/eliminar)",
  "input_schema": {
    "type": "object",
    "required": ["workflow_id", "updated_xml"],
    "properties": {
      "workflow_id": { "type": "string" },
      "updated_xml": {
        "type": "string",
        "description": "XML con cambios del usuario"
      }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "workflow_id": { "type": "string" },
      "status": { "type": "string", "enum": ["xml_approved"] }
    }
  }
}
```

### process_to_blocks

```json
{
  "name": "process_to_blocks",
  "description": "Map approved XML to blocks with timestamps using unified-processor",
  "input_schema": {
    "type": "object",
    "required": ["workflow_id"],
    "properties": {
      "workflow_id": { "type": "string" },
      "config": {
        "type": "object",
        "properties": {
          "padding_before_ms": { "type": "number", "default": 90 },
          "padding_after_ms": { "type": "number", "default": 130 },
          "silence_threshold_ms": { "type": "number", "default": 50 },
          "merge_threshold_ms": { "type": "number", "default": 100 }
        }
      }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "workflow_id": { "type": "string" },
      "blocks": { "type": "array", "items": { "$ref": "#/components/Block" } },
      "gaps": { "type": "array", "items": { "$ref": "#/components/Gap" } },
      "stats": { "$ref": "#/components/Stats" },
      "task_enqueued": {
        "type": "object",
        "description": "Cloud Tasks information (if async processing enabled)",
        "properties": {
          "success": { "type": "boolean" },
          "task_name": { "type": "string" },
          "task_type": { "type": "string", "enum": ["transcribe", "analyze", "process", "preview", "render"] },
          "workflow_id": { "type": "string" }
        }
      }
    }
  }
}
```

### generate_preview

```json
{
  "name": "generate_preview",
  "description": "Generate low-res preview video for timeline review",
  "input_schema": {
    "type": "object",
    "required": ["workflow_id"],
    "properties": {
      "workflow_id": { "type": "string" },
      "quality": {
        "type": "string",
        "enum": ["480p", "720p"],
        "default": "480p"
      },
      "fade_duration": {
        "type": "number",
        "default": 0.025
      }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "workflow_id": { "type": "string" },
      "status": { "type": "string" },
      "preview_url": { "type": "string", "format": "uri" },
      "preview_duration_ms": { "type": "integer" },
      "blocks": { "type": "array" },
      "gaps": { "type": "array" },
      "stats": { "type": "object" },
      "task_enqueued": {
        "type": "object",
        "description": "Cloud Tasks information (if async processing enabled)",
        "properties": {
          "success": { "type": "boolean" },
          "task_name": { "type": "string" },
          "task_type": { "type": "string", "enum": ["transcribe", "analyze", "process", "preview", "render"] },
          "workflow_id": { "type": "string" }
        }
      }
    }
  }
}
```

### modify_blocks

```json
{
  "name": "modify_blocks",
  "description": "Adjust block timestamps, split/merge blocks, or restore gaps",
  "input_schema": {
    "type": "object",
    "required": ["workflow_id", "modifications"],
    "properties": {
      "workflow_id": { "type": "string" },
      "modifications": {
        "type": "array",
        "items": {
          "type": "object",
          "required": ["action"],
          "properties": {
            "action": {
              "type": "string",
              "enum": ["adjust", "split", "merge", "delete", "restore_gap"]
            },
            "block_id": { "type": "string" },
            "block_ids": { "type": "array", "items": { "type": "string" } },
            "gap_id": { "type": "string" },
            "gap_index": { "type": "integer" },
            "new_inMs": { "type": "integer" },
            "new_outMs": { "type": "integer" },
            "split_at_ms": { "type": "integer" }
          }
        }
      }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "workflow_id": { "type": "string" },
      "blocks": { "type": "array" },
      "gaps": { "type": "array" },
      "stats": { "type": "object" },
      "needs_preview_regeneration": { "type": "boolean" }
    }
  }
}
```

### approve_and_render

```json
{
  "name": "approve_and_render",
  "description": "Approve final blocks and start high-quality render",
  "input_schema": {
    "type": "object",
    "required": ["workflow_id"],
    "properties": {
      "workflow_id": { "type": "string" },
      "quality": {
        "type": "string",
        "enum": ["standard", "high", "4k"],
        "default": "high"
      },
      "crossfade_duration": {
        "type": "number",
        "default": 0.025
      }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "workflow_id": { "type": "string" },
      "status": { "type": "string" },
      "output_url": { "type": "string", "format": "uri" },
      "output_duration_ms": { "type": "integer" },
      "stats": { "type": "object" },
      "task_enqueued": {
        "type": "object",
        "description": "Cloud Tasks information (if async processing enabled)",
        "properties": {
          "success": { "type": "boolean" },
          "task_name": { "type": "string" },
          "task_type": { "type": "string", "enum": ["transcribe", "analyze", "process", "preview", "render"] },
          "workflow_id": { "type": "string" }
        }
      }
    }
  }
}
```

### get_render_status

```json
{
  "name": "get_render_status",
  "description": "Check render progress and get final video URL when complete",
  "input_schema": {
    "type": "object",
    "required": ["workflow_id"],
    "properties": {
      "workflow_id": { "type": "string" }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "workflow_id": { "type": "string" },
      "status": {
        "type": "string",
        "enum": ["rendering", "completed", "error"]
      },
      "progress_percent": { "type": "integer" },
      "output_url": { "type": "string", "format": "uri" },
      "error_message": { "type": "string" },
      "stats": { "type": "object" }
    }
  }
}
```

---

## Integración con n8n

### Consideraciones Cloud Tasks

Cuando AutoEdit usa Cloud Tasks para procesamiento asíncrono:

- **Polling es necesario**: Las operaciones no son inmediatas, debes hacer polling al estado del workflow
- **Timeouts apropiados**: Usa los timeouts recomendados en [Cloud Tasks Async Processing](#cloud-tasks-async-processing)
- **Retry logic**: Implementa reintentos con backoff exponencial para eventual consistency en GCS
- **Check task_enqueued**: Verifica que `task_enqueued.success === true` antes de empezar polling

### Workflow de Ejemplo

```json
{
  "name": "AutoEdit Video Processing",
  "nodes": [
    {
      "name": "Webhook Trigger",
      "type": "n8n-nodes-base.webhook",
      "parameters": {
        "path": "autoedit-trigger",
        "httpMethod": "POST"
      }
    },
    {
      "name": "Create Workflow",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "method": "POST",
        "url": "={{ $env.NCA_TOOLKIT_URL }}/v1/autoedit/workflow",
        "headers": {
          "X-API-Key": "={{ $env.NCA_API_KEY }}",
          "Content-Type": "application/json"
        },
        "body": {
          "video_url": "={{ $json.video_url }}",
          "options": {
            "language": "es",
            "style": "dynamic",
            "skip_hitl_1": true,
            "skip_hitl_2": true
          }
        }
      }
    },
    {
      "name": "Wait for Transcription",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "method": "GET",
        "url": "={{ $env.NCA_TOOLKIT_URL }}/v1/autoedit/workflow/{{ $json.workflow_id }}",
        "headers": {
          "X-API-Key": "={{ $env.NCA_API_KEY }}"
        },
        "options": {
          "retry": {
            "maxRetries": 30,
            "retryInterval": 2000,
            "retryOn": [
              "={{ $json.status === 'transcribing' }}"
            ]
          }
        }
      }
    },
    {
      "name": "Wait for Analysis",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "method": "GET",
        "url": "={{ $env.NCA_TOOLKIT_URL }}/v1/autoedit/workflow/{{ $json.workflow_id }}",
        "headers": {
          "X-API-Key": "={{ $env.NCA_API_KEY }}"
        },
        "options": {
          "retry": {
            "maxRetries": 15,
            "retryInterval": 2000,
            "retryOn": [
              "={{ $json.status === 'analyzing' }}"
            ]
          }
        }
      }
    },
    {
      "name": "Process to Blocks",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "method": "POST",
        "url": "={{ $env.NCA_TOOLKIT_URL }}/v1/autoedit/workflow/{{ $json.workflow_id }}/process",
        "headers": {
          "X-API-Key": "={{ $env.NCA_API_KEY }}",
          "Content-Type": "application/json"
        },
        "body": {
          "config": {
            "padding_before_ms": 90,
            "padding_after_ms": 130
          }
        }
      }
    },
    {
      "name": "Generate Preview",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "method": "POST",
        "url": "={{ $env.NCA_TOOLKIT_URL }}/v1/autoedit/workflow/{{ $json.workflow_id }}/preview",
        "headers": {
          "X-API-Key": "={{ $env.NCA_API_KEY }}",
          "Content-Type": "application/json"
        },
        "body": {
          "quality": "480p"
        }
      }
    },
    {
      "name": "Render Final",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "method": "POST",
        "url": "={{ $env.NCA_TOOLKIT_URL }}/v1/autoedit/workflow/{{ $json.workflow_id }}/render",
        "headers": {
          "X-API-Key": "={{ $env.NCA_API_KEY }}",
          "Content-Type": "application/json"
        },
        "body": {
          "quality": "high"
        }
      }
    },
    {
      "name": "Send Result Webhook",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "method": "POST",
        "url": "={{ $json.callback_url }}",
        "body": {
          "workflow_id": "={{ $json.workflow_id }}",
          "output_url": "={{ $json.output_url }}",
          "stats": "={{ $json.stats }}"
        }
      }
    }
  ]
}
```

### Nodos Personalizados Recomendados

Para n8n, puedes crear nodos personalizados que encapsulan los endpoints:

```javascript
// autoedit-create-workflow.node.js
module.exports = {
  description: {
    displayName: 'AutoEdit Create Workflow',
    name: 'autoEditCreateWorkflow',
    group: ['transform'],
    version: 1,
    description: 'Create a new AutoEdit workflow',
    defaults: {
      name: 'AutoEdit Create',
    },
    inputs: ['main'],
    outputs: ['main'],
    credentials: [
      {
        name: 'ncaToolkitApi',
        required: true,
      },
    ],
    properties: [
      {
        displayName: 'Video URL',
        name: 'videoUrl',
        type: 'string',
        required: true,
        default: '',
      },
      {
        displayName: 'Language',
        name: 'language',
        type: 'options',
        options: [
          { name: 'Spanish', value: 'es' },
          { name: 'English', value: 'en' },
          { name: 'Portuguese', value: 'pt' },
        ],
        default: 'es',
      },
      {
        displayName: 'Skip HITL',
        name: 'skipHitl',
        type: 'boolean',
        default: false,
        description: 'Skip human review steps',
      },
    ],
  },

  async execute() {
    const credentials = await this.getCredentials('ncaToolkitApi');
    const videoUrl = this.getNodeParameter('videoUrl', 0);
    const language = this.getNodeParameter('language', 0);
    const skipHitl = this.getNodeParameter('skipHitl', 0);

    const response = await this.helpers.request({
      method: 'POST',
      url: `${credentials.baseUrl}/v1/autoedit/workflow`,
      headers: {
        'X-API-Key': credentials.apiKey,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        video_url: videoUrl,
        options: {
          language,
          skip_hitl_1: skipHitl,
          skip_hitl_2: skipHitl,
        },
      }),
    });

    return [{ json: JSON.parse(response) }];
  },
};
```

---

## Integración con Make.com

### Consideraciones Cloud Tasks

Al usar Make.com con AutoEdit y Cloud Tasks:

- **Sleep modules**: Usa módulos Sleep entre polling checks (recomendado: 2-5s)
- **Router + Iterator**: Implementa loops condicionales para esperar estados específicos
- **Error handling**: Captura errores cuando `task_enqueued.success === false`
- **Gateway conditions**: Usa condiciones regex para detectar estados en progreso

### Scenario de Ejemplo

```json
{
  "name": "AutoEdit Full Pipeline",
  "modules": [
    {
      "module": "webhook",
      "name": "Watch for video URL",
      "parameters": {
        "hook": "autoedit_trigger"
      }
    },
    {
      "module": "http",
      "name": "Create Workflow",
      "parameters": {
        "url": "{{env.NCA_URL}}/v1/autoedit/workflow",
        "method": "POST",
        "headers": [
          { "name": "X-API-Key", "value": "{{env.NCA_API_KEY}}" },
          { "name": "Content-Type", "value": "application/json" }
        ],
        "body": {
          "video_url": "{{1.video_url}}",
          "options": {
            "skip_hitl_1": true,
            "skip_hitl_2": true
          }
        }
      }
    },
    {
      "module": "tools",
      "name": "Sleep for transcription",
      "parameters": { "seconds": 5 }
    },
    {
      "module": "http",
      "name": "Poll Transcription Status",
      "parameters": {
        "url": "{{env.NCA_URL}}/v1/autoedit/workflow/{{2.workflow_id}}",
        "method": "GET",
        "headers": [
          { "name": "X-API-Key", "value": "{{env.NCA_API_KEY}}" }
        ]
      }
    },
    {
      "module": "router",
      "name": "Check Transcription Status",
      "routes": [
        {
          "condition": "{{4.status == 'transcribing'}}",
          "modules": [
            {
              "module": "tools",
              "name": "Retry Sleep",
              "parameters": { "seconds": 2 }
            },
            {
              "module": "iterator",
              "name": "Retry Transcription Poll",
              "parameters": {
                "max_iterations": 30,
                "array": "{{ range(1, 31) }}"
              }
            }
          ]
        },
        {
          "condition": "{{4.status == 'analyzing' || 4.status == 'pending_review_1'}}",
          "modules": ["Continue to next step"]
        },
        {
          "condition": "{{4.status == 'error'}}",
          "modules": ["Error Handler"]
        }
      ]
    },
    {
      "module": "router",
      "name": "Check if ready",
      "routes": [
        {
          "condition": "{{4.status == 'pending_review_1'}}",
          "modules": ["Process", "Preview", "Render"]
        },
        {
          "condition": "{{4.status == 'error'}}",
          "modules": ["Send Error Notification"]
        },
        {
          "condition": "default",
          "modules": ["Sleep and retry"]
        }
      ]
    }
  ]
}
```

### Variables de Entorno

Configura las siguientes variables en Make.com:

```
NCA_URL=${NCA_TOOLKIT_URL}
NCA_API_KEY=${NCA_API_KEY}
```

> Ver archivo `.env.autoedit` en el repo del NCA Toolkit para los valores reales.

---

## Cloud Tasks Async Processing

### Overview

AutoEdit utiliza Google Cloud Tasks para procesamiento asíncrono de operaciones largas. Cada fase del pipeline puede ser encolada como una tarea independiente:

- **transcribe**: Transcripción de video (timeout: 60s)
- **analyze**: Análisis con Gemini (timeout: 30s)
- **process**: Mapeo XML a blocks (timeout: 30s)
- **preview**: Generación de preview (timeout: 120s)
- **render**: Renderizado final (timeout: 600s)

### Respuesta Cloud Tasks

Cuando una operación es encolada, la respuesta incluye `task_enqueued`:

```json
{
  "workflow_id": "abc-123-def",
  "status": "transcribing",
  "task_enqueued": {
    "success": true,
    "task_name": "projects/my-project/locations/us-central1/queues/autoedit-pipeline/tasks/abc-123-def-transcribe",
    "task_type": "transcribe",
    "workflow_id": "abc-123-def"
  }
}
```

**Campos:**
- `success`: `true` si la tarea fue encolada correctamente
- `task_name`: Nombre completo de la tarea en Cloud Tasks
- `task_type`: Tipo de operación (`transcribe`, `analyze`, `process`, `preview`, `render`)
- `workflow_id`: ID del workflow asociado

### Workflow Storage en GCS

Los workflows se almacenan en Google Cloud Storage:

```
gs://{GCP_BUCKET_NAME}/workflows/{workflow_id}.json
```

**Características:**
- **Optimistic Locking**: Updates condicionales usando GCS generation number
- **TTL**: 24 horas de retención
- **Retry Logic**: 5 reintentos con 2s de delay para eventual consistency

### Polling con Cloud Tasks

#### n8n Retry Loop Pattern

```json
{
  "name": "Poll Workflow Status",
  "type": "n8n-nodes-base.httpRequest",
  "parameters": {
    "method": "GET",
    "url": "={{ $env.NCA_TOOLKIT_URL }}/v1/autoedit/workflow/{{ $json.workflow_id }}",
    "headers": {
      "X-API-Key": "={{ $env.NCA_API_KEY }}"
    },
    "options": {
      "retry": {
        "maxRetries": 30,
        "retryInterval": 2000,
        "retryOn": [
          "={{ $json.status === 'transcribing' || $json.status === 'analyzing' }}"
        ]
      }
    }
  }
}
```

**Timeouts recomendados por fase:**

| Fase | Max Retries | Interval (ms) | Total Timeout |
|------|-------------|---------------|---------------|
| transcribe | 30 | 2000 | 60s |
| analyze | 15 | 2000 | 30s |
| process | 15 | 2000 | 30s |
| preview | 60 | 2000 | 120s |
| render | 300 | 2000 | 600s |

#### Make.com Iterator Pattern

```json
{
  "module": "gateway",
  "name": "Wait for Completion",
  "parameters": {
    "condition": "{{4.status}}",
    "routes": [
      {
        "label": "Still Processing",
        "condition": "transcribing|analyzing|processing|generating_preview|rendering",
        "modules": [
          {
            "module": "tools",
            "name": "Sleep",
            "parameters": { "seconds": 5 }
          },
          {
            "module": "iterator",
            "name": "Retry Check",
            "parameters": {
              "max_iterations": 120,
              "array": "{{ range(1, 121) }}"
            }
          }
        ]
      },
      {
        "label": "Completed",
        "condition": "pending_review_1|pending_review_2|completed",
        "modules": ["Next Step"]
      },
      {
        "label": "Error",
        "condition": "error",
        "modules": ["Error Handler"]
      }
    ]
  }
}
```

### Manejo de Errores Cloud Tasks

#### Cuando Cloud Tasks Falla

Si `task_enqueued.success === false`:

```json
{
  "workflow_id": "abc-123-def",
  "status": "error",
  "task_enqueued": {
    "success": false,
    "error": "Failed to enqueue task: DEADLINE_EXCEEDED"
  },
  "error": "Cloud Tasks enqueue failed"
}
```

**Estrategia de recuperación:**

1. **Verificar estado del workflow**: GET `/v1/autoedit/workflow/{workflow_id}`
2. **Reintentar operación**: Repetir el POST original
3. **Timeout progresivo**: 2s, 4s, 8s, 16s (max 30s)
4. **Notificar al usuario** si falla después de 5 reintentos

#### Ejemplo en Python (n8n Code Node)

```python
import requests
import time

def retry_with_backoff(func, max_retries=5):
    for attempt in range(max_retries):
        try:
            response = func()
            data = response.json()

            # Check if task was enqueued
            if data.get('task_enqueued', {}).get('success'):
                return data

            # Cloud Tasks failed, retry
            print(f"Task enqueue failed, attempt {attempt + 1}/{max_retries}")
            time.sleep(2 ** attempt)  # Exponential backoff

        except Exception as e:
            print(f"Request failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise

    raise Exception("Max retries exceeded")

# Usage
def create_workflow():
    return requests.post(
        f"{NCA_URL}/v1/autoedit/workflow",
        headers={"X-API-Key": API_KEY},
        json={"video_url": video_url}
    )

result = retry_with_backoff(create_workflow)
```

#### Ejemplo en JavaScript (Make.com Code Module)

```javascript
async function retryWithBackoff(operation, maxRetries = 5) {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const response = await operation();
      const data = await response.json();

      // Check if task was enqueued
      if (data?.task_enqueued?.success) {
        return data;
      }

      // Cloud Tasks failed, retry
      console.log(`Task enqueue failed, attempt ${attempt + 1}/${maxRetries}`);
      await new Promise(r => setTimeout(r, 2 ** attempt * 1000));

    } catch (error) {
      console.error(`Request failed: ${error}`);
      if (attempt < maxRetries - 1) {
        await new Promise(r => setTimeout(r, 2 ** attempt * 1000));
      } else {
        throw error;
      }
    }
  }

  throw new Error('Max retries exceeded');
}

// Usage
const result = await retryWithBackoff(() =>
  fetch(`${NCA_URL}/v1/autoedit/workflow`, {
    method: 'POST',
    headers: {
      'X-API-Key': API_KEY,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ video_url })
  })
);
```

### Monitoreo de Tasks

#### Verificar Estado de Task

```bash
# Get workflow status (includes task info if available)
curl -X GET "${NCA_TOOLKIT_URL}/v1/autoedit/workflow/${WORKFLOW_ID}" \
  -H "X-API-Key: ${NCA_API_KEY}"
```

Respuesta incluye última tarea encolada:

```json
{
  "workflow_id": "abc-123-def",
  "status": "transcribing",
  "last_task_enqueued": {
    "task_type": "transcribe",
    "task_name": "projects/.../tasks/abc-123-def-transcribe",
    "enqueued_at": "2025-01-15T10:30:00Z"
  }
}
```

---

## Webhook Patterns

### Patrón con Callback

Cuando el procesamiento toma mucho tiempo, usa el patrón de callback:

```json
{
  "video_url": "https://storage.example.com/video.mp4",
  "webhook_url": "https://your-server.com/autoedit-callback",
  "options": {
    "skip_hitl_1": true,
    "skip_hitl_2": true
  }
}
```

El sistema enviará un POST al `webhook_url` cuando el proceso termine:

```json
{
  "workflow_id": "abc123",
  "status": "completed",
  "output_url": "https://storage.example.com/output.mp4",
  "stats": {
    "original_duration_ms": 180000,
    "result_duration_ms": 27340,
    "removal_percentage": 84.8
  }
}
```

### Patrón de Polling

Para sistemas que no soportan webhooks:

```javascript
async function pollUntilComplete(workflowId, apiKey) {
  const maxAttempts = 120;
  const intervalMs = 5000;

  for (let i = 0; i < maxAttempts; i++) {
    const response = await fetch(`/v1/autoedit/workflow/${workflowId}`, {
      headers: { 'X-API-Key': apiKey }
    });
    const data = await response.json();

    if (data.status === 'completed') {
      return data;
    }

    if (data.status === 'error') {
      throw new Error(data.error);
    }

    await new Promise(r => setTimeout(r, intervalMs));
  }

  throw new Error('Timeout waiting for completion');
}
```

---

## Modo Automático (Skip HITL)

Para flujos completamente automatizados sin intervención humana:

### Crear Workflow sin HITL

```bash
curl -X POST "${NCA_TOOLKIT_URL}/v1/autoedit/workflow" \
  -H "X-API-Key: ${NCA_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "video_url": "https://storage.example.com/video.mp4",
    "options": {
      "language": "es",
      "style": "dynamic",
      "skip_hitl_1": true,
      "skip_hitl_2": true
    }
  }'
```

### Flujo Automático Completo

```javascript
async function autoEditVideo(videoUrl, apiKey) {
  // 1. Crear workflow
  const createResponse = await fetch('/v1/autoedit/workflow', {
    method: 'POST',
    headers: {
      'X-API-Key': apiKey,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      video_url: videoUrl,
      options: {
        skip_hitl_1: true,
        skip_hitl_2: true
      }
    })
  });
  const { workflow_id } = await createResponse.json();

  // 2. Esperar transcripción y análisis
  await waitForStatus(workflow_id, ['pending_review_1', 'xml_approved']);

  // 3. Procesar a blocks (automáticamente usa XML de Gemini)
  await fetch(`/v1/autoedit/workflow/${workflow_id}/process`, {
    method: 'POST',
    headers: { 'X-API-Key': apiKey, 'Content-Type': 'application/json' },
    body: JSON.stringify({})
  });

  // 4. Generar preview
  await fetch(`/v1/autoedit/workflow/${workflow_id}/preview`, {
    method: 'POST',
    headers: { 'X-API-Key': apiKey, 'Content-Type': 'application/json' },
    body: JSON.stringify({ quality: '480p' })
  });

  // 5. Render final (sin revisión)
  const renderResponse = await fetch(`/v1/autoedit/workflow/${workflow_id}/render`, {
    method: 'POST',
    headers: { 'X-API-Key': apiKey, 'Content-Type': 'application/json' },
    body: JSON.stringify({ quality: 'high' })
  });

  return await renderResponse.json();
}
```

---

## Ejemplos de Agentes

### Google ADK Agent

```python
from google.adk import Agent, Tool

class AutoEditAgent(Agent):
    """Agent para edición automática de videos."""

    def __init__(self, nca_url: str, api_key: str):
        self.nca_url = nca_url
        self.api_key = api_key

    @Tool
    async def edit_video(self, video_url: str, style: str = "dynamic") -> dict:
        """
        Edita un video automáticamente removiendo muletillas y silencios.

        Args:
            video_url: URL del video a editar
            style: Estilo de edición (dynamic, conservative, aggressive)

        Returns:
            URL del video editado y estadísticas
        """
        import httpx

        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient() as client:
            # Crear workflow
            create_resp = await client.post(
                f"{self.nca_url}/v1/autoedit/workflow",
                headers=headers,
                json={
                    "video_url": video_url,
                    "options": {
                        "style": style,
                        "skip_hitl_1": True,
                        "skip_hitl_2": True
                    }
                }
            )
            workflow_id = create_resp.json()["workflow_id"]

            # Esperar y procesar
            await self._wait_for_status(client, workflow_id, "pending_review_1")

            await client.post(
                f"{self.nca_url}/v1/autoedit/workflow/{workflow_id}/process",
                headers=headers,
                json={}
            )

            await client.post(
                f"{self.nca_url}/v1/autoedit/workflow/{workflow_id}/preview",
                headers=headers,
                json={"quality": "480p"}
            )

            result = await client.post(
                f"{self.nca_url}/v1/autoedit/workflow/{workflow_id}/render",
                headers=headers,
                json={"quality": "high"}
            )

            return result.json()

    async def _wait_for_status(self, client, workflow_id, target_status, timeout_seconds=300):
        """
        Wait for workflow to reach target status with configurable timeout.

        Args:
            client: HTTP client
            workflow_id: Workflow ID
            target_status: Target status to wait for
            timeout_seconds: Max wait time (default: 300s for Cloud Tasks)
        """
        import asyncio
        max_attempts = timeout_seconds // 2  # Poll every 2 seconds

        for attempt in range(max_attempts):
            try:
                resp = await client.get(
                    f"{self.nca_url}/v1/autoedit/workflow/{workflow_id}",
                    headers={"X-API-Key": self.api_key}
                )
                data = resp.json()

                if data["status"] == target_status:
                    return data

                if data["status"] == "error":
                    error_msg = data.get("error", "Unknown error")
                    raise Exception(f"Workflow failed: {error_msg}")

                # Check if Cloud Tasks is processing
                if data.get("task_enqueued"):
                    print(f"Cloud Task {data['task_enqueued']['task_type']} processing...")

                await asyncio.sleep(2)

            except Exception as e:
                if attempt < max_attempts - 1:
                    await asyncio.sleep(2)
                else:
                    raise

        raise TimeoutError(f"Timeout waiting for status '{target_status}' after {timeout_seconds}s")
```

### LangChain Tool

```python
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
import requests

class AutoEditInput(BaseModel):
    video_url: str = Field(description="URL del video a editar")
    style: str = Field(default="dynamic", description="Estilo: dynamic, conservative, aggressive")

class AutoEditTool(BaseTool):
    name = "auto_edit_video"
    description = "Edita un video automáticamente removiendo muletillas, silencios y contenido irrelevante"
    args_schema = AutoEditInput

    def __init__(self, nca_url: str, api_key: str):
        super().__init__()
        self.nca_url = nca_url
        self.api_key = api_key

    def _run(self, video_url: str, style: str = "dynamic") -> str:
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }

        # Crear workflow con skip_hitl
        resp = requests.post(
            f"{self.nca_url}/v1/autoedit/workflow",
            headers=headers,
            json={
                "video_url": video_url,
                "options": {
                    "style": style,
                    "skip_hitl_1": True,
                    "skip_hitl_2": True
                }
            }
        )
        workflow_id = resp.json()["workflow_id"]

        # ... (polling y procesamiento)

        return f"Video editado: {output_url}"
```

---

## Best Practices para Cloud Tasks

### 1. Siempre Verificar task_enqueued

```javascript
// ✅ CORRECTO
const response = await createWorkflow(videoUrl);
if (!response.task_enqueued?.success) {
  console.error('Task enqueue failed:', response.task_enqueued?.error);
  // Retry o notificar error
  throw new Error('Failed to enqueue task');
}

// ❌ INCORRECTO - No verificar
const response = await createWorkflow(videoUrl);
// Asume que siempre fue exitoso
```

### 2. Implementar Timeouts Apropiados

```javascript
// ✅ CORRECTO - Timeouts por fase
const TIMEOUTS = {
  transcribe: 60,
  analyze: 30,
  process: 30,
  preview: 120,
  render: 600
};

await pollWithTimeout(workflowId, 'pending_review_1', TIMEOUTS.analyze);

// ❌ INCORRECTO - Timeout genérico
await pollWithTimeout(workflowId, 'pending_review_1', 300); // Muy largo
```

### 3. Manejar Eventual Consistency en GCS

```python
# ✅ CORRECTO - Retry con backoff
def get_workflow_with_retry(workflow_id, max_retries=5):
    for attempt in range(max_retries):
        try:
            workflow = get_workflow(workflow_id)
            if workflow.get('status'):  # Verificar que tenga datos válidos
                return workflow
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                raise
    return None

# ❌ INCORRECTO - Una sola petición
workflow = get_workflow(workflow_id)  # Puede fallar por eventual consistency
```

### 4. Usar Estados Correctos para Polling

```javascript
// ✅ CORRECTO - Esperar estados específicos
const PROCESSING_STATES = ['transcribing', 'analyzing', 'processing', 'generating_preview', 'rendering'];
const READY_STATES = ['pending_review_1', 'pending_review_2', 'completed'];
const ERROR_STATE = 'error';

while (PROCESSING_STATES.includes(workflow.status)) {
  await sleep(2000);
  workflow = await getWorkflow(workflowId);
}

// ❌ INCORRECTO - Polling sin fin
while (workflow.status !== 'completed') {
  await sleep(5000);
  workflow = await getWorkflow(workflowId);
}
```

### 5. Log de Cloud Tasks para Debugging

```python
# ✅ CORRECTO - Log información de tasks
response = create_workflow(video_url)
if response.get('task_enqueued'):
    logger.info(
        f"Task enqueued: {response['task_enqueued']['task_type']}",
        extra={
            'workflow_id': response['workflow_id'],
            'task_name': response['task_enqueued']['task_name']
        }
    )

# ❌ INCORRECTO - No loggear
response = create_workflow(video_url)
# No hay trace de qué task se encoló
```

### 6. Timeout Progresivo en n8n/Make

```json
{
  "name": "Progressive Timeout Polling",
  "steps": [
    {
      "name": "Initial Quick Poll",
      "retry": { "maxRetries": 5, "interval": 1000 }
    },
    {
      "name": "Medium Poll",
      "retry": { "maxRetries": 10, "interval": 2000 }
    },
    {
      "name": "Slow Poll",
      "retry": { "maxRetries": 20, "interval": 5000 }
    }
  ]
}
```

### 7. Manejo de Errores Granular

```javascript
// ✅ CORRECTO - Manejar diferentes tipos de error
try {
  const response = await createWorkflow(videoUrl);

  if (!response.task_enqueued?.success) {
    // Error de enqueue
    throw new TaskEnqueueError(response.task_enqueued?.error);
  }

  const result = await pollWorkflow(response.workflow_id);

  if (result.status === 'error') {
    // Error de procesamiento
    throw new WorkflowProcessingError(result.error);
  }

} catch (error) {
  if (error instanceof TaskEnqueueError) {
    // Retry con backoff
    return retryWithBackoff(() => createWorkflow(videoUrl));
  } else if (error instanceof WorkflowProcessingError) {
    // Notificar al usuario
    notifyUser(error.message);
  } else if (error instanceof TimeoutError) {
    // Timeout - verificar estado y decidir
    const status = await getWorkflowStatus(workflowId);
    if (status.status === 'rendering') {
      // Continuar esperando
      return pollWorkflow(workflowId, { timeout: 600 });
    }
  }
}

// ❌ INCORRECTO - Catch genérico
try {
  await createWorkflow(videoUrl);
} catch (error) {
  console.error('Error:', error);
  // No hay diferenciación de tipos de error
}
```

---

## Recursos Adicionales

- [API Reference](./API-REFERENCE.md) - Documentación completa de endpoints
- [Frontend Guide](./FRONTEND-GUIDE.md) - Integración con UI
- [Workflow States](./WORKFLOW-STATES.md) - Diagrama de estados
- [OpenAPI Spec](../openapi/autoedit.yaml) - Especificación formal
