# Copyright (c) 2025 Stephen G. Pope
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

"""
Prepare Blocks Service for AutoEdit pipeline.

Transforms transcription with speakers into text blocks for Gemini analysis.
IMPORTANT: Output contains ONLY TEXT - no timestamps.
This separates semantic analysis (Gemini) from timestamp mapping (later step).
"""

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def group_segments_into_blocks(
    segments: List[Dict[str, Any]],
    merge_same_speaker: bool = True,
    max_block_duration: float = 60.0
) -> List[Dict[str, Any]]:
    """
    Group transcription segments into speaker blocks.

    Consecutive segments from the same speaker are merged into single blocks
    to reduce the number of blocks Gemini needs to process.

    Args:
        segments: Transcription segments with 'speaker', 'text', 'start', 'end'
        merge_same_speaker: Whether to merge consecutive same-speaker segments
        max_block_duration: Maximum duration for a single block (seconds)

    Returns:
        List of blocks with blockID, speaker, text (NO timestamps in text)
    """
    if not segments:
        return []

    blocks = []
    current_block = None

    for seg in segments:
        speaker = seg.get('speaker', 'UNKNOWN')
        text = seg.get('text', '').strip()
        start = seg.get('start', 0)
        end = seg.get('end', 0)

        if not text:
            continue

        # Check if we should merge with current block
        should_merge = (
            merge_same_speaker and
            current_block is not None and
            current_block['speaker'] == speaker and
            (end - current_block['_start']) <= max_block_duration
        )

        if should_merge:
            # Append to current block
            current_block['text'] += ' ' + text
            current_block['_end'] = end
            current_block['_segment_count'] += 1
        else:
            # Save current block if exists
            if current_block is not None:
                # Remove internal tracking fields before adding to blocks
                block_data = {
                    "blockID": str(len(blocks)),
                    "speaker": current_block['speaker'],
                    "text": current_block['text']
                }
                blocks.append(block_data)

            # Start new block
            current_block = {
                "speaker": speaker,
                "text": text,
                "_start": start,
                "_end": end,
                "_segment_count": 1
            }

    # Don't forget the last block
    if current_block is not None:
        block_data = {
            "blockID": str(len(blocks)),
            "speaker": current_block['speaker'],
            "text": current_block['text']
        }
        blocks.append(block_data)

    logger.info(f"Grouped {len(segments)} segments into {len(blocks)} blocks")

    return blocks


def format_blocks_for_gemini(blocks: List[Dict[str, Any]]) -> str:
    """
    Format blocks into the text format expected by Gemini.

    This produces the input format that matches the original Make.com system:
    0: Text from first block...
    1: Text from second block...

    Args:
        blocks: List of block dicts with blockID, speaker, text

    Returns:
        Formatted string for Gemini input
    """
    lines = []

    for block in blocks:
        block_id = block['blockID']
        text = block['text']
        lines.append(f"{block_id}: {text}")

    return '\n'.join(lines)


def prepare_blocks_for_analysis(
    transcription: Dict[str, Any],
    merge_same_speaker: bool = True,
    max_block_duration: float = 60.0
) -> Dict[str, Any]:
    """
    Main function: prepare transcription for Gemini analysis.

    Takes full transcription output and prepares:
    1. Text blocks (ONLY TEXT, no timestamps) for Gemini
    2. Metadata for later timestamp mapping

    Args:
        transcription: Full transcription dict with 'segments' array
        merge_same_speaker: Whether to merge consecutive same-speaker segments
        max_block_duration: Maximum duration for merged blocks

    Returns:
        Dict containing:
        - blocks: List of block dicts for Gemini
        - formatted_text: String formatted for Gemini input
        - original_segments: Original segments (preserved for timestamp mapping)
        - block_to_segment_map: Mapping for later timestamp recovery
    """
    segments = transcription.get('segments', [])

    if not segments:
        return {
            "blocks": [],
            "formatted_text": "",
            "original_segments": [],
            "block_to_segment_map": {},
            "total_blocks": 0
        }

    # Group into blocks
    blocks = group_segments_into_blocks(
        segments,
        merge_same_speaker=merge_same_speaker,
        max_block_duration=max_block_duration
    )

    # Format for Gemini
    formatted_text = format_blocks_for_gemini(blocks)

    # Create mapping from blocks back to original segments
    # This is crucial for timestamp recovery after Gemini analysis
    block_to_segment_map = {}
    current_segment_idx = 0

    for block in blocks:
        block_id = block['blockID']
        block_speaker = block['speaker']
        block_text = block['text']

        # Find matching segments
        matching_segment_indices = []
        accumulated_text = ""

        while current_segment_idx < len(segments):
            seg = segments[current_segment_idx]

            # Check if this segment belongs to this block
            if seg.get('speaker') == block_speaker or not matching_segment_indices:
                accumulated_text += ' ' + seg.get('text', '').strip()
                matching_segment_indices.append(current_segment_idx)
                current_segment_idx += 1

                # Check if we've accumulated all the text for this block
                if block_text.strip() in accumulated_text.strip():
                    break
            else:
                break

        block_to_segment_map[block_id] = {
            "segment_indices": matching_segment_indices,
            "speaker": block_speaker
        }

    return {
        "blocks": blocks,
        "formatted_text": formatted_text,
        "original_segments": segments,
        "block_to_segment_map": block_to_segment_map,
        "total_blocks": len(blocks),
        "total_original_segments": len(segments)
    }
