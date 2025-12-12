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
AutoEdit Services Module

Provides core services for the AutoEdit video editing pipeline:
- workflow: Workflow state management
- blocks: Block manipulation and gap calculation
- preview: Low-res preview and final render generation
- ffmpeg_builder: FFmpeg payload construction with crossfade
"""

from services.v1.autoedit.workflow import (
    WorkflowManager,
    get_workflow_manager,
    WORKFLOW_STATES
)
from services.v1.autoedit.blocks import (
    calculate_gaps,
    calculate_stats,
    apply_modifications,
    ensure_block_ids,
    add_preview_positions
)
from services.v1.autoedit.preview import (
    generate_preview,
    generate_final_render,
    estimate_preview_time,
    estimate_render_time_for_blocks
)
from services.v1.autoedit.ffmpeg_builder import (
    build_preview_payload,
    build_final_render_payload,
    blocks_to_cuts,
    RENDER_PROFILES
)

__all__ = [
    # Workflow
    'WorkflowManager',
    'get_workflow_manager',
    'WORKFLOW_STATES',
    # Blocks
    'calculate_gaps',
    'calculate_stats',
    'apply_modifications',
    'ensure_block_ids',
    'add_preview_positions',
    # Preview
    'generate_preview',
    'generate_final_render',
    'estimate_preview_time',
    'estimate_render_time_for_blocks',
    # FFmpeg
    'build_preview_payload',
    'build_final_render_payload',
    'blocks_to_cuts',
    'RENDER_PROFILES'
]
