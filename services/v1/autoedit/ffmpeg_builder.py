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
FFmpeg Builder for AutoEdit Pipeline

Builds FFmpeg compose payloads with crossfade support and multiple render profiles.
Implements the "separate inputs" technique for audio crossfade without A/V drift.

CROSSFADE TECHNIQUE:
- Video uses exact cut times (inputs 0 to n-1)
- Audio uses extended times to compensate for crossfade overlap (inputs n to 2n-1)
- acrossfade "consumes" the extensions, preserving original content duration
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# =============================================================================
# RENDER PROFILES
# =============================================================================

RENDER_PROFILES = {
    "preview": {
        "scale": "854:480",       # 480p
        "crf": 30,                # Low quality, small file
        "preset": "ultrafast",    # Maximum speed
        "audio_bitrate": "64k",
        "video_codec": "libx264",
        "pix_fmt": "yuv420p",
        "estimated_speed": "10-20x realtime"
    },
    "preview_720p": {
        "scale": "1280:720",      # 720p
        "crf": 28,
        "preset": "veryfast",
        "audio_bitrate": "96k",
        "video_codec": "libx264",
        "pix_fmt": "yuv420p",
        "estimated_speed": "5-10x realtime"
    },
    "standard": {
        "scale": None,            # Keep original resolution
        "crf": 23,                # Standard quality
        "preset": "medium",
        "audio_bitrate": "192k",
        "video_codec": "libx264",
        "pix_fmt": "yuv420p",
        "estimated_speed": "2-4x realtime"
    },
    "high": {
        "scale": None,
        "crf": 18,                # High quality
        "preset": "slow",
        "audio_bitrate": "256k",
        "video_codec": "libx264",
        "pix_fmt": "yuv420p",
        "estimated_speed": "0.5-1x realtime"
    },
    "4k": {
        "scale": None,
        "crf": 16,                # Maximum quality
        "preset": "slow",
        "audio_bitrate": "320k",
        "video_codec": "libx264",
        "pix_fmt": "yuv420p",
        "estimated_speed": "0.2-0.5x realtime"
    }
}


def get_render_profile(profile_name: str) -> Dict[str, Any]:
    """Get render profile settings by name.

    Args:
        profile_name: One of 'preview', 'preview_720p', 'standard', 'high', '4k'

    Returns:
        Dict with render settings

    Raises:
        ValueError: If profile_name is not recognized
    """
    if profile_name not in RENDER_PROFILES:
        valid_profiles = ", ".join(RENDER_PROFILES.keys())
        raise ValueError(f"Unknown render profile '{profile_name}'. Valid: {valid_profiles}")
    return RENDER_PROFILES[profile_name].copy()


# =============================================================================
# PAYLOAD BUILDERS
# =============================================================================

def build_ffmpeg_compose_payload(
    video_url: str,
    cuts: List[Dict[str, str]],
    profile: str = "standard",
    fade_duration: float = 0.025,
    use_stream_copy: bool = False
) -> Dict[str, Any]:
    """Build FFmpeg compose payload with audio crossfade.

    Implements the "separate inputs" technique:
    - Video inputs (0 to n-1): exact cut times
    - Audio inputs (n to 2n-1): extended times to compensate for crossfade overlap
    - acrossfade consumes the extensions, preserving original content duration

    Args:
        video_url: URL of the source video
        cuts: List of cuts [{"start": "5.72", "end": "7.22"}, ...]
        profile: Render profile name ('preview', 'standard', 'high', '4k')
        fade_duration: Duration of audio crossfade in seconds (default 0.025s = 25ms)
        use_stream_copy: If True, attempt -c copy for single cut (faster)

    Returns:
        Dict payload for /v1/ffmpeg/compose endpoint
    """
    if not cuts:
        raise ValueError("At least one cut is required")

    render_settings = get_render_profile(profile)

    inputs = []
    n_cuts = len(cuts)
    durations = []

    # Build video inputs (exact times)
    for cut in cuts:
        start = float(cut["start"])
        end = float(cut["end"])
        duration = end - start
        durations.append(duration)

        inputs.append({
            "file_url": video_url,
            "options": [
                {"option": "-ss", "argument": str(start)},
                {"option": "-t", "argument": str(duration)}
            ]
        })

    # Single cut: stream copy (fastest) or encode based on profile
    if n_cuts == 1:
        if use_stream_copy:
            return {
                "inputs": inputs,
                "outputs": [{
                    "options": [
                        {"option": "-c", "argument": "copy"},
                        {"option": "-avoid_negative_ts", "argument": "make_zero"}
                    ]
                }]
            }
        else:
            return _build_single_cut_encode_payload(inputs, render_settings)

    # Multiple cuts: crossfade with separate video/audio inputs
    return _build_crossfade_payload(
        video_url, cuts, durations, inputs, n_cuts,
        fade_duration, render_settings
    )


