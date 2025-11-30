# Unified Processor Endpoint

## Endpoint

`POST /v1/transcription/unified-processor`

## Description

Unified processor that combines XML processing and transcription processing in a single call. Migrated from Media Processing Gateway.

## Authentication

Requires API key in `X-API-Key` header.

## Request Body

```json
{
  "xml_string": "<resultado><mantener>hello world</mantener></resultado>",
  "transcript": [
    {"inMs": 1000, "outMs": 1500, "text": "hello"},
    {"inMs": 1500, "outMs": 2000, "text": "world"}
  ],
  "input_transcription": "<pt.1>\n\tst: 1000\n\twd: hello\n\ten: 2000\n</pt.1>",
  "config": {
    "silence_threshold": 50,
    "padding_before": 90,
    "padding_after": 90,
    "merge_threshold": 100
  }
}
```

### Parameters

- **xml_string** (required, string): XML string with `<mantener>` tags
- **transcript** (required, array or object or string): Transcript items with timestamps
- **input_transcription** (optional, string): Transcription text in XML format for additional processing
- **config** (optional, object): Processing configuration (same as `/v1/transcription/process`)

## Response

### Success (200)

If `input_transcription` is provided:

```json
{
  "success": true,
  "xml_result": {
    "cortes": [
      {"inMs": 1000, "outMs": 2000, "text": "hello world"}
    ],
    "status": "success"
  },
  "blocks": [
    {"inMs": 1000, "outMs": 2000}
  ],
  "processed_tokens": 50,
  "config_used": {
    "silence_threshold": 50,
    "padding_before": 90,
    "padding_after": 90,
    "merge_threshold": 100
  }
}
```

If `input_transcription` is not provided:

```json
{
  "cortes": [
    {"inMs": 1000, "outMs": 2000, "text": "hello world"}
  ],
  "status": "success"
}
```

## Example

```bash
curl -X POST https://your-api-url/v1/transcription/unified-processor \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "xml_string": "<resultado><mantener>hello world</mantener></resultado>",
    "transcript": [
      {"inMs": 1000, "outMs": 1500, "text": "hello"},
      {"inMs": 1500, "outMs": 2000, "text": "world"}
    ],
    "input_transcription": "<pt.1>\n\tst: 1000\n\twd: hello\n\ten: 2000\n</pt.1>"
  }'
```

## Notes

- This endpoint performs two steps:
  1. Processes XML to find segments in transcript (same as `/v1/transcription/xml-processor`)
  2. If `input_transcription` is provided, processes it with the found cuts (same as `/v1/transcription/process`)
- Useful for complete workflows that need both XML processing and transcription refinement

