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

## Fase 3: Multi-Video Support 📋 PLANIFICADO

### Objetivos
- [ ] Workflows con múltiples videos de entrada
- [ ] Timeline unificado multi-source
- [ ] Transiciones entre videos
- [ ] Audio mixing de múltiples fuentes

### Prioridad: BAJA
### ETA: Q2 2025

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
