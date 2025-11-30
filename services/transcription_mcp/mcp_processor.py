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
MCP Transcription Processor
Migrated from Media Processing Gateway - processes transcriptions with timestamps
"""

import json
from typing import List, Dict, Any, Union, Tuple
import logging

logger = logging.getLogger(__name__)

# Configuraciones con los valores que funcionaban mejor
SILENCE_THRESHOLD = 50  # duración mínima de silencio significativo (ms)
PADDING_BEFORE = 90     # padding antes de cada bloque (ms)
PADDING_AFTER = 90      # padding después de cada bloque (ms)
MERGE_THRESHOLD = 100   # umbral para fusionar bloques cercanos (ms)

def parse_transcription(transcription_text: str) -> List[Dict[str, Any]]:
    """
    Parsea el texto de transcripción en formato XML a una lista de tokens.
    
    Args:
        transcription_text: Texto de transcripción en formato XML con etiquetas <pt> y <spc>
        
    Returns:
        Lista de diccionarios representando cada token (palabra o silencio)
    """
    tokens = []
    current_token = {}
    current_type = None
    
    for line in transcription_text.splitlines():
        line = line.strip()
        if not line:
            continue
        
        # Inicio de un token
        if line.startswith("<") and not line.startswith("</") and line.endswith(">"):
            if line.startswith("<pt"):
                current_type = "word"
            elif line.startswith("<spc"):
                current_type = "spc"
            current_token = {}
        # Fin de un token
        elif line.startswith("</") and line.endswith(">"):
            if current_type is not None:
                current_token["type"] = current_type
                tokens.append(current_token)
                current_token = {}
                current_type = None
        # Línea con un campo
        else:
            if ":" in line:
                parts = line.split(":", 1)
                field = parts[0].strip().lower()
                value = parts[1].strip()
                if field == "st":
                    current_token["st"] = int(value)
                elif field == "en":
                    current_token["en"] = int(value)
                elif field == "wd":
                    current_token["wd"] = value
                elif field == "dur":
                    current_token["dur"] = int(value)
            # Manejo de texto (para palabras)
            elif current_type == "word" and "wd" not in current_token:
                current_token["wd"] = line.strip()
    
    return tokens

def clean_agent_data(agent_data: Union[str, Dict, List]) -> Dict[str, Any]:
    """
    Limpia y parsea la entrada del agente.
    
    Args:
        agent_data: Datos del agente en formato string JSON o diccionario
        
    Returns:
        Diccionario con los datos limpios/parseados
    """
    try:
        if isinstance(agent_data, str):
            # Limpiar si es necesario (ej. quitar ```json)
            cleaned = agent_data.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            if not cleaned:
                return {"error": "Agent data string is empty after cleaning"}
            # Intentar parsear el string limpio
            return json.loads(cleaned)
        elif isinstance(agent_data, (dict, list)):
            # Si ya es un dict o list (ej. Flask lo parseó), devolver tal cual
            return agent_data
        else:
            # Tipo de entrada inesperado
            return {"error": f"Invalid type for agent data: {type(agent_data).__name__}"}
    except json.JSONDecodeError as e:
        # Error específico al parsear JSON
        return {"error": f"Invalid JSON format in agent data: {e}"}
    except Exception as e:
        # Otros errores durante limpieza/parseo
        return {"error": f"Unexpected error cleaning/loading agent JSON: {e}"}

def refine_range(tokens: List[Dict[str, Any]], 
                base_range: Dict[str, Any], 
                silence_threshold: int = SILENCE_THRESHOLD, 
                pad_before: int = PADDING_BEFORE, 
                pad_after: int = PADDING_AFTER) -> List[Dict[str, Any]]:
    """
    Procesa la lista de tokens de la transcripción que caen dentro del rango base y
    genera sub-rangos cortando en cada silencio con duración > silence_threshold.
    
    Args:
        tokens: Lista de tokens de transcripción
        base_range: Diccionario con inMs y outMs definiendo el rango del corte
        silence_threshold: Umbral de duración para considerar un silencio como significativo
        pad_before: Padding antes de cada bloque
        pad_after: Padding después de cada bloque
        
    Returns:
        Lista de bloques refinados
    """
    if not isinstance(base_range, dict) or "inMs" not in base_range or "outMs" not in base_range:
        return []
    try:
        in_ms = int(base_range["inMs"])
        out_ms = int(base_range["outMs"])
        if in_ms >= out_ms or in_ms < 0:
            return []
    except (ValueError, TypeError):
        return []
        
    # Filtrar tokens que se solapan con el rango base
    tokens_in_range = []
    for token in tokens:
        if not isinstance(token, dict):
            continue
            
        # Asegurarse de que los valores numéricos son enteros
        try:
            st = int(token.get("st", 0))
            en = int(token.get("en", 0))
            dur = int(token.get("dur", 0)) if "dur" in token else en - st
            
            # Verificar si el token se solapa con el rango base
            if en >= in_ms and st <= out_ms:
                token_copy = token.copy()
                token_copy["st"] = max(st, in_ms)
                token_copy["en"] = min(en, out_ms)
                if token_copy.get("type") == "spc":
                    token_copy["dur"] = token_copy["en"] - token_copy["st"]
                tokens_in_range.append(token_copy)
        except (ValueError, TypeError):
            continue
    
    blocks = []
    current_block_start = None
    last_word_end = None

    i = 0
    while i < len(tokens_in_range):
        token = tokens_in_range[i]
        if token.get("type") == "word":
            if current_block_start is None:
                current_block_start = token["st"]
            last_word_end = token["en"]
            i += 1
        elif token.get("type") == "spc":
            if token["dur"] > silence_threshold and current_block_start is not None and last_word_end is not None:
                # Finalizar bloque actual con padding (+pad_before) sin sobrepasar el inicio del silencio
                tentative_end = last_word_end + pad_before
                block_end = min(tentative_end, token["st"])
                blocks.append({"inMs": current_block_start, "outMs": block_end})
                
                # Buscar la siguiente palabra para iniciar el siguiente bloque y aplicar padding (-pad_after)
                next_word_start = None
                j = i + 1
                while j < len(tokens_in_range):
                    if tokens_in_range[j].get("type") == "word":
                        next_word_start = tokens_in_range[j]["st"]
                        break
                    j += 1
                if next_word_start is not None:
                    new_block_start = max(next_word_start - pad_after, in_ms)
                else:
                    new_block_start = None
                current_block_start = new_block_start
                last_word_end = None
                i += 1
            else:
                i += 1
        else:
            i += 1

    # Finalizar el último bloque si es necesario
    if current_block_start is not None and last_word_end is not None:
        blocks.append({"inMs": current_block_start, "outMs": min(last_word_end + pad_before, out_ms)})
    
    # Si no hay bloques pero hay palabras, crear un bloque para todo el rango
    if not blocks and any(t.get("type") == "word" for t in tokens_in_range):
        blocks.append({"inMs": in_ms, "outMs": out_ms})
    
    return blocks

def merge_blocks(blocks: List[Dict[str, Any]], 
                merge_threshold: int = MERGE_THRESHOLD) -> List[Dict[str, Any]]:
    """
    Fusiona bloques de tiempo cercanos.
    
    Args:
        blocks: Lista de bloques a fusionar
        merge_threshold: Umbral de tiempo máximo entre bloques para fusionarlos
        
    Returns:
        Lista de bloques fusionados
    """
    if not blocks:
        return []

    # Filtrar solo bloques válidos y ordenarlos por tiempo de inicio
    valid_blocks = [
        b for b in blocks if isinstance(b, dict) and
        isinstance(b.get("inMs"), int) and isinstance(b.get("outMs"), int) and
        b["inMs"] < b["outMs"]
    ]
    if not valid_blocks:
        return []
    
    # Ordenar por tiempo de inicio
    valid_blocks.sort(key=lambda x: x["inMs"])

    # Inicializar lista de bloques fusionados
    merged = [valid_blocks[0].copy()]

    # Iterar sobre los bloques restantes
    for block in valid_blocks[1:]:
        last_merged = merged[-1]
        gap = block["inMs"] - last_merged["outMs"]
        
        # Fusionar si el gap es pequeño
        if gap <= merge_threshold:
            merged[-1] = {"inMs": last_merged["inMs"], "outMs": block["outMs"]}
        else:
            merged.append(block.copy())

    return merged

def process_transcription(transcription_text: str, agent_data: Dict[str, Any], 
                          silence_threshold: int = SILENCE_THRESHOLD,
                          padding_before: int = PADDING_BEFORE,
                          padding_after: int = PADDING_AFTER,
                          merge_threshold: int = MERGE_THRESHOLD) -> Tuple[List[Dict[str, Any]], int]:
    """
    Procesa la transcripción y datos del agente para generar bloques de tiempo.
    
    Args:
        transcription_text: Texto de transcripción en formato XML
        agent_data: Datos del agente con cortes
        silence_threshold: Umbral para considerar un silencio como significativo
        padding_before: Padding antes de cada bloque
        padding_after: Padding después de cada bloque
        merge_threshold: Umbral para fusionar bloques cercanos
        
    Returns:
        Tupla de (bloques procesados, número de tokens procesados)
    """
    # Parsear transcripción
    tokens = parse_transcription(transcription_text)
    
    # Verificar estructura de datos del agente
    if not isinstance(agent_data, dict) or "cortes" not in agent_data:
        return [], len(tokens)
    
    # Procesar cada corte
    all_refined = []
    for base_range in agent_data["cortes"]:
        sub_ranges = refine_range(
            tokens, 
            base_range, 
            silence_threshold=silence_threshold, 
            pad_before=padding_before, 
            pad_after=padding_after
        )
        all_refined.extend(sub_ranges)
    
    # Fusionar bloques cercanos
    final_blocks = merge_blocks(all_refined, merge_threshold=merge_threshold)
    
    return final_blocks, len(tokens)

