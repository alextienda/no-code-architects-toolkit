# XML Processor Endpoint

## Endpoint

`POST /v1/transcription/xml-processor`

## Description

Processes XML with `<mantener>` tags and finds corresponding segments in transcript with timestamps. Migrated from Media Processing Gateway.

## Authentication

Requires API key in `X-API-Key` header.

## Request Body

```json
{
  "xml_string": "<resultado><mantener>hello world</mantener><mantener>test</mantener></resultado>",
  "transcript": [
    {"inMs": 1000, "outMs": 1500, "text": "hello"},
    {"inMs": 1500, "outMs": 2000, "text": "world"},
    {"inMs": 3000, "outMs": 3500, "text": "test"}
  ]
}
```

### Parameters

- **xml_string** (required, string): XML string with `<mantener>` tags containing text to find
- **transcript** (required, array or object or string): Transcript items with timestamps
  - If array: direct array of transcript items
  - If object: can have `"json"`, `"transcript"`, or `"data"` key
  - If string: JSON string that will be parsed
- Each transcript item should have:
  - `text` (required): The word text
  - `inMs` (required): Start time in milliseconds
  - `outMs` (required): End time in milliseconds
  - `NumID` (optional): Numeric ID

## Response

### Success (200)

```json
{
  "cortes": [
    {
      "inMs": 1000,
      "outMs": 2000,
      "text": "hello world"
    },
    {
      "inMs": 3000,
      "outMs": 3500,
      "text": "test"
    }
  ],
  "status": "success"
}
```

### Error (400/500)

```json
{
  "cortes": [],
  "status": "error",
  "error": "Error message"
}
```

## Example

```bash
curl -X POST https://your-api-url/v1/transcription/xml-processor \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "xml_string": "<resultado><mantener>hello world</mantener></resultado>",
    "transcript": [
      {"inMs": 1000, "outMs": 1500, "text": "hello"},
      {"inMs": 1500, "outMs": 2000, "text": "world"}
    ]
  }'
```

## Notes

- The endpoint searches for segments sequentially, starting each search from where the previous one ended
- This ensures chronological order of results
- If a segment is not found, it will be included in results with `inMs: null, outMs: null` and an error message
- The endpoint normalizes text for comparison (lowercase, removes punctuation, handles special characters)

