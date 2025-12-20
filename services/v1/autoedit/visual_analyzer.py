# Copyright (c) 2025 Stephen G. Pope
# Licensed under GPL-2.0

"""
Visual Analyzer Service for AutoEdit Phase 5

Uses LLM (Gemini) to analyze video content and recommend visual enhancements.
Identifies opportunities for B-Roll, graphics, animations, maps, data
visualizations, and other supporting visual elements.

Key capabilities:
- B-Roll recommendations with stock search keywords
- Diagram and infographic suggestions
- Data visualization opportunities
- Map and geographic content recommendations
- AI generation prompts for visual assets
- Production notes for consistent styling
"""

import os
import json
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# Prompt file path
PROMPT_FILE = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "infrastructure", "prompts", "autoedit_visual_recommender_prompt.txt"
)


# Visual recommendation types
VISUAL_TYPES = {
    "broll": "B-Roll footage",
    "title_card": "Title card or lower third",
    "diagram": "Diagram or illustration",
    "data_visualization": "Chart or infographic",
    "map_animation": "Map or geographic visual",
    "screen_recording": "Screen capture or UI mockup",
    "3d_render": "3D render or animation",
    "historical": "Historical or archival content",
    "text_overlay": "Text overlay or caption"
}


class VisualAnalyzer:
    """
    LLM-powered analyzer for visual enhancement recommendations.

    Analyzes video content to identify opportunities for visual
    support and generates actionable recommendations including
    AI generation prompts and stock search keywords.
    """

    def __init__(self):
        self._prompt_template = None
        self._model = None

    def _load_prompt(self) -> str:
        """Load the visual recommender prompt template."""
        if self._prompt_template is None:
            try:
                prompt_path = os.path.normpath(PROMPT_FILE)
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    self._prompt_template = f.read()
            except Exception as e:
                logger.error(f"Failed to load prompt: {e}")
                self._prompt_template = ""
        return self._prompt_template

    def _get_model(self):
        """Get or initialize the Gemini model."""
        if self._model is None:
            try:
                import google.generativeai as genai

                api_key = os.environ.get("GEMINI_API_KEY")
                if not api_key:
                    logger.warning("GEMINI_API_KEY not set, visual analysis disabled")
                    return None

                genai.configure(api_key=api_key)
                self._model = genai.GenerativeModel("gemini-2.0-flash")
                logger.info("Initialized Gemini model for visual analysis")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini: {e}")
                return None

        return self._model

    def is_available(self) -> bool:
        """Check if the visual analyzer is available."""
        return self._get_model() is not None

    # =========================================================================
    # VISUAL ANALYSIS
    # =========================================================================

    def analyze_visual_needs(
        self,
        workflow_data: Dict[str, Any],
        project_context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze a video workflow and recommend visual enhancements.

        Args:
            workflow_data: Workflow with segments/blocks:
                - workflow_id: Unique identifier
                - blocks: List of segments with text
                - analysis: Optional existing analysis
            project_context: Optional creator/project context

        Returns:
            Visual recommendations or None on failure
        """
        model = self._get_model()
        if not model:
            logger.warning("Model not available, using basic analysis")
            return self._basic_visual_analysis(workflow_data, project_context)

        try:
            # Prepare input data
            input_data = self._prepare_workflow_input(workflow_data, project_context)

            # Build the full prompt
            prompt = self._load_prompt()
            full_prompt = f"{prompt}\n\n## Input Data\n\n```json\n{json.dumps(input_data, indent=2)}\n```\n\nProvide comprehensive visual recommendations."

            # Call the model
            response = model.generate_content(
                full_prompt,
                generation_config={
                    "temperature": 0.5,  # Slightly higher for creativity
                    "max_output_tokens": 4000
                }
            )

            # Parse response
            result = self._parse_response(response.text)

            if result:
                result["workflow_id"] = workflow_data.get("workflow_id")
                result["analyzed_at"] = datetime.utcnow().isoformat()
                logger.info(f"Visual analysis complete for workflow {workflow_data.get('workflow_id')}")

            return result

        except Exception as e:
            logger.error(f"Visual analysis failed: {e}")
            return self._basic_visual_analysis(workflow_data, project_context)

    def analyze_project_visuals(
        self,
        project_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze visual needs across all videos in a project.

        Args:
            project_data: Project with videos and context

        Returns:
            Aggregated visual recommendations for the project
        """
        project_context = project_data.get("creator_context", {})
        project_id = project_data.get("project_id")

        all_recommendations = []
        workflow_results = []

        for video in project_data.get("videos", []):
            result = self.analyze_visual_needs(video, project_context)
            if result:
                workflow_results.append({
                    "workflow_id": video.get("workflow_id"),
                    "recommendation_count": len(result.get("visual_recommendations", [])),
                    "high_priority_count": sum(
                        1 for r in result.get("visual_recommendations", [])
                        if r.get("priority") == "high"
                    )
                })
                all_recommendations.extend(result.get("visual_recommendations", []))

        # Aggregate statistics
        type_counts = {}
        priority_counts = {"high": 0, "medium": 0, "low": 0}

        for rec in all_recommendations:
            rec_type = rec.get("type", "unknown")
            type_counts[rec_type] = type_counts.get(rec_type, 0) + 1
            priority = rec.get("priority", "medium")
            priority_counts[priority] = priority_counts.get(priority, 0) + 1

        # Extract common themes for visual library
        themes = set()
        for rec in all_recommendations:
            themes.update(rec.get("alternatives", {}).get("stock_keywords", []))
            content = rec.get("content", {})
            themes.update(content.get("key_elements", []))

        return {
            "project_id": project_id,
            "total_recommendations": len(all_recommendations),
            "by_type": type_counts,
            "by_priority": priority_counts,
            "workflows": workflow_results,
            "visual_themes": list(themes)[:20],  # Top themes
            "production_effort": self._estimate_effort(all_recommendations),
            "analyzed_at": datetime.utcnow().isoformat()
        }

    def get_broll_recommendations(
        self,
        workflow_data: Dict[str, Any],
        project_context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get B-Roll specific recommendations for a video.

        Args:
            workflow_data: Workflow with segments
            project_context: Optional context

        Returns:
            List of B-Roll recommendations
        """
        full_analysis = self.analyze_visual_needs(workflow_data, project_context)

        if not full_analysis:
            return []

        # Filter for B-Roll only
        recommendations = full_analysis.get("visual_recommendations", [])
        return [r for r in recommendations if r.get("type") == "broll"]

    def get_graphics_recommendations(
        self,
        workflow_data: Dict[str, Any],
        project_context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get graphics/animation recommendations (diagrams, charts, etc.).

        Args:
            workflow_data: Workflow with segments
            project_context: Optional context

        Returns:
            List of graphics recommendations
        """
        full_analysis = self.analyze_visual_needs(workflow_data, project_context)

        if not full_analysis:
            return []

        # Filter for graphics types
        graphics_types = ["diagram", "data_visualization", "map_animation", "3d_render"]
        recommendations = full_analysis.get("visual_recommendations", [])
        return [r for r in recommendations if r.get("type") in graphics_types]

    # =========================================================================
    # SEGMENT-LEVEL ANALYSIS
    # =========================================================================

    def analyze_segment_visual_needs(
        self,
        segment: Dict[str, Any],
        workflow_context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze visual needs for a single segment.

        Args:
            segment: Segment data with text and timing
            workflow_context: Optional workflow context

        Returns:
            Visual recommendations for this segment or None
        """
        model = self._get_model()
        if not model:
            return None

        try:
            prompt = f"""Analyze this video segment and recommend visual enhancements.

Segment:
- ID: {segment.get('segment_id', segment.get('id', 'unknown'))}
- Text: {segment.get('text', '')}
- Duration: {(segment.get('out_ms', segment.get('out', 0)) - segment.get('in_ms', segment.get('in', 0))) / 1000:.1f}s
- Topics: {segment.get('topics', [])}

Context: {json.dumps(workflow_context or {}, indent=2)}

Recommend 0-2 visual enhancements. Only suggest if truly beneficial.

Respond with JSON:
{{
  "needs_visual": true|false,
  "recommendations": [
    {{
      "type": "broll|diagram|data_visualization|map_animation|text_overlay",
      "priority": "high|medium|low",
      "description": "What to show",
      "ai_prompt": "Prompt for AI generation (if applicable)",
      "stock_keywords": ["keyword1", "keyword2"],
      "duration_sec": 5,
      "rationale": "Why this visual helps"
    }}
  ],
  "talking_head_ok": true|false,
  "notes": "Any additional observations"
}}"""

            response = model.generate_content(
                prompt,
                generation_config={"temperature": 0.4, "max_output_tokens": 1000}
            )

            result = self._parse_response(response.text)
            if result:
                result["segment_id"] = segment.get("segment_id", segment.get("id"))

            return result

        except Exception as e:
            logger.error(f"Segment visual analysis failed: {e}")
            return None

    def identify_visual_gaps(
        self,
        workflow_data: Dict[str, Any],
        max_talking_head_sec: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Identify segments with extended talking head time that need visual variety.

        Args:
            workflow_data: Workflow with segments
            max_talking_head_sec: Maximum seconds before suggesting visual break

        Returns:
            List of gap identifications with suggestions
        """
        blocks = workflow_data.get("blocks", [])
        gaps = []

        # Track consecutive talking head time
        consecutive_speech_ms = 0
        gap_start_ms = 0

        for block in blocks:
            if block.get("action") != "keep":
                continue

            block_type = block.get("type", "speech")
            duration = block.get("out", 0) - block.get("in", 0)

            if block_type == "speech":
                if consecutive_speech_ms == 0:
                    gap_start_ms = block.get("in", 0)
                consecutive_speech_ms += duration

                # Check if exceeded threshold
                if consecutive_speech_ms > max_talking_head_sec * 1000:
                    gaps.append({
                        "segment_id": block.get("id"),
                        "gap_type": "extended_talking_head",
                        "start_ms": gap_start_ms,
                        "end_ms": block.get("out", 0),
                        "duration_sec": consecutive_speech_ms / 1000,
                        "suggestion": "Consider adding B-Roll, graphic, or text overlay",
                        "severity": "high" if consecutive_speech_ms > 60000 else "medium"
                    })
            else:
                consecutive_speech_ms = 0

        return gaps

    # =========================================================================
    # AI GENERATION PROMPTS
    # =========================================================================

    def generate_ai_prompts(
        self,
        recommendations: List[Dict[str, Any]],
        style_guide: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate refined AI prompts for visual recommendations.

        Args:
            recommendations: List of visual recommendations
            style_guide: Optional brand/style guidelines

        Returns:
            Recommendations with enhanced AI prompts
        """
        enhanced = []
        style = style_guide or {}

        for rec in recommendations:
            enhanced_rec = rec.copy()
            gen = rec.get("generation", {})
            ai_prompt = gen.get("ai_prompt")

            if ai_prompt:
                # Enhance prompt with style guidelines
                style_additions = []

                if style.get("color_palette"):
                    style_additions.append(f"color palette: {style['color_palette']}")
                if style.get("brand_style"):
                    style_additions.append(f"style: {style['brand_style']}")
                if style.get("mood"):
                    style_additions.append(f"mood: {style['mood']}")

                if style_additions:
                    enhanced_prompt = f"{ai_prompt}, {', '.join(style_additions)}"
                    enhanced_rec["generation"]["ai_prompt"] = enhanced_prompt
                    enhanced_rec["generation"]["style_applied"] = True

            enhanced.append(enhanced_rec)

        return enhanced

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _prepare_workflow_input(
        self,
        workflow_data: Dict[str, Any],
        project_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Prepare workflow data for LLM input."""
        blocks = workflow_data.get("blocks", [])

        # Convert blocks to segments format
        segments = []
        for block in blocks:
            if block.get("action") != "keep":
                continue

            segments.append({
                "segment_id": block.get("id", f"seg_{block.get('in', 0)}"),
                "in_ms": block.get("in", 0),
                "out_ms": block.get("out", 0),
                "text": block.get("text", ""),
                "type": block.get("type", "speech"),
                "topics": block.get("topics", []),
                "entities": block.get("entities", [])
            })

        # Limit segments for context
        if len(segments) > 30:
            segments = segments[:30]

        return {
            "workflow_id": workflow_data.get("workflow_id"),
            "project_context": project_context or {},
            "segments": segments,
            "video_analysis": {
                "main_topics": workflow_data.get("analysis", {}).get("main_topics", []),
                "content_type": workflow_data.get("analysis", {}).get("content_type", "general"),
                "visual_complexity": "low"  # Default, will be assessed
            }
        }

    def _parse_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Parse the LLM response into structured data."""
        try:
            text = response_text.strip()

            # Extract JSON block
            if "```json" in text:
                start = text.find("```json") + 7
                end = text.find("```", start)
                if end > start:
                    text = text[start:end].strip()
            elif "```" in text:
                start = text.find("```") + 3
                end = text.find("```", start)
                if end > start:
                    text = text[start:end].strip()

            return json.loads(text)

        except json.JSONDecodeError:
            logger.warning("Failed to parse visual response as JSON")
            return None

    def _basic_visual_analysis(
        self,
        workflow_data: Dict[str, Any],
        project_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Basic visual analysis without LLM."""
        blocks = workflow_data.get("blocks", [])
        recommendations = []

        # Simple heuristics: suggest B-Roll for long speech segments
        for block in blocks:
            if block.get("action") != "keep":
                continue

            duration = block.get("out", 0) - block.get("in", 0)
            text = block.get("text", "")

            # Long segment with technical content
            if duration > 20000 and any(word in text.lower() for word in ["how", "process", "step", "method"]):
                recommendations.append({
                    "id": f"vis_{block.get('in', 0)}",
                    "segment_id": block.get("id"),
                    "timestamp": {
                        "in_ms": block.get("in", 0) + 2000,
                        "out_ms": block.get("out", 0) - 2000
                    },
                    "type": "broll",
                    "priority": "medium",
                    "content": {
                        "description": "Consider B-Roll to support this explanation"
                    },
                    "alternatives": {
                        "stock_keywords": self._extract_keywords(text)
                    },
                    "rationale": "Extended explanation segment, visual variety recommended",
                    "fallback_used": True
                })

        return {
            "visual_recommendations": recommendations,
            "segment_gaps": self.identify_visual_gaps(workflow_data),
            "overall_assessment": {
                "visual_complexity_current": "low",
                "total_recommendations": len(recommendations),
                "high_priority_count": 0,
                "estimated_production_effort": "low"
            },
            "workflow_id": workflow_data.get("workflow_id"),
            "fallback_used": True,
            "analyzed_at": datetime.utcnow().isoformat()
        }

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract potential stock search keywords from text."""
        # Simple extraction - could be enhanced with NLP
        words = text.lower().split()

        # Common stop words to exclude
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                     "have", "has", "had", "do", "does", "did", "will", "would",
                     "could", "should", "may", "might", "must", "and", "or", "but",
                     "in", "on", "at", "to", "for", "of", "with", "by", "from",
                     "this", "that", "these", "those", "it", "its", "they", "them"}

        keywords = []
        for word in words:
            clean = word.strip(".,!?\"'()")
            if len(clean) > 3 and clean not in stop_words:
                keywords.append(clean)

        # Return unique keywords
        return list(dict.fromkeys(keywords))[:5]

    def _estimate_effort(self, recommendations: List[Dict[str, Any]]) -> str:
        """Estimate production effort based on recommendations."""
        if not recommendations:
            return "none"

        # Count complex types
        complex_types = ["3d_render", "map_animation", "diagram"]
        complex_count = sum(1 for r in recommendations if r.get("type") in complex_types)

        high_priority = sum(1 for r in recommendations if r.get("priority") == "high")

        if complex_count > 3 or high_priority > 5:
            return "high"
        elif complex_count > 0 or high_priority > 2 or len(recommendations) > 8:
            return "medium"
        else:
            return "low"


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_analyzer = None


def get_visual_analyzer() -> VisualAnalyzer:
    """Get the singleton VisualAnalyzer instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = VisualAnalyzer()
    return _analyzer


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def analyze_workflow_visuals(
    workflow_data: Dict[str, Any],
    project_context: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Get visual recommendations for a workflow.

    Args:
        workflow_data: Workflow with blocks/segments
        project_context: Optional project/creator context

    Returns:
        Visual recommendations
    """
    analyzer = get_visual_analyzer()
    return analyzer.analyze_visual_needs(workflow_data, project_context)


def get_broll_suggestions(
    workflow_data: Dict[str, Any],
    project_context: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Get B-Roll suggestions for a workflow.

    Args:
        workflow_data: Workflow with blocks
        project_context: Optional context

    Returns:
        List of B-Roll recommendations
    """
    analyzer = get_visual_analyzer()
    return analyzer.get_broll_recommendations(workflow_data, project_context)


def get_graphics_suggestions(
    workflow_data: Dict[str, Any],
    project_context: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Get graphics/animation suggestions.

    Args:
        workflow_data: Workflow with blocks
        project_context: Optional context

    Returns:
        List of graphics recommendations
    """
    analyzer = get_visual_analyzer()
    return analyzer.get_graphics_recommendations(workflow_data, project_context)


def is_visual_analyzer_available() -> bool:
    """Check if visual analysis is available."""
    analyzer = get_visual_analyzer()
    return analyzer.is_available()
