# Phase 5: Guía de Integración UX para Frontend

> **Documento estratégico** para el equipo de frontend sobre cómo implementar efectivamente las funcionalidades de Phase 5 en la experiencia de usuario.

---

## 1. Visión General

### ¿Qué es Phase 5?

Phase 5 transforma AutoEdit de un editor automático a un **asistente inteligente de edición** que:

| Módulo | Problema que Resuelve | Valor para el Usuario |
|--------|----------------------|----------------------|
| **Intelligence** | "Primera ocurrencia gana" ignora calidad | Selección basada en calidad de audio, delivery, completitud |
| **Narrative** | Videos en orden arbitrario | Estructura narrativa óptima (3 actos, arcos emocionales) |
| **Visual** | Falta saber dónde agregar B-Roll | Sugerencias específicas de qué agregar y dónde |

### Flujo de Usuario Recomendado

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PROYECTO MULTI-VIDEO                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   1. Usuario sube videos ──► Transcripción + Análisis básico       │
│                                      │                              │
│                                      ▼                              │
│   2. ┌─────────────────────────────────────────────────────┐       │
│      │           PANEL DE ANÁLISIS INTELIGENTE              │       │
│      │                                                      │       │
│      │   [Tab: Redundancia]  [Tab: Narrativa]  [Tab: Visual]│       │
│      │                                                      │       │
│      │   ┌──────────────────────────────────────────────┐  │       │
│      │   │  Botón: "Analizar con IA"                    │  │       │
│      │   │  (Ejecuta los 3 análisis en paralelo)        │  │       │
│      │   └──────────────────────────────────────────────┘  │       │
│      └─────────────────────────────────────────────────────┘       │
│                                      │                              │
│                                      ▼                              │
│   3. Usuario revisa recomendaciones ──► HITL: Acepta/Rechaza       │
│                                      │                              │
│                                      ▼                              │
│   4. Aplicar cambios ──► Preview ──► Render final                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Intelligence API - Patrones UX

### 2.1 ¿Cuándo Mostrar Análisis de Redundancia?

**Trigger recomendado**: Después de que el proyecto tenga ≥2 videos procesados.

```typescript
// Mostrar panel de redundancia si:
const showRedundancyPanel =
  project.workflow_ids.length >= 2 &&
  project.stats.completed >= 2;
```

### 2.2 Visualización de Grupos Redundantes

**Diseño sugerido**: Cards agrupadas con comparación lado a lado.

