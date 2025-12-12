# Copyright (c) 2025 Stephen G. Pope
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

"""
Map Timestamps Service for AutoEdit pipeline.

Maps Gemini's XML output (<mantener>/<eliminar>) back to actual timestamps
using word-level alignment from the original Whisper transcription.
"""

import re
import logging
from typing import Dict, Any, List, Tuple, Optional
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


def parse_xml_output(output_xml: str) -> List[Dict[str, Any]]:
    """
    Parse the outputXML string into a list of actions.

    Args:
        output_xml: XML string like "<resultado><mantener>text</mantener><eliminar>text</eliminar>...</resultado>"

    Returns:
        List of dicts with 'action' (keep/remove) and 'text'
    """
    actions = []

    # Extract content inside <resultado>
    resultado_match = re.search(r'<resultado>(.*?)</resultado>', output_xml, re.DOTALL)
    if not resultado_match:
        logger.warning(f"No <resultado> tag found in: {output_xml[:100]}...")
        return actions

    content = resultado_match.group(1)

    # Find all <mantener> and <eliminar> tags in order
    pattern = r'<(mantener|eliminar)>(.*?)</\1>'
    for match in re.finditer(pattern, content, re.DOTALL):
        tag = match.group(1)
        text = match.group(2).strip()

        if text:
            actions.append({
                "action": "keep" if tag == "mantener" else "remove",
                "text": text
            })

    return actions


def normalize_text(text: str) -> str:
    """
    Normalize text for comparison.

    Args:
        text: Input text

    Returns:
        Normalized text (lowercase, single spaces, no extra punctuation)
    """
    # Convert to lowercase
    normalized = text.lower()

    # Remove quotes that Gemini sometimes adds
    normalized = normalized.replace('"', '').replace("'", '')

    # Normalize whitespace
    normalized = ' '.join(normalized.split())

    return normalized


def find_text_in_words(
    search_text: str,
    words: List[Dict[str, Any]],
    start_idx: int = 0
) -> Tuple[Optional[int], Optional[int], float]:
    """
    Find a text fragment in the word list using fuzzy matching.

    Args:
        search_text: Text to find
        words: List of word dicts with 'word', 'start', 'end'
        start_idx: Index to start searching from

    Returns:
        Tuple of (start_word_idx, end_word_idx, confidence)
        Returns (None, None, 0) if not found
    """
    if not words or not search_text:
        return None, None, 0

    search_normalized = normalize_text(search_text)
    search_words = search_normalized.split()

    if not search_words:
        return None, None, 0

    best_match = (None, None, 0)

    # Try different starting positions
    for i in range(start_idx, len(words)):
        # Build candidate text from consecutive words
        for j in range(i + 1, min(i + len(search_words) + 5, len(words) + 1)):
            candidate_words = words[i:j]
            candidate_text = ' '.join(normalize_text(w.get('word', '')) for w in candidate_words)

            # Calculate similarity
            similarity = SequenceMatcher(None, search_normalized, candidate_text).ratio()

            # Exact match or very high similarity
            if similarity > 0.9:
                return i, j - 1, similarity

            # Track best match
            if similarity > best_match[2] and similarity > 0.6:
                best_match = (i, j - 1, similarity)

    return best_match


def map_block_to_timestamps(
    xml_actions: List[Dict[str, Any]],
    original_segments: List[Dict[str, Any]],
    segment_indices: List[int]
) -> List[Dict[str, Any]]:
    """
    Map XML actions to timestamps using original segments.

    Args:
        xml_actions: List of action dicts with 'action' and 'text'
        original_segments: Full list of original transcription segments
        segment_indices: Indices of segments belonging to this block

    Returns:
        List of mapped segments with action, text, start, end
    """
    mapped = []

    if not segment_indices or not original_segments:
        return mapped

    # Collect all words from the relevant segments
    all_words = []
    for idx in segment_indices:
        if idx < len(original_segments):
            seg = original_segments[idx]
            # If segment has word-level timestamps
            if 'words' in seg:
                for word in seg['words']:
                    all_words.append({
                        "word": word.get('word', word.get('text', '')),
                        "start": word.get('start', seg['start']),
                        "end": word.get('end', seg['end'])
                    })
            else:
                # Fall back to segment-level
                words_in_seg = seg.get('text', '').split()
                seg_duration = seg['end'] - seg['start']
                word_duration = seg_duration / len(words_in_seg) if words_in_seg else 0

                for i, w in enumerate(words_in_seg):
                    all_words.append({
                        "word": w,
                        "start": seg['start'] + i * word_duration,
                        "end": seg['start'] + (i + 1) * word_duration
                    })

    if not all_words:
        return mapped

    # Map each action to timestamps
    current_word_idx = 0

    for action in xml_actions:
        action_text = action['text']
        action_type = action['action']

        # Find this text in the word list
        start_idx, end_idx, confidence = find_text_in_words(
            action_text,
            all_words,
            current_word_idx
        )

        if start_idx is not None and end_idx is not None:
            mapped.append({
                "action": action_type,
                "text": action_text,
                "start": all_words[start_idx]['start'],
                "end": all_words[end_idx]['end'],
                "confidence": confidence
            })
            current_word_idx = end_idx + 1
        else:
            logger.warning(f"Could not map text to timestamps: '{action_text[:50]}...'")
            # Still include it with estimated timestamps based on position
            if mapped:
                last_end = mapped[-1]['end']
            elif segment_indices and segment_indices[0] < len(original_segments):
                last_end = original_segments[segment_indices[0]]['start']
            else:
                last_end = 0

            mapped.append({
                "action": action_type,
                "text": action_text,
                "start": last_end,
                "end": last_end + 1.0,  # Estimate 1 second
                "confidence": 0.0
            })

    return mapped


