# Changelog - AutoEdit Pipeline

All notable changes to the AutoEdit pipeline will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.1] - 2025-12-19 - Workflow Filtering for Project Start

### Added
- **Workflow Filtering**: Parametros opcionales para controlar que workflows procesar
  - `workflow_ids`: Array opcional de IDs especificos a procesar
  - `include_failed`: Boolean para incluir workflows con status "error" (retry)

- **Enhanced Response**: Respuesta mejorada con detalles de filtrado
  - `skipped_count`: Numero de workflows omitidos
  - `skipped_by_status`: Desglose de workflows omitidos por status
  - `invalid_workflow_ids`: IDs que no pertenecen al proyecto

### Changed
- `POST /v1/autoedit/project/{id}/start`: Nuevos parametros opcionales
  - Backward compatible: sin parametros nuevos, comportamiento identico
  - Frontend puede especificar exactamente que videos procesar
  - Respuesta incluye razon por la que workflows fueron omitidos

### Technical Details
- Solo workflows con status "created" son procesados por defecto
- Con `include_failed=true`, tambien procesa status "error"
- Validacion de que `workflow_ids` pertenezcan al proyecto
- 22 tests estructurales en `tests/test_workflow_filtering.py`

---

## [1.4.0] - 2025-12-19 - Fase 4B: Multi-Video Context & Consolidation

### Added
- **TwelveLabs Marengo 3.0 Integration**: Video embeddings para similitud visual cross-video
  - `services/v1/autoedit/twelvelabs_embeddings.py`: Wrapper para TwelveLabs API
  - Soporte para embeddings síncronos y asíncronos
  - Caché local de embeddings en GCS

- **Context Builder**: Sistema de contexto progresivo entre videos
  - `services/v1/autoedit/context_builder.py`: Generador de contexto para análisis
  - Resúmenes semánticos de cada video con Gemini
  - Contexto acumulado para mejorar análisis de videos posteriores
  - Tracking de temas cubiertos, entidades introducidas, funciones narrativas

- **Redundancy Detector**: Detección de contenido similar cross-video
  - `services/v1/autoedit/redundancy_detector.py`: Comparación de embeddings
  - Similitud coseno con umbral configurable (default 0.85)
  - Categorización de severidad: high (>0.9), medium (>0.8), low (>0.7)
  - Generación automática de recomendaciones de corte

- **Project Consolidation**: Orquestador del pipeline de consolidación
  - `services/v1/autoedit/project_consolidation.py`: Pipeline completo
  - Análisis narrativo global (arc type, tone consistency)
  - Estados de consolidación granulares (10 estados)

- **Context API**: 9 nuevos endpoints REST
  - `routes/v1/autoedit/context_api.py`: Endpoints de contexto
  - `POST /project/{id}/consolidate` - Ejecutar consolidación
  - `GET /project/{id}/consolidation-status` - Estado de consolidación
  - `GET /project/{id}/redundancies` - Obtener redundancias
  - `GET /project/{id}/narrative` - Análisis narrativo
  - `GET /project/{id}/recommendations` - Recomendaciones de corte
  - `POST /project/{id}/apply-recommendations` - Aplicar recomendaciones
  - `PUT /project/{id}/videos/reorder` - Reordenar videos
  - `GET /project/{id}/context` - Contexto acumulado
  - `GET /project/{id}/summaries` - Resúmenes de videos

- **Cloud Tasks Integration**: 3 nuevos tipos de tareas
  - `generate_embeddings` - Generación de embeddings TwelveLabs
  - `generate_summaries` - Generación de resúmenes Gemini
  - `consolidate_project` - Pipeline de consolidación completo

- **Tests Fase 4B**: 68 tests estructurales en `tests/test_fase4b_multicontext.py`
  - Tests de estructura de código sin dependencias externas
  - Validación de funciones, imports, y configuración

### Changed
- `services/v1/autoedit/project.py`:
  - Nuevo campo `consolidation_state` para tracking de consolidación
  - Nuevo campo `consolidation_updated_at` para timestamps
- `services/v1/autoedit/task_queue.py`:
  - Nuevos task types para consolidación
  - Funciones para encolar tareas de embeddings/summaries