```
┌─────────────────────────────────────────────────────────────────────┐
│  GRUPO DE REDUNDANCIA #1                              Confianza: 85%│
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌─────────────────────────┐     ┌─────────────────────────┐      │
│   │ 📹 Video 2 - 01:23      │     │ 📹 Video 5 - 03:45      │      │
│   │                         │     │                         │      │
│   │ "Entonces lo que        │     │ "Entonces lo que        │      │
│   │  hacemos es..."         │     │  hacemos es..."         │      │
│   │                         │     │                         │      │
│   │ ┌─────────────────────┐ │     │ ┌─────────────────────┐ │      │
│   │ │ 🎤 Audio: ████████░ │ │     │ │ 🎤 Audio: ██████░░░ │ │      │
│   │ │ 🗣️ Delivery: 92%   │ │     │ │ 🗣️ Delivery: 78%   │ │      │
│   │ │ ✓ Completitud: Alta │ │     │ │ ⚠ Completitud: Media│ │      │
│   │ └─────────────────────┘ │     │ └─────────────────────┘ │      │
│   │                         │     │                         │      │
│   │ ⭐ RECOMENDADO          │     │                         │      │
│   └─────────────────────────┘     └─────────────────────────┘      │
│                                                                     │
│   Razón: "Mejor calidad de audio y delivery más confiado"          │
│                                                                     │
│   [ Mantener Izquierdo ]  [ Mantener Derecho ]  [ Mantener Ambos ] │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.3 Indicadores de Confianza

| Nivel | Color | Badge | Acción Sugerida |
|-------|-------|-------|-----------------|
| ≥ 0.8 | Verde | `Alta Confianza` | Auto-aplicar con confirmación |
| 0.6-0.8 | Amarillo | `Revisar` | Mostrar comparación detallada |
| < 0.6 | Gris | `Baja Confianza` | Dejar decisión al usuario |

### 2.4 Código de Implementación

```typescript
// Hook para manejar análisis de redundancia
function useRedundancyAnalysis(projectId: string) {
  const [status, setStatus] = useState<'idle' | 'analyzing' | 'completed'>('idle');
  const [recommendations, setRecommendations] = useState([]);

  const analyze = async () => {
    setStatus('analyzing');

    // POST para iniciar análisis
    const result = await intelligenceApi.analyzeRedundancyQuality(projectId);

    if (result.status === 'analyzing') {
      // Poll cada 5 segundos si es async
      pollForCompletion(projectId);
    } else {
      await fetchRecommendations();
    }
  };

  const fetchRecommendations = async () => {
    const data = await intelligenceApi.getRedundancyRecommendations(projectId, {
      minConfidence: 0.5,
      includeAnalysis: true
    });
    setRecommendations(data.recommendations);
    setStatus('completed');
  };

  const applyRecommendation = async (groupId: string, action: 'keep_left' | 'keep_right' | 'keep_both') => {
    await intelligenceApi.applySmartRecommendations(projectId, {
      groupIds: [groupId],
      // La decisión del usuario
    });
  };

  return { status, recommendations, analyze, applyRecommendation };
}
```

---

## 3. Narrative API - Patrones UX

### 3.1 Timeline Visual de Estructura Narrativa

**Diseño sugerido**: Barra horizontal con secciones coloreadas.

```
┌─────────────────────────────────────────────────────────────────────┐
│  ESTRUCTURA DETECTADA: Three-Act Structure            Confianza: 85%│
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────┬────────────────────────────────┬──────────────────┐  │
│  │  SETUP   │         CONFRONTATION          │    RESOLUTION    │  │
│  │  (25%)   │            (50%)               │      (25%)       │  │
│  └──────────┴────────────────────────────────┴──────────────────┘  │
│                                                                     │
│  📹 Video 1  📹 Video 2  📹 Video 3  📹 Video 4  📹 Video 5        │
│  └────┬────┘ └────┬────┘ └────────┬────────┘ └────┬────┘ └───┬───┘│
│       │           │               │               │           │    │
│       ▼           ▼               ▼               ▼           ▼    │
│   Introducción   Hook      Desarrollo del    Clímax      Cierre   │
│                             problema                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Visualización de Arco Emocional

**Diseño sugerido**: Gráfico de línea con puntos de tensión.

```
Tensión
   ▲
   │                      ●━━━━● Clímax
   │                   ╱         ╲
   │                ╱              ╲
   │             ╱                   ╲
   │          ●                        ●
   │       ╱                              ╲
   │    ●                                    ●━━● Final
   │ ╱
   ●━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━▶ Tiempo
   Video 1   Video 2   Video 3   Video 4   Video 5
```

### 3.3 Drag & Drop para Reordenamiento

```typescript
// Componente de reordenamiento con sugerencias
function NarrativeReorderPanel({ projectId }) {
  const { structure, suggestions } = useNarrativeAnalysis(projectId);
  const [order, setOrder] = useState(structure.current_order);
  const [showSuggestion, setShowSuggestion] = useState(false);

  return (
    <div>
      {/* Orden actual - Draggable */}
      <DragDropContext onDragEnd={handleDragEnd}>
        <Droppable droppableId="videos">
          {(provided) => (
            <div ref={provided.innerRef}>
              {order.map((videoId, index) => (
                <Draggable key={videoId} draggableId={videoId} index={index}>
                  <VideoCard
                    video={videos[videoId]}
                    narrativeRole={structure.video_roles[videoId]}
                  />
                </Draggable>
              ))}
            </div>
          )}
        </Droppable>
      </DragDropContext>

      {/* Sugerencia de IA */}
      {suggestions.length > 0 && (
        <SuggestionBanner
          message={`La IA sugiere reordenar para mejorar el flujo narrativo`}
          confidence={suggestions[0].confidence}
          onApply={() => applyReorder(suggestions[0].new_order)}
          onDismiss={() => setShowSuggestion(false)}
        />
      )}
    </div>
  );
}
```

