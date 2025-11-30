# Transcription Process Endpoint

## Endpoint

`POST /v1/transcription/process`

## Description

Processes transcriptions with timestamps and cuts. Migrated from Media Processing Gateway.

## Authentication

Requires API key in `X-API-Key` header.

## Request Body

```json
{
  "input_transcription": "<pt.1>\n\tst: 1000\n\twd: hello\n\ten: 1500\n</pt.1>",
  "input_agent_data": {
    "cortes": [
      {"inMs": 1000, "outMs": 2000}
    ]
  },
  "config": {
    "silence_threshold": 50,
    "padding_before": 90,
    "padding_after": 90,
    "merge_threshold": 100
  }
}
```

### Parameters

- **input_transcription** (required, string): Transcription text in XML format with `<pt>` and `<spc>` tags
- **input_agent_data** (required, object or array): Agent data with cuts
  - If object: must have `"cortes"` key with array of cuts
  - If array: will be converted to `{"cortes": [...]}`
  - Each cut should have `inMs` and `outMs` (or `timestamp`)
- **config** (optional, object): Processing configuration
  - `silence_threshold` (default: 50): Minimum silence duration in ms
  - `padding_before` (default: 90): Padding before each block in ms
  - `padding_after` (default: 90): Padding after each block in ms
  - `merge_threshold` (default: 100): Threshold to merge nearby blocks in ms

## Response

### Success (200)

```json
{
  "success": true,
  "blocks": [
    {"inMs": 1000, "outMs": 2000},
    {"inMs": 3000, "outMs": 4000}
  ],
  "processed_tokens": 150,
  "config_used": {
    "silence_threshold": 50,
    "padding_before": 90,
    "padding_after": 90,
    "merge_threshold": 100
  }
}
```

### Error (400/500)

```json
{
  "error": "Error message",
  "success": false
}
```

## Example

```bash
curl -X POST https://your-api-url/v1/transcription/process \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "input_transcription": "<pt.1>\n\tst: 1000\n\twd: hello\n\ten: 1500\n</pt.1>",
    "input_agent_data": {
      "cortes": [{"inMs": 1000, "outMs": 2000}]
    }
  }'
```

## Notes

- This endpoint uses the job queue system, so responses may be asynchronous if `webhook_url` is provided
- The endpoint accepts `input_agent_data` as either an array or a dictionary with `"cortes"` key
- Cuts can be in format `{"inMs": X, "outMs": Y}` or `{"timestamp": X}`

