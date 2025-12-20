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



import os
import logging

# Retrieve the API key from environment variables
API_KEY = os.environ.get('API_KEY')
if not API_KEY:
    raise ValueError("API_KEY environment variable is not set")

# Storage path setting
LOCAL_STORAGE_PATH = os.environ.get('LOCAL_STORAGE_PATH', '/tmp')

# GCP environment variables
GCP_SA_CREDENTIALS = os.environ.get('GCP_SA_CREDENTIALS', '')
GCP_BUCKET_NAME = os.environ.get('GCP_BUCKET_NAME', '')

def validate_env_vars(provider):

    """ Validate the necessary environment variables for the selected storage provider """
    required_vars = {
        'GCP': ['GCP_BUCKET_NAME', 'GCP_SA_CREDENTIALS'],
        'S3': ['S3_ENDPOINT_URL', 'S3_ACCESS_KEY', 'S3_SECRET_KEY', 'S3_BUCKET_NAME', 'S3_REGION'],
        'S3_DO': ['S3_ENDPOINT_URL', 'S3_ACCESS_KEY', 'S3_SECRET_KEY']
    }
    
    missing_vars = [var for var in required_vars[provider] if not os.getenv(var)]
    if missing_vars:
        raise ValueError(f"Missing environment variables for {provider} storage: {', '.join(missing_vars)}")


# =============================================================================
# AUTOEDIT: CREATOR GLOBAL PROFILE
# =============================================================================
# This profile is used by AutoEdit prompts to personalize content for the creator.
# Each field can be overridden via environment variables.
# Per-project overrides can be set in project.project_context when creating projects.

CREATOR_GLOBAL_PROFILE = {
    # Creator's name (used instead of "el orador" in summaries)
    "name": os.environ.get("CREATOR_NAME", "Alex"),

    # Brand description
    "brand": os.environ.get(
        "CREATOR_BRAND",
        "Contenido educativo de aviación y tecnología"
    ),

    # Target audience description
    "audience": os.environ.get(
        "CREATOR_AUDIENCE",
        "Estudiantes de piloto, entusiastas de aviación, tech enthusiasts"
    ),

    # Content style
    "style": os.environ.get(
        "CREATOR_STYLE",
        "Didáctico, técnico pero accesible, práctico"
    ),

    # Communication tone
    "tone": os.environ.get(
        "CREATOR_TONE",
        "Informativo, profesional, cercano"
    ),

    # Typical content types (comma-separated, parsed to list)
    "typical_content": [
        x.strip() for x in os.environ.get(
            "CREATOR_CONTENT_TYPES",
            "tutoriales técnicos, explicaciones de conceptos, cursos"
        ).split(",")
    ],

    # Things to avoid in content (comma-separated, parsed to list)
    "avoid": [
        x.strip() for x in os.environ.get(
            "CREATOR_AVOID",
            "humor forzado, clickbait, contenido superficial"
        ).split(",")
    ]
}
