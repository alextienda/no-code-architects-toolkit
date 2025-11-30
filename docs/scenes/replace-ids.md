# Scene ID Replacement Endpoint

## Endpoint

`POST /v1/scenes/replace-ids`

## Description

Replaces scene IDs in JSON according to a mapping. Migrated from Media Processing Gateway.

## Authentication

Requires API key in `X-API-Key` header.

## Request Body

```json
[
  {
    "tareas_de_investigacion_identificadas": [
      {
        "idEscenaAsociada": "S01_E01",
        "nombre": "Tarea 1"
      },
      {
        "idEscenaAsociada": "S01_E02",
        "nombre": "Tarea 2"
      }
    ]
  },
  {
    "S01_E01": "recXXXXXXXXXXXX",
    "S01_E02": "recYYYYYYYYYYYY"
  }
]
```

### Parameters

- **Array with 2 elements:**
  1. **First element** (required, object): JSON with `tareas_de_investigacion_identificadas` array
     - Each task should have `idEscenaAsociada` field
  2. **Second element** (required, object): Dictionary mapping old IDs to new IDs
     - Keys: Original scene IDs (e.g., "S01_E01")
     - Values: New scene IDs (e.g., "recXXXXXXXXXXXX")

## Response

### Success (200)

```json
{
  "tareas_de_investigacion_identificadas": [
    {
      "idEscenaAsociada": "recXXXXXXXXXXXX",
      "nombre": "Tarea 1"
    },
    {
      "idEscenaAsociada": "recYYYYYYYYYYYY",
      "nombre": "Tarea 2"
    }
  ]
}
```

### Error (400/500)

```json
{
  "error": "Error message"
}
```

## Example

```bash
curl -X POST https://your-api-url/v1/scenes/replace-ids \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '[
    {
      "tareas_de_investigacion_identificadas": [
        {"idEscenaAsociada": "S01_E01", "nombre": "Tarea 1"}
      ]
    },
    {
      "S01_E01": "recXXXXXXXXXXXX"
    }
  ]'
```

## Notes

- The endpoint requires exactly 2 elements in the array
- Only tasks with `idEscenaAsociada` field will be processed
- If an ID is not found in the mapping, it will remain unchanged
- The endpoint returns the updated first JSON with replaced IDs

