# Roadmap - AutoEdit Pipeline

## Fase 1: Cloud Tasks ✅ COMPLETADO (Diciembre 2024)

### Objetivos
- [x] Procesamiento asíncrono con Cloud Tasks
- [x] Almacenamiento persistente en GCS
- [x] Optimistic locking para evitar race conditions
- [x] Retry logic para eventual consistency
- [x] Soporte múltiples formatos de respuesta FFmpeg

### Beneficios Logrados
- No más timeouts HTTP en renders largos
- Escalabilidad horizontal
- Recuperación automática de fallos
- Persistencia de workflows entre reinicios

---

## Fase 2: Webhooks Mejorados 🔄 EN PROGRESO

### Objetivos
- [ ] Webhook authentication (HMAC signatures)
- [ ] Retry con exponential backoff para webhooks fallidos
- [ ] Webhook status tracking
- [ ] Multiple webhook endpoints por workflow

### Prioridad: MEDIA
### ETA: Q1 2025

---

## Fase 3: Multi-Video Projects + B-Roll Analysis ✅ COMPLETADO (Diciembre 2024)

### Logros
- [x] **ProjectManager** con CRUD completo en GCS
- [x] **9 endpoints REST** para gestión de proyectos
- [x] **Batch processing** con parallel_limit configurable
- [x] **B-Roll Analysis** con Gemini 2.5 Pro Vision via Vertex AI
- [x] **Frame extraction** con FFmpeg (1 frame/2s, max 30)
- [x] **7 categorías B-Roll**: establishing, detail, transition, ambient, action, nature, graphic
- [x] **38 tests estructurales** en `tests/test_fase3_projects_broll.py`
- [x] Documentación completa para frontend

### Archivos Creados
- `services/v1/autoedit/project.py` - ProjectManager
- `routes/v1/autoedit/project_api.py` - 9 endpoints REST
- `services/v1/autoedit/analyze_broll.py` - Análisis B-Roll
- `services/v1/autoedit/frame_extractor.py` - Extracción de frames
- `infrastructure/prompts/autoedit_broll_prompt.txt` - System prompt

### Endpoints de Proyecto
```
POST   /v1/autoedit/project              - Crear proyecto
GET    /v1/autoedit/project/{id}         - Obtener proyecto
DELETE /v1/autoedit/project/{id}         - Eliminar proyecto
GET    /v1/autoedit/projects             - Listar proyectos
POST   /v1/autoedit/project/{id}/videos  - Agregar videos
DELETE /v1/autoedit/project/{id}/videos/{wf} - Remover video
POST   /v1/autoedit/project/{id}/start   - Iniciar batch
GET    /v1/autoedit/project/{id}/stats   - Estadísticas
```

---

## Fase 4: AI Enhancements 🤖 FUTURO

### Ideas
- Auto-detection de segmentos relevantes
- Smart cut suggestions basadas en contenido
- Audio normalization automático
- Speaker diarization en transcripción

### Prioridad: EXPLORATORIA
### ETA: TBD

---

## Contribuciones

¿Tienes ideas para el roadmap? Abre un issue en GitHub o contacta al equipo de desarrollo.