def map_gemini_output_to_timestamps(
    gemini_blocks: List[Dict[str, Any]],
    original_transcription: Dict[str, Any],
    block_to_segment_map: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Main function: map all Gemini XML blocks to timestamps.

    Args:
        gemini_blocks: List of block dicts with blockID and outputXML
        original_transcription: Original transcription with segments
        block_to_segment_map: Optional pre-computed mapping from prepare_blocks

    Returns:
        Dict with mapped segments and summary
    """
    logger.info(f"Mapping {len(gemini_blocks)} blocks to timestamps")

    original_segments = original_transcription.get('segments', [])
    all_mapped = []

    # Track which segments we've processed
    processed_segment_idx = 0

    for block in gemini_blocks:
        block_id = block.get('blockID', '')
        output_xml = block.get('outputXML', '')

        # Parse XML actions
        xml_actions = parse_xml_output(output_xml)

        if not xml_actions:
            logger.warning(f"No actions found in block {block_id}")
            continue

        # Get segment indices for this block
        if block_to_segment_map and block_id in block_to_segment_map:
            segment_indices = block_to_segment_map[block_id].get('segment_indices', [])
        else:
            # Estimate based on block text
            block_text = ' '.join(a['text'] for a in xml_actions)
            segment_indices = []

            # Find matching segments
            for i in range(processed_segment_idx, len(original_segments)):
                seg_text = original_segments[i].get('text', '')
                if seg_text.strip() in block_text or block_text in seg_text.strip():
                    segment_indices.append(i)
                    processed_segment_idx = i + 1
                elif segment_indices:
                    # We've moved past this block
                    break

            if not segment_indices and processed_segment_idx < len(original_segments):
                # Fallback: use next segment
                segment_indices = [processed_segment_idx]
                processed_segment_idx += 1

        # Map actions to timestamps
        mapped_segments = map_block_to_timestamps(
            xml_actions,
            original_segments,
            segment_indices
        )

        # Add block metadata
        for seg in mapped_segments:
            seg['blockID'] = block_id
            seg['speaker'] = block.get('speaker', 'UNKNOWN')

        all_mapped.extend(mapped_segments)

    # Calculate summary
    keep_segments = [s for s in all_mapped if s['action'] == 'keep']
    remove_segments = [s for s in all_mapped if s['action'] == 'remove']

    keep_duration = sum(s['end'] - s['start'] for s in keep_segments)
    remove_duration = sum(s['end'] - s['start'] for s in remove_segments)
    total_duration = keep_duration + remove_duration

    summary = {
        "kept_count": len(keep_segments),
        "removed_count": len(remove_segments),
        "kept_duration": round(keep_duration, 2),
        "removed_duration": round(remove_duration, 2),
        "total_duration": round(total_duration, 2),
        "keep_ratio": round(keep_duration / total_duration, 2) if total_duration > 0 else 1.0
    }

    logger.info(f"Mapped {len(all_mapped)} segments: {summary['kept_count']} keep, {summary['removed_count']} remove")

    return {
        "segments": all_mapped,
        "summary": summary
    }


def generate_cuts_from_mapped_segments(
    mapped_segments: List[Dict[str, Any]],
    video_duration: Optional[float] = None,
    padding_before_ms: int = 90,
    padding_after_ms: int = 90,
    merge_threshold_ms: int = 100
) -> List[Dict[str, str]]:
    """
    Generate FFmpeg cuts from mapped segments.

    The /v1/video/cut endpoint REMOVES specified segments.
    So we send the 'remove' segments as cuts.

    Args:
        mapped_segments: Output from map_gemini_output_to_timestamps
        video_duration: Optional video duration for final cut
        padding_before_ms: Padding to add before each cut
        padding_after_ms: Padding to add after each cut
        merge_threshold_ms: Merge cuts closer than this

    Returns:
        List of cut dicts with 'start' and 'end' as strings
    """
    # Filter for remove segments
    remove_segments = [s for s in mapped_segments if s['action'] == 'remove']

    if not remove_segments:
        return []

    # Sort by start time
    remove_segments.sort(key=lambda x: x['start'])

    # Apply padding and merge
    cuts = []
    padding_before = padding_before_ms / 1000.0
    padding_after = padding_after_ms / 1000.0
    merge_threshold = merge_threshold_ms / 1000.0

    for seg in remove_segments:
        start = max(0, seg['start'] - padding_before)
        end = seg['end'] + padding_after

        if video_duration:
            end = min(end, video_duration)

        # Check if we should merge with previous cut
        if cuts and start - cuts[-1]['end_float'] < merge_threshold:
            # Merge
            cuts[-1]['end_float'] = end
            cuts[-1]['end'] = str(round(end, 3))
        else:
            cuts.append({
                "start": str(round(start, 3)),
                "end": str(round(end, 3)),
                "start_float": start,
                "end_float": end
            })

    # Remove internal tracking fields
    for cut in cuts:
        del cut['start_float']
        del cut['end_float']

    logger.info(f"Generated {len(cuts)} cuts from {len(remove_segments)} remove segments")

    return cuts
