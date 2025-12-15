# Copyright (c) 2025 Stephen G. Pope
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.

"""
Block Manipulation Service for AutoEdit Pipeline

Handles operations on edit blocks:
- Adjust timestamps
- Split blocks
- Merge blocks
- Delete blocks
- Restore gaps (convert removed segment back to block)
- Calculate gaps from blocks
"""

import logging
import uuid
from typing import Dict, Any, List, Optional, Tuple
from copy import deepcopy

logger = logging.getLogger(__name__)


def generate_block_id() -> str:
    """Generate a unique block ID."""
    return f"b_{uuid.uuid4().hex[:8]}"


def calculate_gaps(
    blocks: List[Dict[str, Any]],
    video_duration_ms: int,
    transcript_words: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """Calculate gaps (removed segments) between blocks.

    Args:
        blocks: List of blocks with inMs/outMs
        video_duration_ms: Total video duration in milliseconds
        transcript_words: Optional transcript to get text of removed segments

    Returns:
        List of gaps with timestamps and metadata
    """
    # Validate transcript_words format - if malformed, skip text extraction
    if transcript_words and len(transcript_words) > 0:
        if not isinstance(transcript_words[0], dict):
            import logging
            logging.getLogger(__name__).warning(f"transcript_words has wrong format (first item is {type(transcript_words[0])}), skipping text extraction")
            transcript_words = None

    if not blocks:
        return [{
            "id": generate_block_id(),
            "inMs": 0,
            "outMs": video_duration_ms,
            "reason": "all_content_removed",
            "original_text": None
        }]

    # Validate blocks format
    if not isinstance(blocks[0], dict):
        import logging
        logging.getLogger(__name__).warning(f"blocks has wrong format (first item is {type(blocks[0])})")
        return []

    # Sort blocks by start time
    sorted_blocks = sorted(blocks, key=lambda b: b.get("inMs", 0))
    gaps = []

    # Gap at the beginning
    if sorted_blocks[0].get("inMs", 0) > 0:
        gaps.append({
            "id": generate_block_id(),
            "inMs": 0,
            "outMs": sorted_blocks[0]["inMs"],
            "reason": "removed_start",
            "original_text": _get_text_in_range(transcript_words, 0, sorted_blocks[0]["inMs"])
        })

    # Gaps between blocks
    for i in range(len(sorted_blocks) - 1):
        current_end = sorted_blocks[i]["outMs"]
        next_start = sorted_blocks[i + 1]["inMs"]

        if next_start > current_end:
            gaps.append({
                "id": generate_block_id(),
                "inMs": current_end,
                "outMs": next_start,
                "reason": "removed_middle",
                "original_text": _get_text_in_range(transcript_words, current_end, next_start)
            })

    # Gap at the end
    if sorted_blocks[-1]["outMs"] < video_duration_ms:
        gaps.append({
            "id": generate_block_id(),
            "inMs": sorted_blocks[-1]["outMs"],
            "outMs": video_duration_ms,
            "reason": "removed_end",
            "original_text": _get_text_in_range(transcript_words, sorted_blocks[-1]["outMs"], video_duration_ms)
        })

    return gaps


def _get_text_in_range(
    transcript_words: Optional[List[Dict[str, Any]]],
    start_ms: int,
    end_ms: int
) -> Optional[str]:
    """Get transcript text within a time range.

    Args:
        transcript_words: List of words with inMs/outMs
        start_ms: Start time in milliseconds
        end_ms: End time in milliseconds

    Returns:
        Concatenated text of words in range, or None
    """
    if not transcript_words:
        return None

    words_in_range = []
    for word in transcript_words:
        # Skip if word is not a dict (defensive against malformed data)
        if not isinstance(word, dict):
            continue
        word_start = word.get("inMs", word.get("start", 0) * 1000)
        word_end = word.get("outMs", word.get("end", 0) * 1000)

        # Word overlaps with range
        if word_end > start_ms and word_start < end_ms:
            words_in_range.append(word.get("text", ""))

    return " ".join(words_in_range) if words_in_range else None


def adjust_block(
    blocks: List[Dict[str, Any]],
    block_id: str,
    new_in_ms: Optional[int] = None,
    new_out_ms: Optional[int] = None
) -> Tuple[List[Dict[str, Any]], bool]:
    """Adjust timestamps of a block.

    Args:
        blocks: List of blocks
        block_id: ID of block to adjust
        new_in_ms: New start time (optional)
        new_out_ms: New end time (optional)

    Returns:
        Tuple of (updated blocks, success flag)
    """
    blocks = deepcopy(blocks)

    for block in blocks:
        if block.get("id") == block_id:
            if new_in_ms is not None:
                if new_in_ms >= block["outMs"]:
                    logger.warning(f"Invalid adjustment: new_in_ms {new_in_ms} >= outMs {block['outMs']}")
                    return blocks, False
                block["inMs"] = new_in_ms

            if new_out_ms is not None:
                if new_out_ms <= block["inMs"]:
                    logger.warning(f"Invalid adjustment: new_out_ms {new_out_ms} <= inMs {block['inMs']}")
                    return blocks, False
                block["outMs"] = new_out_ms

            logger.info(f"Adjusted block {block_id}: inMs={block['inMs']}, outMs={block['outMs']}")
            return blocks, True

    logger.warning(f"Block not found: {block_id}")
    return blocks, False


def split_block(
    blocks: List[Dict[str, Any]],
    block_id: str,
    split_at_ms: int
) -> Tuple[List[Dict[str, Any]], bool]:
    """Split a block into two at the specified time.

    Args:
        blocks: List of blocks
        block_id: ID of block to split
        split_at_ms: Time to split at (must be within block)

    Returns:
        Tuple of (updated blocks, success flag)
    """
    blocks = deepcopy(blocks)

    for i, block in enumerate(blocks):
        if block.get("id") == block_id:
            # Validate split point
            if split_at_ms <= block["inMs"] or split_at_ms >= block["outMs"]:
                logger.warning(f"Invalid split point {split_at_ms} for block [{block['inMs']}, {block['outMs']}]")
                return blocks, False

            # Create two new blocks
            block1 = {
                "id": generate_block_id(),
                "inMs": block["inMs"],
                "outMs": split_at_ms,
                "text": block.get("text", "")[:len(block.get("text", ""))//2] if block.get("text") else ""
            }
            block2 = {
                "id": generate_block_id(),
                "inMs": split_at_ms,
                "outMs": block["outMs"],
                "text": block.get("text", "")[len(block.get("text", ""))//2:] if block.get("text") else ""
            }

            # Replace original block with two new ones
            blocks[i:i+1] = [block1, block2]

            logger.info(f"Split block {block_id} at {split_at_ms}ms into {block1['id']} and {block2['id']}")
            return blocks, True

    logger.warning(f"Block not found: {block_id}")
    return blocks, False


def merge_blocks(
    blocks: List[Dict[str, Any]],
    block_ids: List[str]
) -> Tuple[List[Dict[str, Any]], bool]:
    """Merge multiple adjacent blocks into one.

    Args:
        blocks: List of blocks
        block_ids: IDs of blocks to merge (must be adjacent)

    Returns:
        Tuple of (updated blocks, success flag)
    """
    if len(block_ids) < 2:
        logger.warning("Need at least 2 blocks to merge")
        return blocks, False

    blocks = deepcopy(blocks)

    # Find blocks to merge
    blocks_to_merge = []
    indices_to_remove = []

    for i, block in enumerate(blocks):
        if block.get("id") in block_ids:
            blocks_to_merge.append(block)
            indices_to_remove.append(i)

    if len(blocks_to_merge) != len(block_ids):
        logger.warning(f"Not all blocks found. Requested: {block_ids}, Found: {len(blocks_to_merge)}")
        return blocks, False

    # Sort by start time
    blocks_to_merge.sort(key=lambda b: b["inMs"])

    # Check if they are adjacent (or at least ordered)
    for i in range(len(blocks_to_merge) - 1):
        if blocks_to_merge[i]["outMs"] > blocks_to_merge[i + 1]["inMs"]:
            logger.warning("Blocks are overlapping, cannot merge")
            return blocks, False

    # Create merged block
    merged_block = {
        "id": generate_block_id(),
        "inMs": blocks_to_merge[0]["inMs"],
        "outMs": blocks_to_merge[-1]["outMs"],
        "text": " ".join(b.get("text", "") for b in blocks_to_merge if b.get("text"))
    }

    # Remove old blocks and insert merged
    # Remove in reverse order to preserve indices
    for idx in sorted(indices_to_remove, reverse=True):
        blocks.pop(idx)

    # Find insertion point
    insert_idx = 0
    for i, block in enumerate(blocks):
        if block["inMs"] > merged_block["inMs"]:
            insert_idx = i
            break
        insert_idx = i + 1

    blocks.insert(insert_idx, merged_block)

    logger.info(f"Merged blocks {block_ids} into {merged_block['id']}")
    return blocks, True


def delete_block(
    blocks: List[Dict[str, Any]],
    block_id: str
) -> Tuple[List[Dict[str, Any]], bool]:
    """Delete a block (convert to gap).

    Args:
        blocks: List of blocks
        block_id: ID of block to delete

    Returns:
        Tuple of (updated blocks, success flag)
    """
    blocks = deepcopy(blocks)

    for i, block in enumerate(blocks):
        if block.get("id") == block_id:
            blocks.pop(i)
            logger.info(f"Deleted block {block_id}")
            return blocks, True

    logger.warning(f"Block not found: {block_id}")
    return blocks, False


def restore_gap(
    blocks: List[Dict[str, Any]],
    gaps: List[Dict[str, Any]],
    gap_id: str
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], bool]:
    """Restore a gap back to a block (un-delete segment).

    Args:
        blocks: List of blocks
        gaps: List of gaps
        gap_id: ID of gap to restore

    Returns:
        Tuple of (updated blocks, updated gaps, success flag)
    """
    blocks = deepcopy(blocks)
    gaps = deepcopy(gaps)

    for i, gap in enumerate(gaps):
        if gap.get("id") == gap_id:
            # Create new block from gap
            new_block = {
                "id": generate_block_id(),
                "inMs": gap["inMs"],
                "outMs": gap["outMs"],
                "text": gap.get("original_text", "")
            }

            # Remove from gaps
            gaps.pop(i)

            # Add to blocks in correct position
            blocks.append(new_block)
            blocks.sort(key=lambda b: b["inMs"])

            logger.info(f"Restored gap {gap_id} as block {new_block['id']}")
            return blocks, gaps, True

    logger.warning(f"Gap not found: {gap_id}")
    return blocks, gaps, False


def restore_gap_by_index(
    blocks: List[Dict[str, Any]],
    gaps: List[Dict[str, Any]],
    gap_index: int
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], bool]:
    """Restore a gap by index.

    Args:
        blocks: List of blocks
        gaps: List of gaps
        gap_index: Index of gap to restore

    Returns:
        Tuple of (updated blocks, updated gaps, success flag)
    """
    if gap_index < 0 or gap_index >= len(gaps):
        logger.warning(f"Invalid gap index: {gap_index}")
        return blocks, gaps, False

    gap_id = gaps[gap_index].get("id")
    if gap_id:
        return restore_gap(blocks, gaps, gap_id)
    else:
        # If gap has no ID, use index directly
        blocks = deepcopy(blocks)
        gaps = deepcopy(gaps)

        gap = gaps.pop(gap_index)
        new_block = {
            "id": generate_block_id(),
            "inMs": gap["inMs"],
            "outMs": gap["outMs"],
            "text": gap.get("original_text", "")
        }

        blocks.append(new_block)
        blocks.sort(key=lambda b: b["inMs"])

        logger.info(f"Restored gap at index {gap_index} as block {new_block['id']}")
        return blocks, gaps, True


def apply_modifications(
    blocks: List[Dict[str, Any]],
    gaps: List[Dict[str, Any]],
    modifications: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """Apply a list of modifications to blocks and gaps.

    Args:
        blocks: List of blocks
        gaps: List of gaps
        modifications: List of modification operations

    Returns:
        Tuple of (updated blocks, updated gaps, list of errors)

    Modification format:
        {"action": "adjust", "block_id": "...", "new_inMs": 100, "new_outMs": 500}
        {"action": "split", "block_id": "...", "split_at_ms": 300}
        {"action": "merge", "block_ids": ["b1", "b2"]}
        {"action": "delete", "block_id": "..."}
        {"action": "restore_gap", "gap_id": "..."} or {"action": "restore_gap", "gap_index": 0}
    """
    errors = []
    blocks = deepcopy(blocks)
    gaps = deepcopy(gaps)

    for i, mod in enumerate(modifications):
        action = mod.get("action")

        if action == "adjust":
            blocks, success = adjust_block(
                blocks,
                mod.get("block_id"),
                mod.get("new_inMs"),
                mod.get("new_outMs")
            )
            if not success:
                errors.append(f"Modification {i}: Failed to adjust block {mod.get('block_id')}")

        elif action == "split":
            blocks, success = split_block(
                blocks,
                mod.get("block_id"),
                mod.get("split_at_ms")
            )
            if not success:
                errors.append(f"Modification {i}: Failed to split block {mod.get('block_id')}")

        elif action == "merge":
            blocks, success = merge_blocks(blocks, mod.get("block_ids", []))
            if not success:
                errors.append(f"Modification {i}: Failed to merge blocks {mod.get('block_ids')}")

        elif action == "delete":
            blocks, success = delete_block(blocks, mod.get("block_id"))
            if not success:
                errors.append(f"Modification {i}: Failed to delete block {mod.get('block_id')}")

        elif action == "restore_gap":
            if "gap_id" in mod:
                blocks, gaps, success = restore_gap(blocks, gaps, mod["gap_id"])
            elif "gap_index" in mod:
                blocks, gaps, success = restore_gap_by_index(blocks, gaps, mod["gap_index"])
            else:
                success = False
            if not success:
                errors.append(f"Modification {i}: Failed to restore gap")

        else:
            errors.append(f"Modification {i}: Unknown action '{action}'")

    return blocks, gaps, errors


def ensure_block_ids(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ensure all blocks have unique IDs.

    Args:
        blocks: List of blocks

    Returns:
        Blocks with IDs added where missing
    """
    if not blocks:
        return []

    # Validate blocks format
    if not isinstance(blocks[0], dict):
        logger.warning(f"ensure_block_ids: blocks has wrong format (first item is {type(blocks[0])})")
        return blocks

    blocks = deepcopy(blocks)
    for block in blocks:
        if isinstance(block, dict) and not block.get("id"):
            block["id"] = generate_block_id()
    return blocks


def calculate_stats(
    blocks: List[Dict[str, Any]],
    video_duration_ms: int
) -> Dict[str, Any]:
    """Calculate statistics from blocks.

    Args:
        blocks: List of blocks
        video_duration_ms: Total video duration

    Returns:
        Statistics dictionary
    """
    if not blocks:
        return {
            "total_blocks": 0,
            "original_duration_ms": video_duration_ms,
            "result_duration_ms": 0,
            "removed_duration_ms": video_duration_ms,
            "removal_percentage": 100.0
        }

    # Validate blocks format
    if not isinstance(blocks[0], dict):
        logger.warning(f"calculate_stats: blocks has wrong format (first item is {type(blocks[0])})")
        return {
            "total_blocks": 0,
            "original_duration_ms": video_duration_ms,
            "result_duration_ms": 0,
            "removed_duration_ms": video_duration_ms,
            "removal_percentage": 100.0,
            "error": "invalid_blocks_format"
        }

    result_duration = sum(b.get("outMs", 0) - b.get("inMs", 0) for b in blocks if isinstance(b, dict))
    removed_duration = video_duration_ms - result_duration

    return {
        "total_blocks": len(blocks),
        "original_duration_ms": video_duration_ms,
        "result_duration_ms": result_duration,
        "removed_duration_ms": removed_duration,
        "removal_percentage": round((removed_duration / video_duration_ms) * 100, 2) if video_duration_ms > 0 else 0
    }


def add_preview_positions(
    blocks: List[Dict[str, Any]],
    fade_duration_ms: float = 25.0
) -> List[Dict[str, Any]]:
    """Add preview_inMs field to blocks showing position in rendered preview.

    The preview position accounts for crossfade overlap between segments.

    Args:
        blocks: List of blocks
        fade_duration_ms: Duration of crossfade in milliseconds

    Returns:
        Blocks with preview_inMs field added
    """
    if not blocks:
        return []

    # Validate blocks format
    if not isinstance(blocks[0], dict):
        logger.warning(f"add_preview_positions: blocks has wrong format (first item is {type(blocks[0])})")
        return blocks

    blocks = deepcopy(blocks)
    sorted_blocks = sorted(blocks, key=lambda b: b.get("inMs", 0))

    preview_position = 0
    for i, block in enumerate(sorted_blocks):
        block["preview_inMs"] = preview_position
        block_duration = block["outMs"] - block["inMs"]

        # Account for crossfade overlap (except for last block)
        if i < len(sorted_blocks) - 1:
            preview_position += block_duration - fade_duration_ms
        else:
            preview_position += block_duration

    return sorted_blocks
