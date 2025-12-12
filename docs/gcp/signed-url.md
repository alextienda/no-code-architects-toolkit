# GCP Signed URLs

Endpoints para generar URLs firmadas que permiten subir y descargar archivos directamente a/desde Google Cloud Storage.

## POST /v1/gcp/signed-upload-url

Genera una URL firmada para subir archivos directamente a GCS desde el frontend.

### Request

```json
{
  "filename": "video.mp4",
  "content_type": "video/mp4",
  "expiration_minutes": 15,
  "folder": "uploads/user123"
}
```

| Campo | Tipo | Requerido | Default | Descripción |
|-------|------|-----------|---------|-------------|
| filename | string | ✅ | - | Nombre del archivo |
| content_type | string | ❌ | video/mp4 | MIME type del archivo |
| expiration_minutes | integer | ❌ | 15 | Minutos de validez (1-60) |
| folder | string | ❌ | - | Carpeta/prefijo para el archivo |

### Response

```json
{
  "upload_url": "https://storage.googleapis.com/bucket/path?X-Goog-Signature=...",
  "public_url": "https://storage.googleapis.com/bucket/uploads/user123/video.mp4",
  "filename": "video.mp4",
  "blob_path": "uploads/user123/video.mp4",
  "bucket": "nca-toolkit-autoedit",
  "content_type": "video/mp4",
  "expires_in_minutes": 15,
  "method": "PUT",
  "headers_required": {
    "Content-Type": "video/mp4"
  }
}
```

### Uso desde Frontend (JavaScript)

```javascript
// 1. Obtener URL firmada del backend
const response = await fetch(`${NCA_TOOLKIT_URL}/v1/gcp/signed-upload-url`, {
  method: 'POST',
  headers: {
    'X-API-Key': NCA_API_KEY,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    filename: file.name,
    content_type: file.type,
    folder: `autoedit/${userId}`
  })
});

const { upload_url, public_url, headers_required } = await response.json();

// 2. Subir archivo directamente a GCS
const uploadResponse = await fetch(upload_url, {
  method: 'PUT',
  headers: headers_required,
  body: file  // File object del input
});

if (uploadResponse.ok) {
  console.log('Archivo subido a:', public_url);

  // 3. Usar public_url para crear workflow
  const workflowResponse = await fetch(`${NCA_TOOLKIT_URL}/v1/autoedit/workflow`, {
    method: 'POST',
    headers: {
      'X-API-Key': NCA_API_KEY,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      video_url: public_url
    })
  });
}
```

### Uso con Progress (XMLHttpRequest)

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
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        reject(new Error(`Upload failed: ${xhr.status}`));
      }
    });

    xhr.addEventListener('error', () => reject(new Error('Upload failed')));

    xhr.open('PUT', uploadUrl);
    xhr.setRequestHeader('Content-Type', contentType);
    xhr.send(file);
  });
}

// Uso
uploadWithProgress(file, upload_url, content_type, (percent) => {
  console.log(`Progreso: ${percent.toFixed(1)}%`);
});
```

### Flujo Completo

```
Frontend                         NCA Toolkit                      GCS
   │                                │                               │
   ├─── POST /signed-upload-url ───►│                               │
   │    {filename, content_type}    │                               │
   │                                ├── Genera signed URL ──────────►
   │◄── {upload_url, public_url} ───┤                               │
   │                                                                │
   ├───────────── PUT file ─────────────────────────────────────────►│
   │              (directo a GCS)                                   │
   │◄──────────── 200 OK ───────────────────────────────────────────┤
   │                                                                │
   ├─── POST /autoedit/workflow ───►│                               │
   │    {video_url: public_url}     │                               │
   │◄── {workflow_id} ──────────────┤                               │
```

---

## POST /v1/gcp/signed-download-url

Genera una URL firmada para descargar archivos privados de GCS.

### Request

```json
{
  "blob_path": "uploads/user123/video.mp4",
  "expiration_minutes": 60
}
```

| Campo | Tipo | Requerido | Default | Descripción |
|-------|------|-----------|---------|-------------|
| blob_path | string | ✅ | - | Ruta al archivo en el bucket |
| expiration_minutes | integer | ❌ | 60 | Minutos de validez (1-1440) |

### Response

```json
{
  "download_url": "https://storage.googleapis.com/bucket/path?X-Goog-Signature=...",
  "blob_path": "uploads/user123/video.mp4",
  "bucket": "nca-toolkit-autoedit",
  "expires_in_minutes": 60
}
```

---

## Content Types Comunes

| Tipo de archivo | content_type |
|-----------------|--------------|
| Video MP4 | video/mp4 |
| Video WebM | video/webm |
| Video MOV | video/quicktime |
| Audio MP3 | audio/mpeg |
| Audio WAV | audio/wav |
| Imagen PNG | image/png |
| Imagen JPEG | image/jpeg |

---

## Consideraciones de Seguridad

1. **Expiración**: Las URLs tienen tiempo de expiración limitado (default 15 min para upload)
2. **Content-Type**: El archivo subido DEBE coincidir con el content_type especificado
3. **Autenticación**: El endpoint requiere X-API-Key válida
4. **Bucket**: Las URLs solo funcionan para el bucket configurado en el backend

---

## Errores Comunes

| Código | Error | Causa |
|--------|-------|-------|
| 400 | "filename is required" | Falta el campo filename |
| 400 | "GCP_BUCKET_NAME not set" | Backend no tiene bucket configurado |
| 403 | SignatureDoesNotMatch | Content-Type no coincide al subir |
| 403 | AccessDenied | URL expirada |
| 500 | "Failed to create GCS client" | Credenciales GCP inválidas |
