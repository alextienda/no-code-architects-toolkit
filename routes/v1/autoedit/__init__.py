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
AutoEdit API Routes Package

Provides REST API endpoints for the AutoEdit video editing pipeline:

Workflow Lifecycle (workflow_api.py):
- POST /v1/autoedit/workflow - Create new workflow
- GET /v1/autoedit/workflow/{id} - Get workflow status
- DELETE /v1/autoedit/workflow/{id} - Delete workflow
- GET /v1/autoedit/workflows - List all workflows

HITL 1 - XML Review (workflow_api.py):
- GET /v1/autoedit/workflow/{id}/analysis - Get XML for review
- PUT /v1/autoedit/workflow/{id}/analysis - Submit reviewed XML

HITL 2 - Preview & Blocks (preview_api.py):
- POST /v1/autoedit/workflow/{id}/process - Process XML to blocks
- POST /v1/autoedit/workflow/{id}/preview - Generate low-res preview
- GET /v1/autoedit/workflow/{id}/preview - Get preview data
- PATCH /v1/autoedit/workflow/{id}/blocks - Modify blocks

Final Render (render_api.py):
- POST /v1/autoedit/workflow/{id}/render - Approve and render
- GET /v1/autoedit/workflow/{id}/render - Get render status
- GET /v1/autoedit/workflow/{id}/result - Get final video
- POST /v1/autoedit/workflow/{id}/rerender - Re-render with new settings
- GET /v1/autoedit/workflow/{id}/estimate - Estimate render time

Blueprints are auto-discovered by app.py from this directory.
"""