### 3.4 Indicadores de Gaps Narrativos

```
┌─────────────────────────────────────────────────────────────────────┐
│ ⚠️ GAPS NARRATIVOS DETECTADOS                                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ⚡ Entre Video 2 y Video 3:                                        │
│     "Falta transición. El tema cambia abruptamente de              │
│      'introducción del problema' a 'solución final'"               │
│     Sugerencia: Agregar video de contexto o B-Roll                 │
│     [ Ver sugerencias de Visual API ]                              │
│                                                                     │
│  ⚡ Video 4:                                                        │
│     "Pacing demasiado lento (35% debajo del promedio)"             │
│     Sugerencia: Considerar recortar segmentos lentos               │
│     [ Ver en timeline ]                                            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Visual API - Patrones UX

### 4.1 Cards de Recomendaciones B-Roll

```
┌─────────────────────────────────────────────────────────────────────┐
│  RECOMENDACIONES VISUALES                                    12 items│
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 🎬 B-ROLL SUGERIDO                           Prioridad: Alta │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │                                                              │   │
│  │ 📍 Posición: Video 2, 01:23 - 01:45                         │   │
│  │                                                              │   │
│  │ Contexto: "...cuando estás en la playa..."                  │   │
│  │                                                              │   │
│  │ Sugerencia: Clips de playa, olas, atardecer                 │   │
│  │                                                              │   │
│  │ ┌──────────┐ ┌──────────┐ ┌──────────┐                      │   │
│  │ │ 🏖️      │ │ 🌊      │ │ 🌅      │  ← Stock suggestions  │   │
│  │ │ Playa   │ │ Olas    │ │ Sunset  │                        │   │
│  │ └──────────┘ └──────────┘ └──────────┘                      │   │
│  │                                                              │   │
│  │ [ Agregar B-Roll ]  [ Buscar en librería ]  [ Descartar ]   │   │
│  │                                                              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 📊 DIAGRAMA SUGERIDO                        Prioridad: Media │   │
│  ├─────────────────────────────────────────────────────────────┤   │
│  │                                                              │   │
│  │ 📍 Posición: Video 3, 02:10 - 02:30                         │   │
│  │                                                              │   │
│  │ Contexto: "...los tres pasos son..."                        │   │
│  │                                                              │   │
│  │ Sugerencia: Diagrama de flujo con 3 pasos                   │   │
│  │                                                              │   │
│  │ [ Generar con IA ]  [ Subir imagen ]  [ Descartar ]         │   │
│  │                                                              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 Tipos de Recomendaciones Visuales

| Tipo | Icono | Descripción | Acción Sugerida |
|------|-------|-------------|-----------------|
| `broll` | 🎬 | Clips complementarios | Buscar en stock / subir |
| `diagram` | 📊 | Diagramas explicativos | Generar con IA / subir |
| `data_viz` | 📈 | Visualización de datos | Crear gráfico |
| `text_overlay` | 📝 | Texto en pantalla | Editor de texto |
| `transition` | 🔄 | Transición entre clips | Selector de transiciones |

### 4.3 Integración con Timeline

