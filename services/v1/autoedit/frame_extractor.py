# Copyright (c) 2025
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

"""
Frame Extractor for B-Roll Analysis

Extracts frames from video files for visual analysis with Gemini Vision.
Uses FFmpeg for efficient frame extraction at configurable intervals.
"""

import os
import subprocess
import tempfile
import logging
import base64
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from config import LOCAL_STORAGE_PATH

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_FRAME_INTERVAL_SEC = 2.0  # Extract 1 frame every 2 seconds
MAX_FRAMES_PER_ANALYSIS = 30     # Maximum frames to send to Gemini
MAX_VIDEO_DURATION_SEC = 600     # 10 minutes max for analysis
FRAME_FORMAT = "jpg"
FRAME_QUALITY = 85  # JPEG quality (1-100)
FRAME_WIDTH = 1280  # Resize to this width (maintains aspect ratio)


class FrameExtractor:
    """Extracts frames from videos for visual analysis."""

    def __init__(
        self,
        frame_interval: float = DEFAULT_FRAME_INTERVAL_SEC,
        max_frames: int = MAX_FRAMES_PER_ANALYSIS,
        output_width: int = FRAME_WIDTH,
        quality: int = FRAME_QUALITY
    ):
        """Initialize the frame extractor.

        Args:
            frame_interval: Seconds between extracted frames
            max_frames: Maximum number of frames to extract
            output_width: Width to resize frames to (height auto-scaled)
            quality: JPEG quality (1-100)
        """
        self.frame_interval = frame_interval
        self.max_frames = max_frames
        self.output_width = output_width
        self.quality = quality
        self.temp_dir = Path(LOCAL_STORAGE_PATH) / "frames"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def get_video_duration(self, video_path: str) -> float:
        """Get video duration in seconds using ffprobe.

        Args:
            video_path: Path to video file (local or URL)

        Returns:
            Duration in seconds
        """
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                return float(result.stdout.strip())
            else:
                logger.error(f"ffprobe error: {result.stderr}")
                return 0.0
        except Exception as e:
            logger.error(f"Error getting video duration: {e}")
            return 0.0

    def extract_frames(
        self,
        video_path: str,
        output_dir: Optional[str] = None,
        start_time: float = 0,
        end_time: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """Extract frames from a video at regular intervals.

        Args:
            video_path: Path to video file (local path or URL)
            output_dir: Directory to save frames (uses temp if None)
            start_time: Start time in seconds (default 0)
            end_time: End time in seconds (default: video duration)

        Returns:
            List of frame metadata dicts with paths and timestamps
        """
        # Create output directory
        if output_dir:
            frame_dir = Path(output_dir)
        else:
            import uuid
            frame_dir = self.temp_dir / f"extract_{uuid.uuid4().hex[:8]}"
        frame_dir.mkdir(parents=True, exist_ok=True)

        # Get video duration if end_time not specified
        duration = self.get_video_duration(video_path)
        if duration <= 0:
            logger.error("Could not determine video duration")
            return []

        if end_time is None:
            end_time = min(duration, MAX_VIDEO_DURATION_SEC)
        else:
            end_time = min(end_time, duration, MAX_VIDEO_DURATION_SEC)

        # Calculate frame timestamps
        frame_times = []
        current_time = start_time
        while current_time < end_time and len(frame_times) < self.max_frames:
            frame_times.append(current_time)
            current_time += self.frame_interval

        if not frame_times:
            logger.warning("No frames to extract")
            return []

        logger.info(f"Extracting {len(frame_times)} frames from {video_path}")

        # Build FFmpeg command for batch extraction
        # Using select filter to extract specific frames
        output_pattern = str(frame_dir / "frame_%04d.jpg")

        # Create select expression for specific timestamps
        select_expr = "+".join([f"gte(t,{t})*lt(t,{t+0.1})" for t in frame_times])

        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-vf", f"select='{select_expr}',scale={self.output_width}:-1",
            "-vsync", "vfr",
            "-q:v", str(int((100 - self.quality) / 3) + 1),  # Convert quality to FFmpeg scale
            "-frames:v", str(len(frame_times)),
            output_pattern
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120  # 2 minute timeout
            )

            if result.returncode != 0:
                logger.warning(f"FFmpeg select failed, trying fps method: {result.stderr[:200]}")
                # Fallback to fps-based extraction
                return self._extract_frames_fps(video_path, frame_dir, start_time, end_time)

        except subprocess.TimeoutExpired:
            logger.error("FFmpeg extraction timed out")
            return []
        except Exception as e:
            logger.error(f"Error extracting frames: {e}")
            return []

        # Collect extracted frames
        frames = []
        for i, frame_time in enumerate(frame_times):
            frame_path = frame_dir / f"frame_{i+1:04d}.jpg"
            if frame_path.exists():
                frames.append({
                    "frame_number": i + 1,
                    "timestamp_sec": frame_time,
                    "timestamp_ms": int(frame_time * 1000),
                    "path": str(frame_path),
                    "filename": frame_path.name
                })

        logger.info(f"Extracted {len(frames)} frames successfully")
        return frames

    def _extract_frames_fps(
        self,
        video_path: str,
        frame_dir: Path,
        start_time: float,
        end_time: float
    ) -> List[Dict[str, Any]]:
        """Fallback method: extract frames using fps filter.

        Args:
            video_path: Path to video file
            frame_dir: Directory to save frames
            start_time: Start time in seconds
            end_time: End time in seconds

        Returns:
            List of frame metadata dicts
        """
        duration = end_time - start_time
        fps = 1.0 / self.frame_interval
        max_frames = min(int(duration / self.frame_interval), self.max_frames)

        output_pattern = str(frame_dir / "frame_%04d.jpg")

        cmd = [
            "ffmpeg",
            "-ss", str(start_time),
            "-i", video_path,
            "-t", str(duration),
            "-vf", f"fps={fps},scale={self.output_width}:-1",
            "-q:v", str(int((100 - self.quality) / 3) + 1),
            "-frames:v", str(max_frames),
            output_pattern
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode != 0:
                logger.error(f"FFmpeg fps extraction failed: {result.stderr[:500]}")
                return []

        except Exception as e:
            logger.error(f"Error in fps extraction: {e}")
            return []

        # Collect extracted frames
        frames = []
        frame_files = sorted(frame_dir.glob("frame_*.jpg"))

        for i, frame_path in enumerate(frame_files[:max_frames]):
            frame_time = start_time + (i * self.frame_interval)
            frames.append({
                "frame_number": i + 1,
                "timestamp_sec": frame_time,
                "timestamp_ms": int(frame_time * 1000),
                "path": str(frame_path),
                "filename": frame_path.name
            })

        logger.info(f"Extracted {len(frames)} frames using fps method")
        return frames

    def frames_to_base64(self, frames: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert frame files to base64 for Gemini API.

        Args:
            frames: List of frame metadata dicts with 'path' key

        Returns:
            List of frame dicts with added 'base64' key
        """
        result = []
        for frame in frames:
            frame_path = frame.get("path")
            if not frame_path or not Path(frame_path).exists():
                continue

            try:
                with open(frame_path, "rb") as f:
                    b64_data = base64.b64encode(f.read()).decode("utf-8")

                result.append({
                    **frame,
                    "base64": b64_data,
                    "mime_type": "image/jpeg"
                })
            except Exception as e:
                logger.error(f"Error encoding frame {frame_path}: {e}")

        return result

    def cleanup_frames(self, frames: List[Dict[str, Any]]) -> None:
        """Delete extracted frame files.

        Args:
            frames: List of frame metadata dicts with 'path' key
        """
        for frame in frames:
            frame_path = frame.get("path")
            if frame_path:
                try:
                    Path(frame_path).unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"Could not delete frame {frame_path}: {e}")

        # Try to remove the directory if empty
        if frames:
            first_path = Path(frames[0].get("path", ""))
            if first_path.parent.exists():
                try:
                    first_path.parent.rmdir()
                except OSError:
                    pass  # Directory not empty

    def extract_and_encode(
        self,
        video_path: str,
        start_time: float = 0,
        end_time: Optional[float] = None,
        cleanup: bool = True
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Extract frames and encode to base64 in one operation.

        Args:
            video_path: Path to video file
            start_time: Start time in seconds
            end_time: End time in seconds (None for full video)
            cleanup: Whether to delete frame files after encoding

        Returns:
            Tuple of (encoded_frames, metadata)
        """
        # Get video duration
        duration = self.get_video_duration(video_path)

        # Extract frames
        frames = self.extract_frames(video_path, start_time=start_time, end_time=end_time)

        if not frames:
            return [], {"error": "No frames extracted", "duration_sec": duration}

        # Encode to base64
        encoded_frames = self.frames_to_base64(frames)

        # Cleanup if requested
        if cleanup:
            self.cleanup_frames(frames)

        metadata = {
            "video_path": video_path,
            "duration_sec": duration,
            "duration_ms": int(duration * 1000),
            "frames_extracted": len(encoded_frames),
            "frame_interval_sec": self.frame_interval,
            "start_time_sec": start_time,
            "end_time_sec": end_time or duration
        }

        return encoded_frames, metadata


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def extract_frames_for_analysis(
    video_path: str,
    frame_interval: float = DEFAULT_FRAME_INTERVAL_SEC,
    max_frames: int = MAX_FRAMES_PER_ANALYSIS
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Extract and encode frames from a video for Gemini analysis.

    Args:
        video_path: Path to video file (local or URL)
        frame_interval: Seconds between frames
        max_frames: Maximum frames to extract

    Returns:
        Tuple of (encoded_frames, metadata)
    """
    extractor = FrameExtractor(
        frame_interval=frame_interval,
        max_frames=max_frames
    )
    return extractor.extract_and_encode(video_path, cleanup=True)


def get_video_info(video_path: str) -> Dict[str, Any]:
    """Get video metadata using ffprobe.

    Args:
        video_path: Path to video file

    Returns:
        Dict with duration, resolution, fps, etc.
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,duration:format=duration",
            "-of", "json",
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)

            # Extract values
            stream = data.get("streams", [{}])[0]
            format_info = data.get("format", {})

            # Parse frame rate (e.g., "30000/1001" -> 29.97)
            fps_str = stream.get("r_frame_rate", "30/1")
            if "/" in fps_str:
                num, den = fps_str.split("/")
                fps = float(num) / float(den) if float(den) > 0 else 30.0
            else:
                fps = float(fps_str)

            duration = float(format_info.get("duration", 0)) or float(stream.get("duration", 0))

            return {
                "width": int(stream.get("width", 0)),
                "height": int(stream.get("height", 0)),
                "fps": round(fps, 2),
                "duration_sec": duration,
                "duration_ms": int(duration * 1000)
            }

        return {"error": result.stderr}

    except Exception as e:
        return {"error": str(e)}
