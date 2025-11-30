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
Format Adapter for Media Gateway
Migrated from Media Processing Gateway - adapts different input formats
"""

import re
import json
import logging

logger = logging.getLogger(__name__)

def normalize_cuts(cuts):
    """
    Normaliza diferentes formatos de cortes a un formato estándar con timestamp.
    
    Formatos soportados:
    - {"timestamp": 1000}
    - {"inMs": 1000, "outMs": 2000}
    - {"timeMs": 1000}
    
    Returns:
        Lista de cortes normalizada con formato {"timestamp": valor}
    """
    normalized_cuts = []
    
    for cut in cuts:
        if "timestamp" in cut:
            # Ya está en el formato esperado
            normalized_cuts.append({"timestamp": cut["timestamp"]})
        elif "inMs" in cut:
            # Formato con inMs/outMs
            normalized_cuts.append({"timestamp": cut["inMs"]})
        elif "timeMs" in cut:
            # Formato con timeMs
            normalized_cuts.append({"timestamp": cut["timeMs"]})
        else:
            # Si no se reconoce el formato, buscamos cualquier campo que parezca un timestamp
            for key, value in cut.items():
                if isinstance(value, (int, float)) and key.lower().endswith(('ms', 'time', 'timestamp')):
                    normalized_cuts.append({"timestamp": value})
                    break
    
    return normalized_cuts

def preprocess_transcription(transcription):
    """
    Preprocesa la transcripción para convertirla a un formato estándar.
    
    Formatos soportados:
    - Formato XML estándar: <w t="7.099">si</w>
    - Formato personalizado: <pt.35> st: 7099 wd: si en: 7179 </pt.35>
    
    Returns:
        Transcripción en formato XML estándar
    """
    # Verificar si ya está en formato estándar
    if re.search(r'<w\s+t="', transcription):
        return transcription
    
    # Verificar si está en formato personalizado
    if re.search(r'<pt\.\d+>', transcription):
        # Convertir de formato personalizado a formato estándar
        standardized = ""
        pattern = r'<pt\.\d+>\s*st:\s*(\d+)\s*wd:\s*([^<\n]+)\s*en:\s*\d+\s*</pt\.\d+>'
        matches = re.findall(pattern, transcription, re.DOTALL)
        
        for timestamp, word in matches:
            # Convertir de milisegundos a segundos
            time_sec = float(timestamp) / 1000.0
            standardized += f'<w t="{time_sec}">{word.strip()}</w> '
        
        return standardized.strip()
    
    # Si no se reconoce ningún formato, tratar como texto simple
    return transcription