```
Timeline Principal
────────────────────────────────────────────────────────────────────────
│ Video 1 │████████│ Video 2 │██████████████│ Video 3 │█████████│
────────────────────────────────────────────────────────────────────────
                    ▲              ▲                    ▲
                    │              │                    │
              ┌─────┴─────┐  ┌─────┴─────┐        ┌─────┴─────┐
              │ 🎬 B-Roll │  │ 📊 Diagram│        │ 📝 Text   │
              │ Sugerido  │  │ Sugerido  │        │ Sugerido  │
              └───────────┘  └───────────┘        └───────────┘

Al hacer hover sobre un marcador:
┌───────────────────────────────────────┐
│ 🎬 B-Roll: Escena de producto        │
│                                       │
│ "Muestra el producto mientras        │
│  el narrador lo describe"            │
│                                       │
│ [+] Agregar   [×] Descartar          │
└───────────────────────────────────────┘
```

---

## 5. Flujo Completo de Integración

### 5.1 Orden Recomendado de Llamadas

```typescript
async function runPhase5Analysis(projectId: string) {
  // Ejecutar los 3 análisis en paralelo
  const [intelligence, narrative, visual] = await Promise.all([
    intelligenceApi.analyzeRedundancyQuality(projectId),
    narrativeApi.analyzeNarrativeStructure(projectId, {
      includePacing: true,
      includeEmotional: true,
      includeGaps: true
    }),
    visualApi.analyzeVisualNeeds(projectId)
  ]);

  return {
    intelligence,
    narrative,
    visual,
    completedAt: new Date().toISOString()
  };
}
```

### 5.2 Estados de UI

```typescript
type Phase5State =
  | 'idle'           // No se ha ejecutado análisis
  | 'analyzing'      // Análisis en progreso
  | 'completed'      // Análisis completado, mostrar resultados
  | 'applying'       // Aplicando recomendaciones
  | 'applied';       // Cambios aplicados

// Componente de estado
function Phase5StatusIndicator({ state }: { state: Phase5State }) {
  const config = {
    idle: { icon: '🔮', text: 'Analizar con IA', color: 'blue' },
    analyzing: { icon: '⏳', text: 'Analizando...', color: 'yellow' },
    completed: { icon: '✅', text: 'Análisis listo', color: 'green' },
    applying: { icon: '⚙️', text: 'Aplicando...', color: 'yellow' },
    applied: { icon: '🎉', text: 'Cambios aplicados', color: 'green' }
  };

  return <Badge {...config[state]} />;
}
```

### 5.3 Manejo de Errores

```typescript
// Errores comunes y cómo manejarlos
const errorHandlers = {
  'Phase 5 agents not enabled': {
    userMessage: 'El análisis con IA no está disponible en este momento',
    action: 'Contactar soporte técnico'
  },
  'Intelligence analyzer not available': {
    userMessage: 'El servicio de análisis está temporalmente no disponible',
    action: 'Intentar más tarde'
  },
  'Project not found': {
    userMessage: 'No se encontró el proyecto',
    action: 'Verificar que el proyecto existe'
  },
  'not_analyzed': {
    userMessage: 'Primero ejecuta el análisis',
    action: 'Mostrar botón de "Analizar"'
  }
};
```

### 5.4 Caching y Optimización

```typescript
// Estrategia de caching recomendada
const cacheStrategy = {
  // GET endpoints - cachear por 5 minutos
  'redundancy-recommendations': { ttl: 5 * 60 * 1000 },
  'narrative/structure': { ttl: 5 * 60 * 1000 },
  'visual/recommendations': { ttl: 5 * 60 * 1000 },

  // Invalidar cache cuando:
  invalidateOn: [
    'POST analyze-*',      // Después de nuevo análisis
    'POST apply-*',        // Después de aplicar cambios
    'workflow updated'     // Cuando se modifica un video
  ]
};
```

---

## 6. Componentes UI Sugeridos

### 6.1 Panel Principal de Phase 5

