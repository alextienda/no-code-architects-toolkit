# Changelog - AutoEdit Pipeline

All notable changes to the AutoEdit pipeline will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
