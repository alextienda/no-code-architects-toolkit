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
XML Processor for Media Gateway
Migrated from Media Processing Gateway - extracts sections from XML and finds timestamps in transcript
"""

import xml.etree.ElementTree as ET
import re
import json
import logging
from typing import List, Dict, Any, Optional, Union, Tuple

# Configurar logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s'
)

logger = logging.getLogger(__name__)

def normalize_text(text: str) -> Tuple[str, List[str]]:
    """
    Normaliza el texto para la comparación:
    - Convierte a minúsculas
    - Elimina puntuación al inicio/final de palabras
    - Elimina espacios extra
    - Maneja caracteres especiales
    """
    # Primero convertimos a minúsculas y eliminamos espacios extra
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    
    # Reemplazamos caracteres especiales comunes
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'ü': 'u', 'ñ': 'n'
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # Separamos en palabras
    words = text.split()
    cleaned_words = []
    
    for word in words:
        # Limpiamos puntuación pero preservamos caracteres especiales dentro de palabras
        cleaned_word = re.sub(r'^[^\w\']+|[^\w\']+$', '', word)
        if cleaned_word:
            # Normalizamos apóstrofes y comillas
            cleaned_word = re.sub(r'[''´`]', "'", cleaned_word)
            # Eliminamos solo puntos y comas al final
            cleaned_word = re.sub(r'[.,;:]+$', '', cleaned_word)
            cleaned_words.append(cleaned_word)

    normalized = ' '.join(cleaned_words)
    return normalized, cleaned_words

def find_segment_in_transcript(segment_words: List[str], full_transcript: List[Dict[str, Any]], 
                              start_index: int = 0, max_search_length: int = None) -> Tuple[Optional[Dict[str, Any]], int]:
    """
    Busca la secuencia exacta de palabras (normalizadas) del segmento
    dentro de la transcripción completa, comenzando desde start_index.
    Devuelve la coincidencia y el índice donde terminó la búsqueda.
    
    Args:
        segment_words: Lista de palabras normalizadas a buscar
        full_transcript: Transcripción completa con marcas de tiempo
        start_index: Índice desde donde comenzar la búsqueda
        max_search_length: Límite opcional de cuántos elementos examinar (para limitar búsquedas largas)
    
    Returns:
        Tuple con (resultado encontrado o None, nuevo índice donde terminó la búsqueda)
    """
    if not segment_words:
        logger.warning("No hay palabras en el segmento para buscar")
        return None, start_index

    # Normalizamos las palabras de la transcripción
    transcript_words_info = []
    for item in full_transcript:
        normalized_word, _ = normalize_text(item['text'])
        if normalized_word:  # Solo agregamos palabras no vacías
            transcript_words_info.append({
                'normalized': normalized_word,
                'text': item['text'],
                'inMs': item['inMs'],
                'outMs': item['outMs']
            })

    n_segment = len(segment_words)
    n_transcript = len(transcript_words_info)
    
    # Limitamos la búsqueda si se especifica max_search_length
    end_index = n_transcript
    if max_search_length and start_index + max_search_length < n_transcript:
        end_index = start_index + max_search_length
        logger.info(f"Limitando búsqueda desde índice {start_index} hasta {end_index}")

    logger.info(f"Buscando segmento: {segment_words} desde índice {start_index} hasta {end_index}")
    if start_index < n_transcript:
        logger.info(f"Transcripción normalizada desde posición {start_index}: {[w['normalized'] for w in transcript_words_info[start_index:min(start_index+10, n_transcript)]]}...")

    # Solo buscamos hasta end_index - n_segment + 1 para asegurar que haya suficientes palabras para comparar
    search_end = min(end_index - n_segment + 1, n_transcript - n_segment + 1)
    
    if start_index >= search_end:
        logger.warning(f"Índice de inicio {start_index} es mayor que el límite de búsqueda {search_end}")
        return None, start_index

    # Ahora buscamos coincidencias
    for i in range(start_index, search_end):
        match = True
        for j in range(n_segment):
            if segment_words[j] != transcript_words_info[i + j]['normalized']:
                match = False
                break

        if match:
            # Recolectar el texto original de las palabras encontradas
            original_text = ' '.join(w['text'] for w in transcript_words_info[i:i + n_segment])
            result = {
                "inMs": transcript_words_info[i]['inMs'],
                "outMs": transcript_words_info[i + n_segment - 1]['outMs'],
                "text": original_text
            }
            logger.info(f"Encontrado segmento en posición {i}: {result}")
            # Devolvemos el resultado y el índice donde terminamos (para la próxima búsqueda)
            return result, i + n_segment
    
    logger.warning(f"No se encontró el segmento en la transcripción desde la posición {start_index}")
    return None, start_index

def extract_sections_from_xml(xml_string: str, full_transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Función principal que extrae segmentos del XML y busca sus marcas de tiempo en la transcripción.
    Busca secuencialmente, comenzando cada búsqueda desde donde terminó la anterior.
    
    Args:
        xml_string: String XML con etiquetas <mantener>
        full_transcript: Lista de diccionarios con la transcripción y marcas de tiempo
        
    Returns:
        Diccionario con "cortes" (resultados encontrados) y "status" (éxito o error)
    """
    logger.info(f"=== INICIO extract_sections_from_xml ===")
    logger.info(f"XML recibido. Longitud: {len(xml_string)} caracteres")
    logger.info(f"Transcript recibido. Elementos: {len(full_transcript)}")
    
    if not full_transcript:
        logger.error("Transcript está vacío")
        return {"cortes": [], "status": "error", "error": "Transcript está vacío"}
    
    try:
        root = ET.fromstring(xml_string)
        logger.info(f"XML parseado exitosamente. Root tag: {root.tag}")
    except ET.ParseError as e:
        logger.error(f"Error parsing XML: {e}")
        logger.error(f"XML que causó el error (primeros 500 chars): {xml_string[:500]}")
        return {"cortes": [], "status": "error", "error": f"Error parsing XML: {e}"}

    results = []
    segments_to_find = root.findall('.//mantener')
    logger.info(f"Etiquetas <mantener> encontradas: {len(segments_to_find)}")

    if not segments_to_find:
        logger.warning("No se encontraron etiquetas <mantener> en el XML.")
        logger.warning(f"XML completo: {xml_string[:500]}...")
        return {"cortes": [], "status": "success"}
    
    # Índice desde el que comenzamos a buscar en la transcripción
    current_index = 0
    last_timestamp = 0
    
    # Máximo número de palabras a buscar después del índice actual (para evitar búsquedas excesivas)
    max_search_length = 1000  # Ajustar según necesidad

    for segment_element in segments_to_find:
        segment_text = segment_element.text
        if not segment_text or not segment_text.strip():
            logger.warning("Segmento <mantener> está vacío o solo contiene espacios.")
            continue
            
        segment_text = segment_text.strip()
        logger.info(f"Procesando segmento: '{segment_text}'")
        normalized_segment_text, segment_words_normalized = normalize_text(segment_text)

        if not segment_words_normalized:
            logger.warning("Segmento vacío después de normalizar, saltando.")
            continue

        logger.info(f"Palabras normalizadas a buscar: {segment_words_normalized}")
        
        # MEJORA 1: Siempre buscamos desde el índice actual
        found_times, new_index = find_segment_in_transcript(
            segment_words_normalized, 
            full_transcript,
            current_index,
            max_search_length
        )

        if found_times:
            # MEJORA 2: Verificamos que el timestamp sea posterior al último para garantizar orden cronológico
            if found_times["inMs"] >= last_timestamp:
                results.append(found_times)
                logger.info(f"Encontrado: {found_times}")
                # Actualizamos para la próxima búsqueda
                current_index = new_index
                last_timestamp = found_times["outMs"]
            else:
                # MEJORA 3: Si el timestamp es anterior, intentamos buscar desde el siguiente índice
                logger.warning(f"Se encontró una coincidencia ({found_times}) pero con timestamp anterior "
                               f"al último ({last_timestamp}). Buscando la siguiente ocurrencia.")
                
                # MEJORA 4: Avanzamos solo una posición para evitar saltar coincidencias
                found_times, new_index = find_segment_in_transcript(
                    segment_words_normalized, 
                    full_transcript,
                    current_index + 1,  # Avanzamos solo una posición, no hasta new_index
                    max_search_length
                )
                
                if found_times:
                    # Verificamos nuevamente el timestamp
                    if found_times["inMs"] >= last_timestamp:
                        results.append(found_times)
                        logger.info(f"Encontrado (segundo intento): {found_times}")
                        current_index = new_index
                        last_timestamp = found_times["outMs"]
                    else:
                        # Si aún es anterior, reportamos como no encontrado en orden cronológico
                        error_result = {
                            "inMs": None,
                            "outMs": None,
                            "text": segment_text,
                            "error": f"Segmento encontrado solo con timestamp anterior: '{segment_text}'"
                        }
                        results.append(error_result)
                else:
                    error_result = {
                        "inMs": None,
                        "outMs": None,
                        "text": segment_text,
                        "error": f"Segmento no encontrado en segundo intento: '{segment_text}'"
                    }
                    results.append(error_result)
        else:
            # MEJORA 5: Solo reportamos como no encontrado, sin intentar buscar desde el inicio
            error_result = {
                "inMs": None,
                "outMs": None,
                "text": segment_text,
                "error": f"Segmento no encontrado: '{segment_text}'"
            }
            results.append(error_result)
            logger.warning(f"Segmento no encontrado en la transcripción: '{segment_text}'")

    # MEJORA 6: No ordenamos los resultados al final, ya que deberían estar en orden cronológico
    # debido a la búsqueda secuencial
    
    logger.info(f"=== FIN extract_sections_from_xml ===")
    logger.info(f"Total de segmentos procesados: {len(segments_to_find)}")
    logger.info(f"Total de cortes encontrados: {len(results)}")
    logger.info(f"Cortes con error: {len([r for r in results if 'error' in r])}")
    logger.info(f"Cortes exitosos: {len([r for r in results if 'error' not in r])}")
    
    if results:
        logger.info(f"Primer corte: {results[0]}")
        if len(results) > 1:
            logger.info(f"Último corte: {results[-1]}")
    
    return {"cortes": results, "status": "success"}

