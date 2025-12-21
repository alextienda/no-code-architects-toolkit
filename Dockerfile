# Optimized Dockerfile using pre-built base image
# This dramatically reduces build time from ~30 min to ~2-3 min
FROM stephengpope/no-code-architects-toolkit:latest

# Set work directory (should already be /app in base image)
WORKDIR /app

# Copy our custom routes and services
# These are the new endpoints we added (transcription processing, scene replacement, etc.)

# Copy new route files
COPY routes/v1/transcription/ /app/routes/v1/transcription/
COPY routes/v1/scenes/ /app/routes/v1/scenes/
COPY routes/v1/logic/ /app/routes/v1/logic/
COPY routes/v1/autoedit/ /app/routes/v1/autoedit/
COPY routes/v1/gcp/ /app/routes/v1/gcp/

# Copy new service files
COPY services/transcription_mcp/ /app/services/transcription_mcp/
COPY services/v1/autoedit/ /app/services/v1/autoedit/
COPY services/v1/video/ /app/services/v1/video/
COPY services/v1/gcp/ /app/services/v1/gcp/

# Copy prompts for autoedit
COPY infrastructure/prompts/ /app/infrastructure/prompts/

# Copy any modified core files
# The base image's app.py auto-discovers blueprints, so new routes are automatically registered
COPY app_utils.py /app/app_utils.py

# Copy updated configuration if needed
COPY config.py /app/config.py

# Copy gunicorn config
COPY gunicorn.conf.py /app/gunicorn.conf.py

# Install additional dependencies not in base image (NO PyAnnote - that will be separate service)
USER root
RUN pip install --no-cache-dir google-cloud-workflows google-cloud-tasks twelvelabs>=0.2.0 \
    # Phase 5: LLM Agents, Knowledge Graph, Vector Search
    google-generativeai>=0.8.0 neo4j>=5.0.0 faiss-cpu>=1.7.4

# Ensure correct permissions for all new directories
RUN mkdir -p /app/routes/v1/transcription /app/routes/v1/scenes /app/routes/v1/logic /app/routes/v1/autoedit /app/routes/v1/gcp /app/services/transcription_mcp /app/services/v1/autoedit /app/services/v1/video /app/services/v1/gcp /app/infrastructure/prompts && \
    chown -R appuser:appuser /app/routes/v1/transcription/ /app/routes/v1/scenes/ /app/routes/v1/logic/ /app/routes/v1/autoedit/ /app/routes/v1/gcp/ /app/services/transcription_mcp/ /app/services/v1/ /app/infrastructure/prompts/
USER appuser

# The base image already has the CMD configured for gunicorn
# No need to change anything else - it will use existing entrypoint
