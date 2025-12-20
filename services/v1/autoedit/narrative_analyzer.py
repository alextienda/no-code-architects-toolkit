# Copyright (c) 2025 Stephen G. Pope
# Licensed under GPL-2.0

"""
Narrative Analyzer Service for AutoEdit Phase 5

Uses LLM (Gemini) to analyze video content for narrative structure,
pacing, emotional arcs, and optimal ordering. Supports both single
videos and multi-video projects.

Key capabilities:
- Detect narrative structure (Three-Act, Hero's Journey, etc.)
- Analyze pacing and tension curves
- Identify emotional arcs and engagement peaks
- Suggest optimal video ordering for multi-video projects
- Detect narrative gaps and structural issues
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
    "infrastructure", "prompts", "autoedit_narrative_analyzer_prompt.txt"
)


class NarrativeAnalyzer:
    """
    LLM-powered analyzer for narrative structure and content organization.

    Analyzes video projects to identify narrative patterns, suggest
    improvements, and optimize content ordering.
    """

    def __init__(self):
        self._prompt_template = None
        self._model = None

    def _load_prompt(self) -> str:
        """Load the narrative analyzer prompt template."""
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
                    logger.warning("GEMINI_API_KEY not set, narrative analysis disabled")
                    return None

                genai.configure(api_key=api_key)
                # Use Gemini 2.5 Pro for complex narrative analysis
                self._model = genai.GenerativeModel("gemini-2.5-pro-preview-06-05")
                logger.info("Initialized Gemini model for narrative analysis")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini: {e}")
                return None

        return self._model

    def is_available(self) -> bool:
        """Check if the narrative analyzer is available."""
        return self._get_model() is not None

    # =========================================================================
    # STRUCTURE ANALYSIS
    # =========================================================================

    def analyze_structure(
        self,
        project_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze the narrative structure of a project.

        Args:
            project_data: Project with videos and content summaries:
                - project_id: Project identifier
                - videos: List of video data with summaries
                - creator_context: Optional creator profile

        Returns:
            Structure analysis result or None on failure
        """
        model = self._get_model()
        if not model:
            logger.warning("Model not available, returning basic structure")
            return self._basic_structure_analysis(project_data)

        try:
            # Build input data
            input_data = self._prepare_project_input(project_data)

            # Build the full prompt
            prompt = self._load_prompt()
            full_prompt = f"{prompt}\n\n## Project Data\n\n```json\n{json.dumps(input_data, indent=2)}\n```\n\nProvide a complete narrative analysis."

            # Call the model
            response = model.generate_content(
                full_prompt,
                generation_config={
                    "temperature": 0.4,
                    "max_output_tokens": 4000
                }
            )

            # Parse response
            result = self._parse_response(response.text)

            if result:
                result["project_id"] = project_data.get("project_id")
                result["analyzed_at"] = datetime.utcnow().isoformat()
                logger.info(f"Narrative analysis complete for project {project_data.get('project_id')}")

            return result

        except Exception as e:
            logger.error(f"Narrative analysis failed: {e}")
            return self._basic_structure_analysis(project_data)

    def analyze_pacing(
        self,
        video_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze pacing and tension curve of a single video.

        Args:
            video_data: Video with segments and timing

        Returns:
            Pacing analysis or None on failure
        """
        model = self._get_model()
        if not model:
            return None

        try:
            prompt = f"""Analyze the pacing of this video content.

Video: {video_data.get('title', video_data.get('workflow_id'))}
Duration: {video_data.get('duration_ms', 0) / 1000:.1f} seconds

Segments:
{json.dumps(video_data.get('segments_summary', video_data.get('blocks', [])), indent=2)}

Analyze and respond with JSON:
{{
  "overall_rhythm": "steady|accelerating|decelerating|varied",
  "tension_curve": [
    {{"time": "0:00-1:00", "level": 3, "trend": "rising|falling|sustaining"}}
  ],
  "pacing_issues": [
    {{
      "time": "2:00-3:00",
      "type": "rushed|slow|uneven",
      "description": "...",
      "suggestion": "..."
    }}
  ],
  "information_density_score": 0.7,
  "engagement_risk_points": ["1:30", "4:00"]
}}"""

            response = model.generate_content(
                prompt,
                generation_config={"temperature": 0.3, "max_output_tokens": 1500}
            )

            result = self._parse_response(response.text)
            if result:
                result["workflow_id"] = video_data.get("workflow_id")

            return result

        except Exception as e:
            logger.error(f"Pacing analysis failed: {e}")
            return None

    def analyze_emotional_arc(
        self,
        project_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze emotional journey across a project.

        Args:
            project_data: Project with video summaries

        Returns:
            Emotional arc analysis or None on failure
        """
        model = self._get_model()
        if not model:
            return None

        try:
            # Prepare video summaries
            videos_summary = []
            for video in project_data.get("videos", []):
                videos_summary.append({
                    "id": video.get("workflow_id"),
                    "summary": video.get("summary", ""),
                    "tone": video.get("emotional_tone", "neutral"),
                    "topics": video.get("topics", [])
                })

            prompt = f"""Analyze the emotional arc of this video project.

Creator: {project_data.get('creator_context', {}).get('name', 'Unknown')}
Content Type: {project_data.get('creator_context', {}).get('typical_content', ['general'])}

Videos:
{json.dumps(videos_summary, indent=2)}

Respond with JSON:
{{
  "dominant_emotions": ["curiosity", "engagement"],
  "emotional_journey": [
    {{"phase": "opening", "video": "wf_001", "emotion": "curiosity", "intensity": 0.6}}
  ],
  "coherence_score": 0.8,
  "emotional_peaks": [
    {{"video": "wf_002", "time": "middle", "emotion": "excitement", "trigger": "reveal moment"}}
  ],
  "emotional_gaps": [
    {{"between": ["wf_001", "wf_002"], "issue": "abrupt shift", "suggestion": "add transition"}}
  ]
}}"""

            response = model.generate_content(
                prompt,
                generation_config={"temperature": 0.4, "max_output_tokens": 1500}
            )

            result = self._parse_response(response.text)
            if result:
                result["project_id"] = project_data.get("project_id")

            return result

        except Exception as e:
            logger.error(f"Emotional arc analysis failed: {e}")
            return None

    # =========================================================================
    # REORDERING SUGGESTIONS
    # =========================================================================

    def suggest_reordering(
        self,
        project_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Suggest optimal ordering for multi-video projects.

        Args:
            project_data: Project with videos and dependencies

        Returns:
            Reordering suggestions with rationale or None
        """
        model = self._get_model()
        videos = project_data.get("videos", [])

        if len(videos) < 2:
            return {
                "suggestions": [],
                "message": "Single video project, no reordering needed"
            }

        if not model:
            return self._basic_reordering(project_data)

        try:
            # Prepare video data for analysis
            videos_data = []
            for video in videos:
                videos_data.append({
                    "id": video.get("workflow_id"),
                    "current_index": video.get("sequence_index", 0),
                    "title": video.get("title", "Untitled"),
                    "summary": video.get("summary", ""),
                    "topics": video.get("topics", []),
                    "dependencies": video.get("requires_videos", []),
                    "key_points": video.get("key_points", [])
                })

            prompt = f"""Analyze the video order for this project and suggest improvements.

Current Order:
{json.dumps(videos_data, indent=2)}

Creator Style: {project_data.get('creator_context', {}).get('style', 'general')}

Consider:
1. Topic dependencies (what must be learned before what)
2. Narrative flow (hooks, build-up, climax, resolution)
3. Engagement curve (don't put all easy content at start)
4. Educational progression (simple to complex)

Respond with JSON:
{{
  "current_order_assessment": {{
    "score": 0.7,
    "issues": ["dependency violation between X and Y"]
  }},
  "suggestions": [
    {{
      "proposed_order": ["wf_001", "wf_003", "wf_002"],
      "confidence": 0.8,
      "rationale": "Video 3 introduces concepts needed in Video 2",
      "changes": [
        {{"video": "wf_003", "from": 2, "to": 1, "reason": "foundational content"}}
      ],
      "impact": {{
        "narrative_flow": "improved",
        "learning_curve": "smoother",
        "engagement": "similar"
      }}
    }}
  ],
  "dependencies_identified": [
    {{"video": "wf_002", "requires": "wf_003", "reason": "uses concepts from"}}
  ]
}}"""

            response = model.generate_content(
                prompt,
                generation_config={"temperature": 0.3, "max_output_tokens": 2000}
            )

            result = self._parse_response(response.text)
            if result:
                result["project_id"] = project_data.get("project_id")
                result["video_count"] = len(videos)

            return result

        except Exception as e:
            logger.error(f"Reordering analysis failed: {e}")
            return self._basic_reordering(project_data)

    # =========================================================================
    # GAP DETECTION
    # =========================================================================

    def detect_narrative_gaps(
        self,
        project_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Detect narrative gaps, missing bridges, and dangling threads.

        Args:
            project_data: Project with video content

        Returns:
            Gap analysis or None on failure
        """
        model = self._get_model()
        if not model:
            return None

        try:
            videos_data = []
            for video in project_data.get("videos", []):
                videos_data.append({
                    "id": video.get("workflow_id"),
                    "summary": video.get("summary", ""),
                    "topics_introduced": video.get("topics", []),
                    "topics_concluded": video.get("concluded_topics", []),
                    "key_points": video.get("key_points", [])
                })

            prompt = f"""Analyze this project for narrative gaps and issues.

Videos:
{json.dumps(videos_data, indent=2)}

Look for:
1. Missing bridges (topics that need transitions between videos)
2. Dangling threads (introduced but never resolved)
3. Redundant content (same topic covered multiple times)
4. Missing conclusions (topics that need wrap-up)

Respond with JSON:
{{
  "gaps": [
    {{
      "type": "missing_bridge|dangling_thread|redundant|incomplete",
      "location": {{"between": ["wf_001", "wf_002"]}} | {{"in": "wf_003"}},
      "topic": "affected topic",
      "description": "what's missing",
      "suggestions": ["how to fix"],
      "severity": "critical|moderate|minor",
      "effort": "high|medium|low"
    }}
  ],
  "coverage_analysis": {{
    "well_covered": ["topic1", "topic2"],
    "needs_expansion": ["topic3"],
    "over_covered": ["topic4"]
  }},
  "overall_completeness": 0.8
}}"""

            response = model.generate_content(
                prompt,
                generation_config={"temperature": 0.3, "max_output_tokens": 2000}
            )

            result = self._parse_response(response.text)
            if result:
                result["project_id"] = project_data.get("project_id")

            return result

        except Exception as e:
            logger.error(f"Gap detection failed: {e}")
            return None

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _prepare_project_input(self, project_data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare project data for LLM input."""
        videos = []
        for video in project_data.get("videos", []):
            # Summarize segments if too many
            segments = video.get("segments_summary", video.get("blocks", []))
            if len(segments) > 20:
                # Group into time ranges
                segments = self._summarize_segments(segments)

            videos.append({
                "workflow_id": video.get("workflow_id"),
                "sequence_index": video.get("sequence_index", 0),
                "title": video.get("title", video.get("workflow_id")),
                "duration_ms": video.get("duration_ms", 0),
                "summary": video.get("summary", ""),
                "topics": video.get("topics", []),
                "emotional_tone": video.get("emotional_tone", "neutral"),
                "key_points": video.get("key_points", []),
                "segments_summary": segments[:15]  # Limit for context
            })

        return {
            "project_id": project_data.get("project_id"),
            "videos": videos,
            "creator_context": project_data.get("creator_context", {})
        }

    def _summarize_segments(self, segments: List[Dict]) -> List[Dict]:
        """Summarize segments into broader time ranges."""
        if not segments:
            return []

        # Group into ~30 second chunks
        summaries = []
        current_group = []
        group_start = 0

        for seg in segments:
            seg_start = seg.get("in_ms", seg.get("in", 0))
            seg_end = seg.get("out_ms", seg.get("out", 0))

            if not current_group:
                group_start = seg_start

            current_group.append(seg)

            # Check if we should close this group
            if seg_end - group_start > 30000:  # 30 seconds
                summaries.append({
                    "time_range": f"{group_start/1000:.0f}s-{seg_end/1000:.0f}s",
                    "content_type": self._infer_content_type(current_group),
                    "summary": " ".join([s.get("text", "")[:50] for s in current_group[:3]])
                })
                current_group = []

        # Handle remaining
        if current_group:
            summaries.append({
                "time_range": f"{group_start/1000:.0f}s-end",
                "content_type": self._infer_content_type(current_group),
                "summary": " ".join([s.get("text", "")[:50] for s in current_group[:3]])
            })

        return summaries

    def _infer_content_type(self, segments: List[Dict]) -> str:
        """Infer content type from segments."""
        if not segments:
            return "unknown"

        # Check for common patterns
        texts = " ".join([s.get("text", "") for s in segments]).lower()

        if any(word in texts for word in ["let's", "today", "welcome", "hello"]):
            return "introduction"
        elif any(word in texts for word in ["step", "first", "then", "next"]):
            return "tutorial"
        elif any(word in texts for word in ["conclusion", "summary", "finally"]):
            return "conclusion"
        elif any(word in texts for word in ["example", "for instance", "like"]):
            return "explanation"
        else:
            return "content"

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
            logger.warning("Failed to parse narrative response as JSON")
            return None

    def _basic_structure_analysis(self, project_data: Dict[str, Any]) -> Dict[str, Any]:
        """Basic structure analysis without LLM."""
        videos = project_data.get("videos", [])

        # Simple heuristics
        if len(videos) == 1:
            structure_type = "single_video"
        elif len(videos) <= 3:
            structure_type = "three_act"
        else:
            structure_type = "episodic"

        return {
            "structure_analysis": {
                "detected_structure": {
                    "type": structure_type,
                    "confidence": 0.4,
                    "note": "Basic analysis without LLM"
                }
            },
            "project_id": project_data.get("project_id"),
            "fallback_used": True,
            "analyzed_at": datetime.utcnow().isoformat()
        }

    def _basic_reordering(self, project_data: Dict[str, Any]) -> Dict[str, Any]:
        """Basic reordering without LLM - keep current order."""
        videos = project_data.get("videos", [])

        return {
            "current_order_assessment": {
                "score": 0.5,
                "issues": ["Analysis unavailable"]
            },
            "suggestions": [],
            "message": "LLM unavailable, cannot suggest reordering",
            "project_id": project_data.get("project_id"),
            "fallback_used": True
        }


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_analyzer = None


def get_narrative_analyzer() -> NarrativeAnalyzer:
    """Get the singleton NarrativeAnalyzer instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = NarrativeAnalyzer()
    return _analyzer


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def analyze_project_narrative(project_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Full narrative analysis of a project.

    Args:
        project_data: Project with videos and context

    Returns:
        Complete narrative analysis
    """
    analyzer = get_narrative_analyzer()
    return analyzer.analyze_structure(project_data)


def get_reorder_suggestions(project_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Get video reordering suggestions.

    Args:
        project_data: Project with videos

    Returns:
        Reordering suggestions
    """
    analyzer = get_narrative_analyzer()
    return analyzer.suggest_reordering(project_data)


def detect_gaps(project_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Detect narrative gaps in project.

    Args:
        project_data: Project with videos

    Returns:
        Gap analysis
    """
    analyzer = get_narrative_analyzer()
    return analyzer.detect_narrative_gaps(project_data)


def is_narrative_analyzer_available() -> bool:
    """Check if narrative analysis is available."""
    analyzer = get_narrative_analyzer()
    return analyzer.is_available()