```
┌─────────────────────────────────────────────────────────────────────┐
│  🧠 ANÁLISIS INTELIGENTE                                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌───────────────┬───────────────┬───────────────┐                 │
│  │ 🔍 Redundancia│ 📖 Narrativa  │ 🎬 Visual     │                 │
│  │    5 grupos   │  3-Act Struct │  12 sugerenc. │                 │
│  │    ✓ Listo    │  ✓ Listo      │  ✓ Listo      │                 │
│  └───────────────┴───────────────┴───────────────┘                 │
│                                                                     │
│  [ 🔄 Re-analizar Todo ]                    Última vez: hace 5 min │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 Estado Vacío (Sin Análisis)

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│                         🧠                                          │
│                                                                     │
│              Potencia tu edición con IA                            │
│                                                                     │
│   La IA analizará tu proyecto para:                                │
│                                                                     │
│   ✓ Detectar segmentos redundantes y elegir el mejor              │
│   ✓ Optimizar la estructura narrativa                              │
│   ✓ Sugerir dónde agregar B-Roll y gráficos                       │
│                                                                     │
│              [ 🚀 Iniciar Análisis con IA ]                         │
│                                                                     │
│   Tiempo estimado: ~30 segundos                                    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.3 Estado de Error

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│                         ⚠️                                          │
│                                                                     │
│           No se pudo completar el análisis                         │
│                                                                     │
│   Error: El servicio de IA no está disponible temporalmente        │
│                                                                     │
│              [ 🔄 Reintentar ]  [ ❌ Cancelar ]                     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 7. Resumen de Endpoints

### Referencia Rápida

| Módulo | Endpoint | Método | Propósito |
|--------|----------|--------|-----------|
| **Intelligence** | `/project/{id}/intelligence/analyze-redundancy-quality` | POST | Iniciar análisis |
| | `/project/{id}/intelligence/redundancy-recommendations` | GET | Obtener recomendaciones |
| | `/project/{id}/intelligence/apply-smart-recommendations` | POST | Aplicar decisiones |
| **Narrative** | `/project/{id}/narrative/analyze-structure` | POST | Iniciar análisis |
| | `/project/{id}/narrative/structure` | GET | Obtener estructura |
| | `/project/{id}/narrative/reorder-suggestions` | GET | Obtener sugerencias |
| | `/project/{id}/narrative/apply-reorder` | POST | Aplicar reorden |
| **Visual** | `/project/{id}/visual/analyze-needs` | POST | Iniciar análisis |
| | `/project/{id}/visual/recommendations` | GET | Obtener sugerencias |
| | `/project/{id}/visual/apply-recommendations` | POST | Aplicar selección |
| | `/project/{id}/visual/broll-suggestions` | GET | Sugerencias B-Roll |

---

## 8. Checklist de Implementación

### Fase 1: Infraestructura
- [ ] Crear servicios API para cada módulo (intelligence, narrative, visual)
- [ ] Implementar polling para análisis async
- [ ] Configurar caching de respuestas GET

### Fase 2: UI Básica
- [ ] Panel de Phase 5 con tabs
- [ ] Estados: idle, analyzing, completed, error
- [ ] Botón "Analizar con IA"

### Fase 3: Intelligence
- [ ] Cards de grupos redundantes
- [ ] Comparación lado a lado
- [ ] Botones de decisión HITL

### Fase 4: Narrative
- [ ] Timeline de estructura narrativa
- [ ] Drag & drop para reordenar
- [ ] Gráfico de arco emocional

### Fase 5: Visual
- [ ] Lista de recomendaciones
- [ ] Marcadores en timeline
- [ ] Integración con librería de assets

### Fase 6: Pulido
- [ ] Animaciones de transición
- [ ] Feedback háptico/visual
- [ ] Tests de usabilidad

---

## Documentación Relacionada

- [API Reference completo](./API-REFERENCE.md)
- [Intelligence API Details](./FRONTEND-PHASE5-INTELLIGENCE.md)
- [Narrative API Details](./FRONTEND-PHASE5-NARRATIVE.md)
- [Visual API Details](./FRONTEND-PHASE5-VISUAL.md)
- [Graph API Details](./FRONTEND-PHASE5-GRAPH.md)