def _build_single_cut_encode_payload(
    inputs: List[Dict],
    render_settings: Dict[str, Any]
) -> Dict[str, Any]:
    """Build payload for single cut with encoding (no crossfade needed)."""
    output_options = [
        {"option": "-c:v", "argument": render_settings["video_codec"]},
        {"option": "-preset", "argument": render_settings["preset"]},
        {"option": "-crf", "argument": str(render_settings["crf"])},
        {"option": "-pix_fmt", "argument": render_settings["pix_fmt"]},
        {"option": "-c:a", "argument": "aac"},
        {"option": "-b:a", "argument": render_settings["audio_bitrate"]}
    ]

    # Add scale filter if specified
    if render_settings["scale"]:
        width, height = render_settings["scale"].split(":")
        output_options.insert(0, {
            "option": "-vf",
            "argument": f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
        })

    return {
        "inputs": inputs,
        "outputs": [{"options": output_options}]
    }


def _build_crossfade_payload(
    video_url: str,
    cuts: List[Dict[str, str]],
    durations: List[float],
    inputs: List[Dict],
    n_cuts: int,
    fade_duration: float,
    render_settings: Dict[str, Any]
) -> Dict[str, Any]:
    """Build payload for multiple cuts with audio crossfade.

    AUDIO CROSSFADE TECHNIQUE:
    The problem with acrossfade is that it shortens the audio because segments overlap.
    Solution: Extend AUDIO segments so that the crossfade "consumes" the extensions,
    not the actual content.

    Video:  [──────][──────]  (exact times, indices 0 to n-1)
    Audio:  [───────][──────] (extended, indices n to 2n-1)
                   ↓ acrossfade ↓
    Audio:  [──────][──────]  (same duration as video)
    """
    # Add AUDIO inputs with extended times
    for i, cut in enumerate(cuts):
        start = float(cut["start"])
        end = float(cut["end"])
        duration = end - start

        # Calculate extensions based on position
        # First segment: only extend at the end
        # Middle segments: extend both sides
        # Last segment: only extend at the start
        extend_before = fade_duration if i > 0 else 0
        extend_after = fade_duration if i < n_cuts - 1 else 0

        audio_start = max(0, start - extend_before)
        audio_duration = duration + extend_before + extend_after

        inputs.append({
            "file_url": video_url,
            "options": [
                {"option": "-ss", "argument": str(audio_start)},
                {"option": "-t", "argument": str(audio_duration)}
            ]
        })

    # Build filter complex
    filter_parts = []

    # 1. Video scaling (if needed) and concat
    if render_settings["scale"]:
        width, height = render_settings["scale"].split(":")
        # Scale each video input
        for i in range(n_cuts):
            filter_parts.append(
                f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}]"
            )
        video_concat_inputs = "".join([f"[v{i}]" for i in range(n_cuts)])
    else:
        video_concat_inputs = "".join([f"[{i}:v]" for i in range(n_cuts)])

    video_concat = f"{video_concat_inputs}concat=n={n_cuts}:v=1:a=0[outv]"
    filter_parts.append(video_concat)

    # 2. Audio: acrossfade chain of inputs n to 2n-1
    audio_start_idx = n_cuts

    if n_cuts == 2:
        # Special case: only 2 segments
        xfade_dur = min(fade_duration, min(durations) / 4)
        audio_filter = (
            f"[{audio_start_idx}:a][{audio_start_idx + 1}:a]"
            f"acrossfade=d={xfade_dur:.3f}:c1=tri:c2=tri[outa]"
        )
        filter_parts.append(audio_filter)
    else:
        # 3+ segments: chain acrossfade
        # First crossfade
        xfade_dur = min(fade_duration, min(durations[0], durations[1]) / 4)
        filter_parts.append(
            f"[{audio_start_idx}:a][{audio_start_idx + 1}:a]"
            f"acrossfade=d={xfade_dur:.3f}:c1=tri:c2=tri[a01]"
        )

        # Intermediate crossfades
        prev_label = "a01"
        for i in range(2, n_cuts):
            xfade_dur = min(fade_duration, min(durations[i-1], durations[i]) / 4)
            audio_idx = audio_start_idx + i
            if i == n_cuts - 1:
                # Last: final output
                filter_parts.append(
                    f"[{prev_label}][{audio_idx}:a]"
                    f"acrossfade=d={xfade_dur:.3f}:c1=tri:c2=tri[outa]"
                )
            else:
                # Intermediate: create label for next
                new_label = f"a{i:02d}"
                filter_parts.append(
                    f"[{prev_label}][{audio_idx}:a]"
                    f"acrossfade=d={xfade_dur:.3f}:c1=tri:c2=tri[{new_label}]"
                )
                prev_label = new_label

    # Join all filters with ;
    full_filter = ";".join(filter_parts)

    # Output options with re-encoding (required for concat filter + crossfade)
    output_options = [
        {"option": "-map", "argument": "[outv]"},
        {"option": "-map", "argument": "[outa]"},
        {"option": "-c:v", "argument": render_settings["video_codec"]},
        {"option": "-preset", "argument": render_settings["preset"]},
        {"option": "-crf", "argument": str(render_settings["crf"])},
        {"option": "-pix_fmt", "argument": render_settings["pix_fmt"]},
        {"option": "-c:a", "argument": "aac"},
        {"option": "-b:a", "argument": render_settings["audio_bitrate"]},
        {"option": "-movflags", "argument": "+faststart"}
    ]

    return {
        "inputs": inputs,
        "filters": [{"filter": full_filter}],
        "outputs": [{"options": output_options}]
    }


