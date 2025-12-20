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

## Fase 4B: Multi-Video Context ✅ COMPLETADO (Diciembre 2024)

### Logros
- [x] **TwelveLabs Marengo 3.0 Integration** para embeddings de video
- [x] **Context Builder** - Generación de contexto progresivo entre videos
- [x] **Redundancy Detector** - Detección de contenido similar cross-video
- [x] **Project Consolidation** - Orquestador del pipeline de consolidación
- [x] **Context API** - 8 nuevos endpoints REST
- [x] **Consolidation States** - Estados de consolidación en proyectos
- [x] **Cloud Tasks Integration** - 3 nuevos tipos de tareas

### Archivos Creados
- `services/v1/autoedit/twelvelabs_embeddings.py` - Wrapper TwelveLabs API
- `services/v1/autoedit/context_builder.py` - Generador de contexto
- `services/v1/autoedit/redundancy_detector.py` - Detector de redundancias
- `services/v1/autoedit/project_consolidation.py` - Orquestador
- `routes/v1/autoedit/context_api.py` - Endpoints REST

### Endpoints de Contexto
```
POST   /v1/autoedit/project/{id}/consolidate         - Ejecutar consolidación
GET    /v1/autoedit/project/{id}/consolidation-status - Estado de consolidación
GET    /v1/autoedit/project/{id}/redundancies        - Obtener redundancias
GET    /v1/autoedit/project/{id}/narrative           - Análisis narrativo
GET    /v1/autoedit/project/{id}/recommendations     - Recomendaciones de corte
POST   /v1/autoedit/project/{id}/apply-recommendations - Aplicar recomendaciones
PUT    /v1/autoedit/project/{id}/videos/reorder      - Reordenar videos
GET    /v1/autoedit/project/{id}/context             - Contexto acumulado
GET    /v1/autoedit/project/{id}/summaries           - Resúmenes de videos
```

### Estados de Consolidación
- `not_started` - Consolidación no iniciada
- `generating_embeddings` - Generando embeddings con TwelveLabs
- `generating_summaries` - Generando resúmenes con Gemini
- `detecting_redundancies` - Detectando redundancias cross-video
- `analyzing_narrative` - Analizando estructura narrativa
- `consolidating` - Ejecutando pipeline completo
- `consolidated` - Consolidación completa, lista para revisión
- `consolidation_complete` - Recomendaciones aplicadas
- `consolidation_failed` - Proceso falló

---

## Fase 4A: Multi-Agent Pipeline 🔄 PLANIFICADO

### Ideas
- 3 agentes especializados en cadena:
  - Agente 1: Limpieza técnica (muletillas, titubeos)
  - Agente 2: Limpieza semántica (relleno, redundancias locales)
  - Agente 3: Narrativo (storytelling, elegir "mejor versión")
- Modo configurable: rápido (1 agente) vs calidad (3 agentes)

### Prioridad: MEDIA
### ETA: Q1 2025

---

## Fase 5: AI Enhancements 🤖 FUTURO

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