- `services/v1/autoedit/analyze_edit.py`:
  - Nuevo parámetro `context` para contexto multi-video
  - Prompt modificado para incluir contexto de videos anteriores

### Consolidation States
- `not_started` - Consolidación no iniciada
- `generating_embeddings` - Generando embeddings con TwelveLabs
- `generating_summaries` - Generando resúmenes con Gemini
- `detecting_redundancies` - Detectando redundancias cross-video
- `analyzing_narrative` - Analizando estructura narrativa
- `consolidating` - Ejecutando pipeline completo
- `consolidated` - Consolidación completa, lista para revisión
- `review_consolidation` - Usuario revisando recomendaciones (HITL 3)
- `applying_recommendations` - Aplicando cortes recomendados
- `consolidation_complete` - Recomendaciones aplicadas
- `consolidation_failed` - Proceso falló
- `invalidated` - Consolidación invalidada (videos modificados)

### Technical Details
- TwelveLabs API: Marengo 3.0 model para video embeddings
- Embedding dimensions: 1024 floats por video
- Cosine similarity para comparación de embeddings
- Context prompt: ~500 tokens adicionales por video procesado
- Redundancy threshold: Configurable 0.5-1.0, default 0.85

---

## [1.3.0] - 2025-12-16 - Fase 3: Multi-Video Projects + B-Roll Analysis

### Added
- **Multi-Video Projects**: Soporte para proyectos con múltiples videos
  - `services/v1/autoedit/project.py`: ProjectManager con CRUD completo
  - `routes/v1/autoedit/project_api.py`: 9 endpoints REST para gestión de proyectos
  - Almacenamiento en GCS: `gs://{bucket}/projects/{project_id}.json`
  - Batch processing con paralelización configurable
  - Estadísticas agregadas por proyecto (videos totales, completados, fallidos)

- **B-Roll Analysis con Gemini Vision**: Identificación automática de segmentos B-Roll
  - `services/v1/autoedit/frame_extractor.py`: Extracción de frames con FFmpeg
  - `services/v1/autoedit/analyze_broll.py`: Análisis visual con Gemini 2.5 Pro
  - `infrastructure/prompts/autoedit_broll_prompt.txt`: System prompt especializado
  - Categorización: establishing, detail, transition, ambient, action shots
  - Scoring de calidad (1-5): technical_quality, visual_appeal, usefulness
  - Filtrado automático: confidence >= 0.5, duration >= 2000ms

- **Nuevos Endpoints de Proyecto**:
  - `POST /v1/autoedit/project` - Crear proyecto
  - `GET /v1/autoedit/project/{id}` - Obtener proyecto
  - `DELETE /v1/autoedit/project/{id}` - Eliminar proyecto
  - `GET /v1/autoedit/projects` - Listar proyectos
  - `POST /v1/autoedit/project/{id}/videos` - Agregar videos
  - `GET /v1/autoedit/project/{id}/videos` - Listar videos
  - `DELETE /v1/autoedit/project/{id}/videos/{wf}` - Remover video
  - `POST /v1/autoedit/project/{id}/start` - Iniciar batch processing
  - `GET /v1/autoedit/project/{id}/stats` - Estadísticas

- **Nuevo Cloud Task Handler**:
  - `POST /v1/autoedit/tasks/analyze-broll` - Análisis B-Roll asíncrono

- **Campos Workflow Nuevos**:
  - `project_id`: Asociación opcional con proyecto (multi-video support)
  - `broll_segments`: Array de segmentos B-Roll identificados
  - `broll_analysis_complete`: Flag de análisis completado

- **Tests Fase 3**: 38 tests estructurales en `tests/test_fase3_projects_broll.py`
  - Tests de estructura de código
  - Validación de archivos y funciones
  - No requiere dependencias GCP para ejecutar

### Changed
- `services/v1/autoedit/workflow.py`: Agregados campos project_id, broll_segments, broll_analysis_complete
- `services/v1/autoedit/task_queue.py`: Agregado task type `analyze_broll` y función `start_project_pipeline()`
- `routes/v1/autoedit/tasks_api.py`: Agregado handler `task_analyze_broll()`

