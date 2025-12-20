# B-Roll Integration Guide

> **Guía para frontend:** Integración del análisis visual de B-Roll.

## ¿Qué es B-Roll?

**B-Roll** son segmentos de video sin diálogo principal - tomas de apoyo:

| Categoría | Descripción | Uso Típico |
|-----------|-------------|------------|
| `establishing_shot` | Tomas amplias de ubicación | Inicio de secciones |
| `detail_shot` | Primer plano de objetos | Énfasis en productos |
| `transition_shot` | Tomas neutrales | Entre segmentos |
| `ambient_shot` | Ambiente, paisajes | Relleno visual |
| `action_shot` | Acciones sin diálogo | Demostraciones |
| `nature_shot` | Naturaleza, exteriores | B-Roll genérico |
| `graphic_overlay` | Gráficos, texto | Títulos, lower thirds |

## Cómo Funciona

```
Video → FFmpeg extrae frames → Gemini Vision analiza → JSON con segmentos B-Roll
         (1 frame/2sec)         (identifica categorías)
```

El análisis usa **Gemini 2.5 Pro Vision** para identificar automáticamente segmentos B-Roll.

---

## Obtener Datos de B-Roll

Los datos están disponibles en el workflow después del análisis:

```javascript
const response = await fetch(`/v1/autoedit/workflow/${workflowId}`, {
  headers: { 'X-API-Key': API_KEY }
});
const workflow = (await response.json()).response;

const brollSegments = workflow.broll_segments || [];
const brollComplete = workflow.broll_analysis_complete || false;
```

---

## Estructura de Segmento B-Roll

```json
{
  "segment_id": "broll_001",
  "inMs": 5720,
  "outMs": 12450,
  "duration_ms": 6730,
  "type": "B-Roll",
  "category": "establishing_shot",
  "description": "Toma aérea de la ciudad al atardecer",
  "confidence": 0.85,
  "scores": {
    "technical_quality": 4,
    "visual_appeal": 5,
    "usefulness": 4
  },
  "potential_use": ["Establecimiento", "Transición"]
}
```

### Campos Principales

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `segment_id` | string | ID único del segmento |
| `inMs` / `outMs` | number | Inicio/fin en milisegundos |
| `category` | string | Tipo de B-Roll (ver tabla arriba) |
| `description` | string | Descripción generada por Gemini |
| `confidence` | number | Confianza del análisis (0-1) |
| `scores` | object | Calidad técnica, visual, utilidad (1-5) |

---

## Integración UI

### Timeline Multi-Track

Mostrar B-Roll en un track separado debajo del A-Roll (diálogo):

```
┌────────────────────────────────────────────────────┐
│ A-Roll     ████████      ██████████      ████████  │
│ (Diálogo)                                          │
├────────────────────────────────────────────────────┤
│ B-Roll        🏙️████            🔍██    🌅██████    │
│ (Apoyo)                                            │
├────────────────────────────────────────────────────┤
│ Eliminados  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   │
└────────────────────────────────────────────────────┘
```

### Iconos por Categoría

```javascript
const categoryIcons = {
  establishing_shot: '🏙️',
  detail_shot: '🔍',
  transition_shot: '➡️',
  ambient_shot: '🌅',
  action_shot: '🎬',
  nature_shot: '🌿',
  graphic_overlay: '📝'
};
```

### Filtros Útiles

```javascript
// Segmentos de alta calidad (score >= 4)
const highQuality = brollSegments.filter(s => s.scores.usefulness >= 4);

// Solo establishing shots
const establishing = brollSegments.filter(s => s.category === 'establishing_shot');

// Segmentos con alta confianza
const confident = brollSegments.filter(s => s.confidence >= 0.8);
```

---

## Validación

Los segmentos B-Roll válidos cumplen:
- `confidence >= 0.5`
- `duration_ms >= 2000` (mínimo 2 segundos)

---

## Ver También

- [FRONTEND-GUIDE.md](./FRONTEND-GUIDE.md) - Guía principal
- [FRONTEND-PROJECTS.md](./FRONTEND-PROJECTS.md) - Multi-video projects
- [API-REFERENCE.md](./API-REFERENCE.md) - Documentación completa
