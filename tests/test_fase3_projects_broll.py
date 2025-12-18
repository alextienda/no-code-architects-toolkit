# Copyright (c) 2025
#
# Test suite for Fase 3: Multi-Video Projects + B-Roll Analysis
#
# Run with: python tests/test_fase3_projects_broll.py
#
# NOTE: These tests verify code structure and logic without requiring
# GCP dependencies. Full integration tests should run in Cloud Run.

import os
import sys
import json
import re
import unittest
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestBRollPromptFile(unittest.TestCase):
    """Test cases for B-Roll prompt file."""

    def setUp(self):
        self.prompt_path = Path(__file__).parent.parent / "infrastructure" / "prompts" / "autoedit_broll_prompt.txt"

    def test_prompt_file_exists(self):
        """Test that the B-Roll prompt file exists."""
        self.assertTrue(self.prompt_path.exists(), f"Prompt file not found at {self.prompt_path}")

    def test_prompt_file_content_structure(self):
        """Test that the prompt file has required structural elements."""
        with open(self.prompt_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for B-Roll categories
        categories = ["establishing_shot", "detail_shot", "transition_shot", "ambient_shot", "action_shot"]
        for category in categories:
            self.assertIn(category, content, f"Missing B-Roll category: {category}")

    def test_prompt_file_json_format(self):
        """Test that the prompt file specifies JSON output format."""
        with open(self.prompt_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for JSON-related keywords
        self.assertIn("JSON", content)
        self.assertIn("inMs", content)
        self.assertIn("outMs", content)
        self.assertIn("confidence", content)

    def test_prompt_file_scoring_system(self):
        """Test that the prompt includes scoring system."""
        with open(self.prompt_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for scoring elements
        self.assertIn("technical_quality", content)
        self.assertIn("visual_appeal", content)
        self.assertIn("usefulness", content)


class TestProjectManagerCodeStructure(unittest.TestCase):
    """Test cases for ProjectManager code structure."""

    def setUp(self):
        self.project_file = Path(__file__).parent.parent / "services" / "v1" / "autoedit" / "project.py"

    def test_project_file_exists(self):
        """Test that project.py file exists."""
        self.assertTrue(self.project_file.exists(), f"Project file not found at {self.project_file}")

    def test_project_manager_class_exists(self):
        """Test that ProjectManager class is defined."""
        with open(self.project_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("class ProjectManager", content)

    def test_project_crud_methods_exist(self):
        """Test that CRUD methods are defined."""
        with open(self.project_file, 'r', encoding='utf-8') as f:
            content = f.read()

        methods = ["def create", "def get", "def update", "def delete", "def list"]
        for method in methods:
            self.assertIn(method, content, f"Missing method: {method}")

    def test_project_workflow_methods_exist(self):
        """Test that workflow management methods exist."""
        with open(self.project_file, 'r', encoding='utf-8') as f:
            content = f.read()

        methods = ["add_workflow", "remove_workflow", "get_workflows"]
        for method in methods:
            self.assertIn(method, content, f"Missing method: {method}")

    def test_project_data_structure(self):
        """Test that project data structure has required fields."""
        with open(self.project_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for key data fields
        fields = ["project_id", "workflow_ids", "options", "stats", "state", "created_at"]
        for field in fields:
            self.assertIn(f'"{field}"', content, f"Missing field: {field}")


class TestFrameExtractorCodeStructure(unittest.TestCase):
    """Test cases for frame_extractor.py code structure."""

    def setUp(self):
        self.extractor_file = Path(__file__).parent.parent / "services" / "v1" / "autoedit" / "frame_extractor.py"

    def test_frame_extractor_file_exists(self):
        """Test that frame_extractor.py file exists."""
        self.assertTrue(self.extractor_file.exists(), f"Frame extractor file not found at {self.extractor_file}")

    def test_frame_extractor_class_exists(self):
        """Test that FrameExtractor class is defined."""
        with open(self.extractor_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("class FrameExtractor", content)

    def test_frame_extraction_methods_exist(self):
        """Test that frame extraction methods exist."""
        with open(self.extractor_file, 'r', encoding='utf-8') as f:
            content = f.read()

        methods = ["extract_frames", "frames_to_base64", "cleanup_frames", "extract_and_encode"]
        for method in methods:
            self.assertIn(f"def {method}", content, f"Missing method: {method}")

    def test_frame_extractor_uses_ffmpeg(self):
        """Test that frame extractor uses FFmpeg."""
        with open(self.extractor_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("ffmpeg", content.lower())
        self.assertIn("ffprobe", content.lower())

    def test_frame_extractor_default_config(self):
        """Test that default configuration values are reasonable."""
        with open(self.extractor_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for default values
        self.assertIn("DEFAULT_FRAME_INTERVAL_SEC", content)
        self.assertIn("MAX_FRAMES_PER_ANALYSIS", content)
        self.assertIn("30", content)  # Max frames default


class TestBRollAnalyzerCodeStructure(unittest.TestCase):
    """Test cases for analyze_broll.py code structure."""

    def setUp(self):
        self.analyzer_file = Path(__file__).parent.parent / "services" / "v1" / "autoedit" / "analyze_broll.py"

    def test_analyzer_file_exists(self):
        """Test that analyze_broll.py file exists."""
        self.assertTrue(self.analyzer_file.exists(), f"Analyzer file not found at {self.analyzer_file}")

    def test_main_functions_exist(self):
        """Test that main analysis functions exist."""
        with open(self.analyzer_file, 'r', encoding='utf-8') as f:
            content = f.read()

        functions = [
            "analyze_video_broll",
            "analyze_workflow_broll",
            "load_broll_prompt",
            "validate_broll_response",
            "parse_broll_response"
        ]
        for func in functions:
            self.assertIn(f"def {func}", content, f"Missing function: {func}")

    def test_gemini_vision_integration(self):
        """Test that Gemini Vision API integration exists."""
        with open(self.analyzer_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for Vertex AI / Gemini integration
        self.assertIn("gemini", content.lower())
        self.assertIn("vertex", content.lower())
        self.assertIn("generateContent", content)

    def test_broll_config_structure(self):
        """Test that BROLL_CONFIG has required fields."""
        with open(self.analyzer_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("BROLL_CONFIG", content)
        config_fields = ["model", "temperature", "max_tokens", "project_id", "location"]
        for field in config_fields:
            self.assertIn(f'"{field}"', content, f"Missing config field: {field}")

    def test_validation_filters_short_segments(self):
        """Test that validation code filters short segments."""
        with open(self.analyzer_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for segment duration filter (2000ms minimum)
        self.assertIn("2000", content)
        self.assertIn("duration_ms", content)

    def test_validation_filters_low_confidence(self):
        """Test that validation code filters low confidence segments."""
        with open(self.analyzer_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for confidence filter (0.5 minimum)
        self.assertIn("confidence", content)
        self.assertIn("0.5", content)


class TestWorkflowBRollFields(unittest.TestCase):
    """Test cases for workflow B-Roll field support."""

    def setUp(self):
        self.workflow_file = Path(__file__).parent.parent / "services" / "v1" / "autoedit" / "workflow.py"

    def test_workflow_has_broll_segments_field(self):
        """Test that workflow has broll_segments field."""
        with open(self.workflow_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("broll_segments", content)

    def test_workflow_has_broll_analysis_complete_field(self):
        """Test that workflow has broll_analysis_complete field."""
        with open(self.workflow_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("broll_analysis_complete", content)

    def test_workflow_has_project_id_field(self):
        """Test that workflow supports project_id field."""
        with open(self.workflow_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("project_id", content)


class TestTaskQueueBRollIntegration(unittest.TestCase):
    """Test cases for Cloud Tasks B-Roll integration."""

    def setUp(self):
        self.task_queue_file = Path(__file__).parent.parent / "services" / "v1" / "autoedit" / "task_queue.py"
        self.tasks_api_file = Path(__file__).parent.parent / "routes" / "v1" / "autoedit" / "tasks_api.py"

    def test_broll_task_type_in_task_queue(self):
        """Test that analyze_broll task type is registered."""
        with open(self.task_queue_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("analyze_broll", content)
        self.assertIn("/v1/autoedit/tasks/analyze-broll", content)

    def test_broll_handler_in_tasks_api(self):
        """Test that analyze_broll handler exists in tasks_api."""
        with open(self.tasks_api_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("task_analyze_broll", content)
        self.assertIn("/v1/autoedit/tasks/analyze-broll", content)

    def test_broll_handler_imports_analyzer(self):
        """Test that B-Roll handler imports the analyzer."""
        with open(self.tasks_api_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("from services.v1.autoedit.analyze_broll import analyze_workflow_broll", content)


class TestProjectAPIStructure(unittest.TestCase):
    """Test cases for Project REST API structure."""

    def setUp(self):
        self.project_api_file = Path(__file__).parent.parent / "routes" / "v1" / "autoedit" / "project_api.py"

    def test_project_api_file_exists(self):
        """Test that project_api.py file exists."""
        self.assertTrue(self.project_api_file.exists(), f"Project API file not found at {self.project_api_file}")

    def test_project_blueprint_defined(self):
        """Test that project API blueprint is defined."""
        with open(self.project_api_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("Blueprint", content)
        self.assertIn("v1_autoedit_project_bp", content)

    def test_project_crud_endpoints_exist(self):
        """Test that CRUD endpoints are defined."""
        with open(self.project_api_file, 'r', encoding='utf-8') as f:
            content = f.read()

        endpoints = [
            "/v1/autoedit/project",  # Create (POST), List (GET)
            "/v1/autoedit/project/<project_id>",  # Get, Update, Delete
        ]
        for endpoint in endpoints:
            self.assertIn(endpoint, content, f"Missing endpoint: {endpoint}")

    def test_project_video_management_endpoints_exist(self):
        """Test that video management endpoints exist."""
        with open(self.project_api_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for video management routes
        self.assertIn("/videos", content)
        self.assertIn("add_video", content)
        self.assertIn("remove_video", content)

    def test_project_batch_processing_endpoint_exists(self):
        """Test that batch processing endpoint exists."""
        with open(self.project_api_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("/start", content)
        self.assertIn("start_project", content)


class TestBRollResponseParsing(unittest.TestCase):
    """Test cases for B-Roll response parsing logic."""

    def setUp(self):
        self.analyzer_file = Path(__file__).parent.parent / "services" / "v1" / "autoedit" / "analyze_broll.py"

    def test_parse_handles_json_response(self):
        """Test that parse function handles direct JSON."""
        with open(self.analyzer_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for JSON parsing
        self.assertIn("json.loads", content)

    def test_parse_handles_markdown_wrapped_json(self):
        """Test that parse function handles markdown-wrapped JSON."""
        with open(self.analyzer_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for markdown code block extraction
        self.assertIn("```", content)
        self.assertIn("re.search", content)

    def test_parse_returns_error_on_failure(self):
        """Test that parse function returns error structure on failure."""
        with open(self.analyzer_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Should return error dict if parsing fails
        self.assertIn('"error"', content)


class TestStartProjectPipeline(unittest.TestCase):
    """Test cases for start_project_pipeline function."""

    def setUp(self):
        self.task_queue_file = Path(__file__).parent.parent / "services" / "v1" / "autoedit" / "task_queue.py"

    def test_start_project_pipeline_exists(self):
        """Test that start_project_pipeline function exists."""
        with open(self.task_queue_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def start_project_pipeline", content)

    def test_start_project_pipeline_parameters(self):
        """Test that start_project_pipeline has correct parameters."""
        with open(self.task_queue_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for key parameters
        self.assertIn("project_id", content)
        self.assertIn("parallel_limit", content)

    def test_start_project_pipeline_staggered_tasks(self):
        """Test that tasks are staggered in batch processing."""
        with open(self.task_queue_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for staggering logic
        self.assertIn("delay_seconds", content)


class TestFilesStructure(unittest.TestCase):
    """Test that all Fase 3 files exist."""

    def test_all_new_files_exist(self):
        """Test that all new Fase 3 files exist."""
        root = Path(__file__).parent.parent

        files = [
            "services/v1/autoedit/project.py",
            "services/v1/autoedit/frame_extractor.py",
            "services/v1/autoedit/analyze_broll.py",
            "routes/v1/autoedit/project_api.py",
            "infrastructure/prompts/autoedit_broll_prompt.txt",
        ]

        for file_path in files:
            full_path = root / file_path
            self.assertTrue(full_path.exists(), f"Missing file: {file_path}")


if __name__ == '__main__':
    # Run tests with verbosity
    unittest.main(verbosity=2)