### Technical Details
- Frame extraction: 1 frame cada 2 segundos, máximo 30 frames
- Frame resize: 1280px width (aspect ratio preserved)
- Gemini Vision: Usa Vertex AI con gemini-2.5-pro
- Batch processing: Staggered task enqueueing (5s delay entre batches)
- Parallel limit: Configurable, default 3 videos simultáneos

---

## [1.2.1] - 2024-12-13

### Changed
- **Modelo Gemini actualizado**: `gemini-2.0-flash-exp` → `gemini-2.5-pro`
  - Mayor capacidad de razonamiento y mejor calidad de análisis
  - Modelo más estable y confiable para producción
- **Temperatura unificada a 0.0**: Consistencia en todas las llamadas a Gemini
  - Eliminada inconsistencia donde algunos endpoints usaban 0.1
  - Mejor reproducibilidad de resultados

### Added
- **Few-shot examples en prompt**: 4 ejemplos demostrativos para guiar al modelo
  - Ejemplo 1: Muletillas y repeticiones
  - Ejemplo 2: Autocorrección del hablante
  - Ejemplo 3: Sonido ambiente (contexto)
  - Ejemplo 4: Énfasis genuino vs relleno
- **Reglas XML estrictas**: Sección explícita para evitar tags cruzados
  - Instrucciones claras sobre formato de tags `<mantener>` y `<eliminar>`
  - Prevención de errores de XML malformado

### Fixed
- **XML malformado**: Sistema de validación y reparación automática de tags cruzados
  - `validate_xml_tags()`: Detecta tags mal cerrados
  - `repair_xml_tags()`: Repara automáticamente XML corrupto
  - Aplicado en parsing de respuesta de Gemini y combinación de bloques

---

## [1.2.0] - 2024-12-12

### Added
- **Cloud Tasks Integration**: Pipeline asíncrono orquestado por Google Cloud Tasks
  - Desacoplamiento completo de tareas para evitar timeouts en Cloud Run
  - Orquestación distribuida con tareas independientes (transcribe, analyze, process, preview, render)
  - Procesamiento paralelo y escalabilidad horizontal
- **GCS Workflow Storage**: Workflows persistidos en GCS en lugar de /tmp efímero
  - Storage path: `gs://{bucket}/workflows/{workflow_id}.json`
  - Persistencia garantizada entre diferentes instancias de Cloud Run
  - Eliminación de dependencia en filesystem local volátil
- **Optimistic Locking**: Conditional updates con GCS generation para evitar race conditions
  - Uso de `if_generation_match` en operaciones de escritura
  - Prevención de overwrites concurrentes
  - Detección y manejo de conflictos de actualización
- **Retry Logic**: 5 reintentos con delay de 2s para eventual consistency en GCS
  - Manejo de eventual consistency en storage distribuido
  - Backoff exponencial para operaciones fallidas
  - Logs detallados de reintentos para debugging
- **Webhook Pattern**: Notificaciones push cuando cambia el estado del workflow
  - POST automático a `webhook_url` al completar cada fase
  - Payload incluye estado actualizado del workflow
  - Eliminación de necesidad de polling por parte del cliente

### Fixed
- **file_url vs output_url**: Soporte para múltiples formatos de respuesta FFmpeg
  - Compatibilidad con respuestas que usan `file_url`, `output_url`, o `url`
  - Extracción robusta de URLs en diferentes formatos de respuesta
  - Prevención de errores por campo faltante en respuesta de servicios externos
- **Race Conditions**: Resuelto problema donde analyze task no veía transcript del transcribe task
  - Implementación de retry logic con delays
  - Validación de estado del workflow antes de proceder
  - Logs mejorados para troubleshooting de timing issues

### Changed
- **Timeouts actualizados para Cloud Tasks**:
  - Transcribe: 60s (procesamiento de audio/video)
  - Analyze: 30s (análisis de transcripción)
  - Process: 30s (generación de bloques editables)
  - Preview: 120s (renderizado de preview)
  - Render: 600s (renderizado final de alta calidad)
- **Error Handling**: Mejoras en manejo de errores con estados de fallback
  - Transiciones a estado `failed` con mensaje descriptivo
  - Preservación de contexto de error en workflow state
  - Notificación de errores vía webhook cuando está configurado