def build_preview_payload(
    video_url: str,
    cuts: List[Dict[str, str]],
    quality: str = "480p",
    fade_duration: float = 0.025
) -> Dict[str, Any]:
    """Build FFmpeg compose payload for low-res preview.

    Convenience wrapper for build_ffmpeg_compose_payload with preview profiles.

    Args:
        video_url: URL of the source video
        cuts: List of cuts [{"start": "5.72", "end": "7.22"}, ...]
        quality: Preview quality ('480p' or '720p')
        fade_duration: Duration of audio crossfade in seconds

    Returns:
        Dict payload for /v1/ffmpeg/compose endpoint
    """
    profile = "preview" if quality == "480p" else "preview_720p"
    return build_ffmpeg_compose_payload(
        video_url=video_url,
        cuts=cuts,
        profile=profile,
        fade_duration=fade_duration,
        use_stream_copy=False  # Always encode for preview to get smaller files
    )


def build_final_render_payload(
    video_url: str,
    cuts: List[Dict[str, str]],
    quality: str = "high",
    fade_duration: float = 0.025
) -> Dict[str, Any]:
    """Build FFmpeg compose payload for final high-quality render.

    Convenience wrapper for build_ffmpeg_compose_payload with quality profiles.

    Args:
        video_url: URL of the source video
        cuts: List of cuts [{"start": "5.72", "end": "7.22"}, ...]
        quality: Output quality ('standard', 'high', '4k')
        fade_duration: Duration of audio crossfade in seconds

    Returns:
        Dict payload for /v1/ffmpeg/compose endpoint
    """
    if quality not in ("standard", "high", "4k"):
        raise ValueError(f"Invalid quality '{quality}'. Use 'standard', 'high', or '4k'")

    return build_ffmpeg_compose_payload(
        video_url=video_url,
        cuts=cuts,
        profile=quality,
        fade_duration=fade_duration,
        use_stream_copy=False
    )


def blocks_to_cuts(blocks: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Convert blocks with timestamps to cuts format for FFmpeg.

    Args:
        blocks: List of blocks [{"inMs": 300, "outMs": 5720, ...}, ...]

    Returns:
        List of cuts [{"start": "0.3", "end": "5.72"}, ...]
    """
    if not blocks:
        return []

    # Validate blocks format
    if not isinstance(blocks[0], dict):
        logger.warning(f"blocks_to_cuts: blocks has wrong format (first item is {type(blocks[0])})")
        return []

    cuts = []
    for block in blocks:
        if not isinstance(block, dict):
            logger.warning(f"blocks_to_cuts: skipping non-dict block: {type(block)}")
            continue
        start_sec = block.get("inMs", 0) / 1000.0
        end_sec = block.get("outMs", 0) / 1000.0
        if end_sec > start_sec:  # Only add valid cuts
            cuts.append({
                "start": f"{start_sec:.3f}",
                "end": f"{end_sec:.3f}"
            })
    return cuts


def estimate_render_time(
    video_duration_sec: float,
    n_cuts: int,
    profile: str
) -> float:
    """Estimate render time based on video duration and profile.

    Args:
        video_duration_sec: Total duration of output video in seconds
        n_cuts: Number of cuts/segments
        profile: Render profile name

    Returns:
        Estimated render time in seconds
    """
    # Base multipliers (inverse of realtime speed)
    multipliers = {
        "preview": 0.08,      # 10-20x realtime -> ~0.05-0.1x duration
        "preview_720p": 0.15, # 5-10x realtime -> ~0.1-0.2x duration
        "standard": 0.35,     # 2-4x realtime -> ~0.25-0.5x duration
        "high": 1.5,          # 0.5-1x realtime -> ~1-2x duration
        "4k": 4.0             # 0.2-0.5x realtime -> ~2-5x duration
    }

    base_mult = multipliers.get(profile, 0.5)

    # Add overhead for multiple cuts (filter setup, etc.)
    cut_overhead = max(0, (n_cuts - 1) * 2)  # ~2 seconds per cut point

    return video_duration_sec * base_mult + cut_overhead
