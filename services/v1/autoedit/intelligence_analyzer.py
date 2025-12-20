# Copyright (c) 2025 Stephen G. Pope
# Licensed under GPL-2.0

"""
Intelligence Analyzer Service for AutoEdit Phase 5

Uses LLM (Gemini) to make intelligent decisions about redundant content selection.
Instead of simple "first occurrence wins", this analyzer evaluates:
- Delivery quality (fluency, pacing, articulation)
- Content completeness (information density, clarity)
- Contextual coherence (transitions, narrative position)
- Production quality (audio clarity, engagement)

Integrates with FAISS for similarity search and Neo4j for relationship storage.
"""

import os
import json
import logging
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# Prompt file path
PROMPT_FILE = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..",
    "infrastructure", "prompts", "autoedit_redundancy_selector_prompt.txt"
)


class IntelligenceAnalyzer:
    """
    LLM-powered analyzer for intelligent redundancy selection.

    Uses Gemini to analyze multiple versions of similar content and
    recommend which version to keep based on quality metrics.
    """

    def __init__(self):
        self._prompt_template = None
        self._model = None

    def _load_prompt(self) -> str:
        """Load the redundancy selector prompt template."""
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
                    logger.warning("GEMINI_API_KEY not set, intelligence analysis disabled")
                    return None

                genai.configure(api_key=api_key)
                self._model = genai.GenerativeModel("gemini-2.0-flash")
                logger.info("Initialized Gemini model for intelligence analysis")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini: {e}")
                return None

        return self._model

    def is_available(self) -> bool:
        """Check if the intelligence analyzer is available."""
        return self._get_model() is not None

    # =========================================================================
    # REDUNDANCY ANALYSIS
    # =========================================================================

    def analyze_redundant_segments(
        self,
        segments: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze redundant segments and recommend which to keep.

        Args:
            segments: List of similar segments with:
                - segment_id: Unique identifier
                - text: Transcribed content
                - in_ms / out_ms: Timestamps
                - context_before: Previous segment text (optional)
                - context_after: Following segment text (optional)
                - embedding_similarity: Similarity score (optional)
            context: Optional project/creator context

        Returns:
            Analysis result with recommendation or None on failure
        """
        model = self._get_model()
        if not model:
            logger.warning("Model not available, using fallback selection")
            return self._fallback_selection(segments)

        if len(segments) < 2:
            logger.warning("Need at least 2 segments for redundancy analysis")
            return None

        try:
            # Prepare the input
            input_data = {
                "segments": [
                    {
                        "segment_id": seg.get("segment_id", seg.get("id")),
                        "text": seg.get("text", ""),
                        "in_ms": seg.get("in_ms", seg.get("in", 0)),
                        "out_ms": seg.get("out_ms", seg.get("out", 0)),
                        "duration_ms": seg.get("out_ms", seg.get("out", 0)) - seg.get("in_ms", seg.get("in", 0)),
                        "context_before": seg.get("context_before", ""),
                        "context_after": seg.get("context_after", ""),
                        "embedding_similarity": seg.get("similarity", seg.get("embedding_similarity", 0.0))
                    }
                    for seg in segments
                ],
                "context": context or {}
            }

            # Build the full prompt
            prompt = self._load_prompt()
            full_prompt = f"{prompt}\n\n## Input Data\n\n```json\n{json.dumps(input_data, indent=2)}\n```\n\nAnalyze these segments and provide your recommendation."

            # Call the model
            response = model.generate_content(
                full_prompt,
                generation_config={
                    "temperature": 0.3,  # Lower for more consistent analysis
                    "max_output_tokens": 2000
                }
            )

            # Parse response
            result = self._parse_response(response.text)

            if result:
                result["analyzed_at"] = datetime.utcnow().isoformat()
                result["segment_count"] = len(segments)
                logger.info(f"Redundancy analysis complete: keep {result.get('recommendation', {}).get('keep_segment_id')}")

            return result

        except Exception as e:
            logger.error(f"Redundancy analysis failed: {e}")
            return self._fallback_selection(segments)

    def analyze_redundancy_batch(
        self,
        redundancy_groups: List[List[Dict[str, Any]]],
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Analyze multiple groups of redundant segments.

        Args:
            redundancy_groups: List of segment groups (each group contains similar segments)
            context: Optional project/creator context

        Returns:
            List of analysis results, one per group
        """
        results = []

        for i, group in enumerate(redundancy_groups):
            logger.info(f"Analyzing redundancy group {i+1}/{len(redundancy_groups)}")

            result = self.analyze_redundant_segments(group, context)
            if result:
                result["group_index"] = i
                results.append(result)

        return results

    def _parse_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Parse the LLM response into structured data."""
        try:
            # Try to extract JSON from response
            text = response_text.strip()

            # Look for JSON block
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
            logger.warning("Failed to parse LLM response as JSON")
            # Try to extract key information manually
            return self._extract_from_text(response_text)

    def _extract_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract recommendation from non-JSON response."""
        # Very basic extraction - look for segment IDs and confidence
        result = {
            "recommendation": {
                "keep_segment_id": None,
                "remove_segment_ids": [],
                "confidence": 0.5,
                "primary_reason": "Extracted from text response"
            },
            "parsing_note": "Response was not valid JSON, extracted manually"
        }

        # Look for segment ID mentions
        import re
        segment_ids = re.findall(r'segment[_\-]?(\w+)', text.lower())
        if segment_ids:
            result["recommendation"]["keep_segment_id"] = f"segment_{segment_ids[0]}"

        return result if result["recommendation"]["keep_segment_id"] else None

    def _fallback_selection(self, segments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Fallback selection when LLM is not available.

        Uses simple heuristics:
        - Prefer shorter segments (more concise)
        - Prefer segments with more context
        - First occurrence as tiebreaker
        """
        if not segments:
            return None

        # Score each segment
        scored = []
        for seg in segments:
            duration = seg.get("out_ms", seg.get("out", 0)) - seg.get("in_ms", seg.get("in", 0))
            text = seg.get("text", "")
            has_context = bool(seg.get("context_before") or seg.get("context_after"))

            # Lower score = better (we want shorter, with context)
            score = duration / 1000  # Penalize length
            if has_context:
                score -= 5  # Bonus for context
            if len(text.split()) > 10:
                score -= 2  # Bonus for substantive content

            scored.append((seg, score))

        # Sort by score (lower is better)
        scored.sort(key=lambda x: x[1])

        winner = scored[0][0]
        losers = [s[0] for s in scored[1:]]

        return {
            "recommendation": {
                "keep_segment_id": winner.get("segment_id", winner.get("id")),
                "remove_segment_ids": [s.get("segment_id", s.get("id")) for s in losers],
                "confidence": 0.4,
                "primary_reason": "Fallback selection based on length and context heuristics"
            },
            "fallback_used": True,
            "analyzed_at": datetime.utcnow().isoformat()
        }

    # =========================================================================
    # QUALITY SCORING
    # =========================================================================

    def score_segment_quality(
        self,
        segment: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Score a single segment's quality across multiple dimensions.

        Args:
            segment: Segment data with text and metadata
            context: Optional context for evaluation

        Returns:
            Quality scores or None on failure
        """
        model = self._get_model()
        if not model:
            return None

        try:
            prompt = f"""Analyze this video segment and score its quality.

Segment:
- Text: {segment.get('text', '')}
- Duration: {segment.get('out_ms', 0) - segment.get('in_ms', 0)}ms

Score each dimension from 1-5:
1. Delivery: Fluency, pacing, articulation (no fillers, natural rhythm)
2. Completeness: Information density, clarity, examples
3. Coherence: Logical flow, transitions
4. Engagement: Energy, enthusiasm, authenticity

Respond with JSON only:
{{
  "scores": {{
    "delivery": 4,
    "completeness": 3,
    "coherence": 4,
    "engagement": 3
  }},
  "overall": 3.5,
  "notes": "Brief observations"
}}"""

            response = model.generate_content(
                prompt,
                generation_config={"temperature": 0.2, "max_output_tokens": 500}
            )

            return self._parse_response(response.text)

        except Exception as e:
            logger.error(f"Quality scoring failed: {e}")
            return None

    # =========================================================================
    # INTEGRATION WITH FAISS
    # =========================================================================

    def find_and_analyze_redundancies(
        self,
        project_id: str,
        similarity_threshold: float = 0.85,
        max_groups: int = 20
    ) -> Dict[str, Any]:
        """
        Find redundant segments using FAISS and analyze each group.

        Args:
            project_id: Project identifier
            similarity_threshold: Minimum similarity to consider redundant
            max_groups: Maximum number of groups to analyze

        Returns:
            Complete redundancy analysis for the project
        """
        try:
            from services.v1.autoedit.faiss_manager import get_faiss_manager

            faiss_mgr = get_faiss_manager()
            if not faiss_mgr.is_available():
                return {"error": "FAISS not available", "groups": []}

            # Find redundant pairs
            pairs = faiss_mgr.find_redundant_pairs(project_id, similarity_threshold)

            if not pairs:
                return {
                    "project_id": project_id,
                    "groups": [],
                    "message": "No redundant segments found"
                }

            # Group related segments
            groups = self._group_redundant_pairs(pairs, max_groups)

            # Analyze each group
            results = []
            for group in groups:
                analysis = self.analyze_redundant_segments(group["segments"])
                if analysis:
                    results.append({
                        "group_id": group["group_id"],
                        "segments": group["segments"],
                        "analysis": analysis
                    })

            return {
                "project_id": project_id,
                "threshold": similarity_threshold,
                "total_pairs": len(pairs),
                "groups_analyzed": len(results),
                "groups": results,
                "analyzed_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Find and analyze failed: {e}")
            return {"error": str(e), "groups": []}

    def _group_redundant_pairs(
        self,
        pairs: List[Dict[str, Any]],
        max_groups: int
    ) -> List[Dict[str, Any]]:
        """Group redundant pairs into clusters of related segments."""
        from collections import defaultdict

        # Build adjacency list
        adjacency = defaultdict(set)
        for pair in pairs:
            seg_a = pair["segment_a"]
            seg_b = pair["segment_b"]
            adjacency[seg_a].add(seg_b)
            adjacency[seg_b].add(seg_a)

        # Find connected components (groups)
        visited = set()
        groups = []

        for segment in adjacency:
            if segment in visited:
                continue

            # BFS to find all connected segments
            group = set()
            queue = [segment]

            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                group.add(current)

                for neighbor in adjacency[current]:
                    if neighbor not in visited:
                        queue.append(neighbor)

            if len(group) >= 2:
                groups.append({
                    "group_id": f"group_{len(groups)}",
                    "segments": [{"segment_id": seg_id} for seg_id in group],
                    "size": len(group)
                })

        # Sort by size and limit
        groups.sort(key=lambda x: x["size"], reverse=True)
        return groups[:max_groups]


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_analyzer = None


def get_intelligence_analyzer() -> IntelligenceAnalyzer:
    """Get the singleton IntelligenceAnalyzer instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = IntelligenceAnalyzer()
    return _analyzer


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def analyze_redundancy(
    segments: List[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Analyze redundant segments and get recommendation.

    Args:
        segments: List of similar segments
        context: Optional context

    Returns:
        Analysis result with keep/remove recommendation
    """
    analyzer = get_intelligence_analyzer()
    return analyzer.analyze_redundant_segments(segments, context)


def find_project_redundancies(
    project_id: str,
    threshold: float = 0.85
) -> Dict[str, Any]:
    """
    Find and analyze all redundancies in a project.

    Args:
        project_id: Project identifier
        threshold: Similarity threshold

    Returns:
        Complete redundancy analysis
    """
    analyzer = get_intelligence_analyzer()
    return analyzer.find_and_analyze_redundancies(project_id, threshold)


def is_intelligence_available() -> bool:
    """Check if intelligence analysis is available."""
    analyzer = get_intelligence_analyzer()
    return analyzer.is_available()