### Technical Debt
- Migración de file-based workflow storage a GCS completada
- Eliminación de dependencias en `/tmp` para datos críticos
- Mejoras en observabilidad y logging de pipeline

## [1.1.0] - 2024-12-01

### Added
- **Pipeline básico funcional** (transcribe → analyze → process → preview → render)
  - Flujo completo de procesamiento de video
  - Integración con servicios de transcripción (MCP)
  - Análisis automático de contenido
  - Generación de bloques editables
- **Dos puntos HITL** (Human-in-the-Loop):
  - **HITL 1**: Revisión y edición de XML de transcripción
  - **HITL 2**: Revisión de preview y modificación de bloques
- **FFmpeg crossfade support**:
  - Transiciones suaves entre clips
  - Uso de inputs separados para video/audio
  - Soporte para múltiples tipos de transición
- **Render profiles**:
  - `preview`: 480p, CRF 30, ultrafast preset
  - `standard`: Original resolution, CRF 23, medium preset
  - `high`: Original resolution, CRF 18, slow preset
  - `4k`: Original resolution, CRF 16, slow preset

### Changed
- Workflow state machine expandida con estados de revisión
- Documentación completa de API en `docs/autoedit/API-REFERENCE.md`

## [1.0.0] - 2024-11-15

### Added
- **Versión inicial del pipeline AutoEdit**
  - Arquitectura base del sistema
  - Definición de componentes principales
- **Workflow state machine**:
  - Estados: created, transcribing, transcribed, analyzing, processing, completed, failed
  - Transiciones automáticas entre estados
  - Persistencia de estado en JSON
- **Block manipulation**:
  - `adjust`: Modificar timestamps de bloques existentes
  - `split`: Dividir un bloque en múltiples bloques
  - `merge`: Combinar bloques adyacentes
  - `delete`: Eliminar bloques del timeline
- **Preview generation**:
  - Renderizado rápido para revisión
  - Soporte para múltiples formatos de salida
  - Integración con FFmpeg para procesamiento

### Technical Details
- Flask blueprints para organización modular
- Decoradores para autenticación y validación
- Integración con cloud storage (GCS/S3)
- Sistema de logging estructurado

---

## Roadmap

### Planned for [1.3.0]
- Redis como backend opcional para workflow storage (alta disponibilidad)
- Métricas y observabilidad mejoradas (OpenTelemetry)
- Soporte para webhooks de progreso granular (percentage complete)
- API de batch processing para múltiples videos

### Under Consideration
- Soporte para templates de edición reutilizables
- ML-powered scene detection
- Automated B-roll insertion
- Multi-language transcription support
- Real-time collaboration en bloques de edición

---

## Migration Guide

### From 1.1.0 to 1.2.0

**Breaking Changes**: None. La versión 1.2.0 es backward compatible.

**Recommended Updates**:

1. **Environment Variables**: Agregar variables para Cloud Tasks (opcional):
   ```bash
   GCP_PROJECT_ID=your-project-id
   GCP_LOCATION=us-central1
   CLOUD_TASKS_QUEUE=autoedit-tasks
   ```

2. **Workflow Storage**: Los workflows nuevos se almacenan en GCS automáticamente. Workflows existentes en `/tmp` continuarán funcionando hasta su expiración (24h TTL).

3. **Webhook URLs**: Asegurar que el endpoint de webhook puede manejar múltiples notificaciones (una por cada transición de estado).

4. **Error Handling**: Revisar lógica de manejo de errores para aprovechar nuevos estados de error detallados.

### From 1.0.0 to 1.1.0

**Breaking Changes**:

1. **Response Format**: Las respuestas ahora incluyen estados HITL adicionales.
2. **Block Schema**: Campos adicionales en estructura de bloques para soportar crossfade.

**Migration Steps**:

1. Actualizar cliente para manejar nuevos estados de workflow
2. Implementar endpoints de revisión HITL en frontend
3. Ajustar timeout expectations para preview/render

---

## Support

Para reportar bugs o sugerir features:
- GitHub Issues: [Repository Issues](https://github.com/your-org/no-code-architects-toolkit/issues)
- Documentación: `docs/autoedit/`
- API Reference: `docs/autoedit/API-REFERENCE.md`
