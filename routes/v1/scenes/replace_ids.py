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
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

"""
Scene ID Replacement Route
Migrated from Media Processing Gateway - POST /api/replace_scene_ids
"""

from flask import Blueprint, request
from app_utils import validate_payload, queue_task_wrapper
from services.authentication import authenticate
import logging
from datetime import datetime
import json
import traceback

v1_scenes_replace_ids_bp = Blueprint('v1_scenes_replace_ids', __name__)
logger = logging.getLogger(__name__)

@v1_scenes_replace_ids_bp.route('/v1/scenes/replace-ids', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "tareas": {
            "type": "object",
            "properties": {
                "tareas_de_investigacion_identificadas": {
                    "type": "array"
                }
            },
            "required": ["tareas_de_investigacion_identificadas"]
        },
        "mapping": {
            "type": "object"
        },
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["tareas", "mapping"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def replace_scene_ids_endpoint(job_id, data):
    """
    Replace scene IDs in JSON according to a mapping.

    Migrated from Media Processing Gateway POST /api/replace_scene_ids

    Args:
        job_id: Job ID assigned by queue_task_wrapper
        data: Object with:
            - tareas: JSON with tareas_de_investigacion_identificadas array
            - mapping: Dictionary mapping old IDs to new IDs

    Returns:
        Tuple of (response_data, endpoint_string, status_code)
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[{timestamp}] Job {job_id}: Processing scene ID replacement request")

    try:
        # Extract data from object format
        tareas_json = data.get('tareas', {})
        mapeo_ids = data.get('mapping', {})
        
        # Verify structure
        if "tareas_de_investigacion_identificadas" not in tareas_json or not isinstance(tareas_json["tareas_de_investigacion_identificadas"], list):
            logger.error(f"[{timestamp}] Job {job_id}: First JSON must contain 'tareas_de_investigacion_identificadas' as array")
            return {"error": "El primer JSON debe contener 'tareas_de_investigacion_identificadas' como array"}, "/v1/scenes/replace-ids", 400
        
        if not isinstance(mapeo_ids, dict):
            logger.error(f"[{timestamp}] Job {job_id}: Second JSON must be a dictionary mapping IDs")
            return {"error": "El segundo JSON debe ser un diccionario de mapeo de IDs"}, "/v1/scenes/replace-ids", 400
        
        # Count IDs to replace
        ids_por_reemplazar = 0
        ids_reemplazados = 0
        
        # Perform replacement
        for tarea in tareas_json["tareas_de_investigacion_identificadas"]:
            if not isinstance(tarea, dict) or "idEscenaAsociada" not in tarea:
                continue
            
            id_original = tarea["idEscenaAsociada"]
            ids_por_reemplazar += 1
            
            if id_original in mapeo_ids:
                tarea["idEscenaAsociada"] = mapeo_ids[id_original]
                ids_reemplazados += 1
        
        logger.info(f"[{timestamp}] Job {job_id}: Replacement completed. IDs replaced: {ids_reemplazados}/{ids_por_reemplazar}")
        
        # Return updated JSON
        return tareas_json, "/v1/scenes/replace-ids", 200
        
    except json.JSONDecodeError as e:
        logger.error(f"[{timestamp}] Job {job_id}: Invalid JSON: {str(e)}")
        return {"error": f"JSON inválido: {str(e)}"}, "/v1/scenes/replace-ids", 400
    except Exception as e:
        error_msg = f"Error processing scene ID replacement: {str(e)}"
        logger.error(f"[{timestamp}] Job {job_id}: {error_msg}")
        logger.error(traceback.format_exc())
        return {"error": error_msg}, "/v1/scenes/replace-ids", 500

