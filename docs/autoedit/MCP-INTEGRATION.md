# Guía de Integración MCP para AutoEdit

Guía para integrar AutoEdit con Model Context Protocol (MCP), n8n, Make.com y otros sistemas de automatización.

---

## Tabla de Contenidos

1. [¿Qué es MCP?](#qué-es-mcp)
2. [Tools Disponibles](#tools-disponibles)
3. [JSON Schema por Tool](#json-schema-por-tool)
4. [Integración con n8n](#integración-con-n8n)
5. [Integración con Make.com](#integración-con-makecom)
6. [Webhook Patterns](#webhook-patterns)
7. [Modo Automático (Skip HITL)](#modo-automático-skip-hitl)
8. [Ejemplos de Agentes](#ejemplos-de-agentes)

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
      "stats": { "$ref": "#/components/Stats" }
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
      "stats": { "type": "object" }
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
      "stats": { "type": "object" }
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
      "name": "Wait for Analysis",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "method": "GET",
        "url": "={{ $env.NCA_TOOLKIT_URL }}/v1/autoedit/workflow/{{ $json.workflow_id }}",
        "headers": {
          "X-API-Key": "={{ $env.NCA_API_KEY }}"
        },
        "retry": {
          "maxRetries": 60,
          "retryInterval": 5000,
          "retryOn": [
            "={{ $json.status !== 'pending_review_1' && $json.status !== 'error' }}"
          ]
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
      "name": "Sleep 60 seconds",
      "parameters": { "seconds": 60 }
    },
    {
      "module": "http",
      "name": "Check Status",
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

    async def _wait_for_status(self, client, workflow_id, target_status):
        import asyncio
        for _ in range(120):
            resp = await client.get(
                f"{self.nca_url}/v1/autoedit/workflow/{workflow_id}",
                headers={"X-API-Key": self.api_key}
            )
            data = resp.json()
            if data["status"] == target_status:
                return
            if data["status"] == "error":
                raise Exception(data.get("error", "Unknown error"))
            await asyncio.sleep(5)
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

## Recursos Adicionales

- [API Reference](./API-REFERENCE.md) - Documentación completa de endpoints
- [Frontend Guide](./FRONTEND-GUIDE.md) - Integración con UI
- [Workflow States](./WORKFLOW-STATES.md) - Diagrama de estados
- [OpenAPI Spec](../openapi/autoedit.yaml) - Especificación formal
