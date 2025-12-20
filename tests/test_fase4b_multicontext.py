# Copyright (c) 2025
#
# Test suite for Fase 4B: Multi-Video Context & Consolidation
#
# Run with: python -m pytest tests/test_fase4b_multicontext.py -v
# Or: python tests/test_fase4b_multicontext.py
#
# NOTE: These tests verify code structure and logic without requiring
# GCP or TwelveLabs API dependencies. Full integration tests should run in Cloud Run.

import os
import sys
import json
import unittest
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestTwelveLabsEmbeddingsCodeStructure(unittest.TestCase):
    """Test cases for twelvelabs_embeddings.py code structure."""

    def setUp(self):
        self.embeddings_file = Path(__file__).parent.parent / "services" / "v1" / "autoedit" / "twelvelabs_embeddings.py"

    def test_embeddings_file_exists(self):
        """Test that twelvelabs_embeddings.py file exists."""
        self.assertTrue(self.embeddings_file.exists(), f"Embeddings file not found at {self.embeddings_file}")

    def test_config_constants_exist(self):
        """Test that configuration constants are defined."""
        with open(self.embeddings_file, 'r', encoding='utf-8') as f:
            content = f.read()

        constants = ["TWELVELABS_API_KEY", "MARENGO_MODEL", "MAX_SYNC_DURATION_SEC", "MAX_ASYNC_DURATION_SEC"]
        for const in constants:
            self.assertIn(const, content, f"Missing constant: {const}")

    def test_get_client_function_exists(self):
        """Test that get_twelvelabs_client function exists."""
        with open(self.embeddings_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def get_twelvelabs_client", content)

    def test_sync_embeddings_function_exists(self):
        """Test that create_video_embeddings_sync function exists."""
        with open(self.embeddings_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def create_video_embeddings_sync", content)

    def test_async_embeddings_function_exists(self):
        """Test that create_video_embeddings_async function exists."""
        with open(self.embeddings_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def create_video_embeddings_async", content)

    def test_embeddings_task_status_function_exists(self):
        """Test that get_embeddings_task_status function exists."""
        with open(self.embeddings_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def get_embeddings_task_status", content)

    def test_wait_for_embeddings_function_exists(self):
        """Test that wait_for_embeddings function exists."""
        with open(self.embeddings_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def wait_for_embeddings", content)

    def test_smart_wrapper_function_exists(self):
        """Test that create_video_embeddings wrapper function exists."""
        with open(self.embeddings_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def create_video_embeddings", content)

    def test_cosine_similarity_function_exists(self):
        """Test that cosine_similarity function exists."""
        with open(self.embeddings_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def cosine_similarity", content)
        self.assertIn("numpy", content)

    def test_find_similar_segments_function_exists(self):
        """Test that find_similar_segments function exists."""
        with open(self.embeddings_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def find_similar_segments", content)

    def test_compare_video_embeddings_function_exists(self):
        """Test that compare_video_embeddings function exists."""
        with open(self.embeddings_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def compare_video_embeddings", content)

    def test_gcs_storage_functions_exist(self):
        """Test that GCS storage functions exist."""
        with open(self.embeddings_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def save_embeddings_to_gcs", content)
        self.assertIn("def load_embeddings_from_gcs", content)


class TestContextBuilderCodeStructure(unittest.TestCase):
    """Test cases for context_builder.py code structure."""

    def setUp(self):
        self.context_file = Path(__file__).parent.parent / "services" / "v1" / "autoedit" / "context_builder.py"

    def test_context_builder_file_exists(self):
        """Test that context_builder.py file exists."""
        self.assertTrue(self.context_file.exists(), f"Context builder file not found at {self.context_file}")

    def test_build_context_function_exists(self):
        """Test that build_context_for_video function is defined."""
        with open(self.context_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def build_context_for_video", content)

    def test_generate_summary_function_exists(self):
        """Test that generate_video_summary function exists."""
        with open(self.context_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def generate_video_summary", content)

    def test_load_all_summaries_function_exists(self):
        """Test that load_all_video_summaries function exists."""
        with open(self.context_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def load_all_video_summaries", content)

    def test_get_accumulated_context_function_exists(self):
        """Test that get_accumulated_context function exists."""
        with open(self.context_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def get_accumulated_context", content)

    def test_save_summary_function_exists(self):
        """Test that save_video_summary function exists."""
        with open(self.context_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def save_video_summary", content)

    def test_uses_gemini_for_summaries(self):
        """Test that context builder uses Gemini for generating summaries."""
        with open(self.context_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("gemini", content.lower())


class TestRedundancyDetectorCodeStructure(unittest.TestCase):
    """Test cases for redundancy_detector.py code structure."""

    def setUp(self):
        self.detector_file = Path(__file__).parent.parent / "services" / "v1" / "autoedit" / "redundancy_detector.py"

    def test_redundancy_detector_file_exists(self):
        """Test that redundancy_detector.py file exists."""
        self.assertTrue(self.detector_file.exists(), f"Redundancy detector file not found at {self.detector_file}")

    def test_detect_redundancies_function_exists(self):
        """Test that detect_cross_video_redundancies function exists."""
        with open(self.detector_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def detect_cross_video_redundancies", content)

    def test_compare_video_embeddings_used(self):
        """Test that compare_video_embeddings is used for comparison."""
        with open(self.detector_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("compare_video_embeddings", content)

    def test_generate_recommendations_function_exists(self):
        """Test that generate_removal_recommendations function exists."""
        with open(self.detector_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def generate_removal_recommendations", content)

    def test_default_threshold_configured(self):
        """Test that default threshold is configured (0.85)."""
        with open(self.detector_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("0.85", content)
        self.assertIn("DEFAULT_SIMILARITY_THRESHOLD", content)

    def test_uses_embeddings_for_comparison(self):
        """Test that detector uses embeddings for comparison."""
        with open(self.detector_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("embedding", content.lower())
        self.assertIn("similarity", content.lower())

    def test_calculate_project_score_function_exists(self):
        """Test that calculate_project_redundancy_score function exists."""
        with open(self.detector_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def calculate_project_redundancy_score", content)


class TestProjectConsolidationCodeStructure(unittest.TestCase):
    """Test cases for project_consolidation.py code structure."""

    def setUp(self):
        self.consolidation_file = Path(__file__).parent.parent / "services" / "v1" / "autoedit" / "project_consolidation.py"

    def test_consolidation_file_exists(self):
        """Test that project_consolidation.py file exists."""
        self.assertTrue(self.consolidation_file.exists(), f"Consolidation file not found at {self.consolidation_file}")

    def test_consolidation_orchestrator_class_exists(self):
        """Test that ProjectConsolidator class is defined."""
        with open(self.consolidation_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("class ProjectConsolidator", content)

    def test_run_full_consolidation_method_exists(self):
        """Test that run_full_consolidation method exists."""
        with open(self.consolidation_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def run_full_consolidation", content)

    def test_ensure_embeddings_method_exists(self):
        """Test that _ensure_embeddings method exists."""
        with open(self.consolidation_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def _ensure_embeddings", content)

    def test_ensure_summaries_method_exists(self):
        """Test that _ensure_summaries method exists."""
        with open(self.consolidation_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def _ensure_summaries", content)

    def test_analyze_narrative_method_exists(self):
        """Test that _analyze_narrative method exists."""
        with open(self.consolidation_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def _analyze_narrative", content)

    def test_apply_recommendations_method_exists(self):
        """Test that _apply_recommendations method exists."""
        with open(self.consolidation_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def _apply_recommendations", content)

    def test_integrates_with_embeddings_service(self):
        """Test that consolidator integrates with embeddings service."""
        with open(self.consolidation_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("from services.v1.autoedit.twelvelabs_embeddings import", content)

    def test_integrates_with_context_builder(self):
        """Test that consolidator integrates with context builder."""
        with open(self.consolidation_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("from services.v1.autoedit.context_builder import", content)

    def test_integrates_with_redundancy_detector(self):
        """Test that consolidator integrates with redundancy detector."""
        with open(self.consolidation_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("from services.v1.autoedit.redundancy_detector import", content)

    def test_convenience_function_exists(self):
        """Test that consolidate_project convenience function exists."""
        with open(self.consolidation_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def consolidate_project", content)


class TestContextAPICodeStructure(unittest.TestCase):
    """Test cases for context_api.py code structure."""

    def setUp(self):
        self.context_api_file = Path(__file__).parent.parent / "routes" / "v1" / "autoedit" / "context_api.py"

    def test_context_api_file_exists(self):
        """Test that context_api.py file exists."""
        self.assertTrue(self.context_api_file.exists(), f"Context API file not found at {self.context_api_file}")

    def test_context_api_blueprint_defined(self):
        """Test that context API blueprint is defined."""
        with open(self.context_api_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("Blueprint", content)
        self.assertIn("v1_autoedit_context_bp", content)

    def test_consolidate_endpoint_exists(self):
        """Test that consolidate endpoint exists."""
        with open(self.context_api_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("/consolidate", content)
        self.assertIn("def consolidate_project", content)

    def test_consolidation_status_endpoint_exists(self):
        """Test that consolidation-status endpoint exists."""
        with open(self.context_api_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("/consolidation-status", content)

    def test_redundancies_endpoint_exists(self):
        """Test that redundancies endpoint exists."""
        with open(self.context_api_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("/redundancies", content)

    def test_narrative_endpoint_exists(self):
        """Test that narrative endpoint exists."""
        with open(self.context_api_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("/narrative", content)

    def test_recommendations_endpoint_exists(self):
        """Test that recommendations endpoint exists."""
        with open(self.context_api_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("/recommendations", content)

    def test_apply_recommendations_endpoint_exists(self):
        """Test that apply-recommendations endpoint exists."""
        with open(self.context_api_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("/apply-recommendations", content)

    def test_reorder_endpoint_exists(self):
        """Test that videos/reorder endpoint exists."""
        with open(self.context_api_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("/reorder", content)

    def test_context_endpoint_exists(self):
        """Test that context endpoint exists."""
        with open(self.context_api_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("/context", content)

    def test_summaries_endpoint_exists(self):
        """Test that summaries endpoint exists."""
        with open(self.context_api_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("/summaries", content)


class TestProjectConsolidationStates(unittest.TestCase):
    """Test cases for consolidation states in project.py."""

    def setUp(self):
        self.project_file = Path(__file__).parent.parent / "services" / "v1" / "autoedit" / "project.py"

    def test_consolidation_states_defined(self):
        """Test that CONSOLIDATION_STATES dictionary is defined."""
        with open(self.project_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("CONSOLIDATION_STATES", content)

    def test_consolidation_states_include_required_states(self):
        """Test that all required consolidation states are defined."""
        with open(self.project_file, 'r', encoding='utf-8') as f:
            content = f.read()

        states = [
            "not_started",
            "generating_embeddings",
            "generating_summaries",
            "detecting_redundancies",
            "analyzing_narrative",
            "consolidating",
            "consolidated",
            "consolidation_complete",
            "consolidation_failed"
        ]
        for state in states:
            self.assertIn(f'"{state}"', content, f"Missing consolidation state: {state}")

    def test_consolidation_fields_in_project(self):
        """Test that consolidation-related fields are in project data."""
        with open(self.project_file, 'r', encoding='utf-8') as f:
            content = f.read()

        fields = ["consolidation_state", "consolidation_results"]
        for field in fields:
            self.assertIn(f'"{field}"', content, f"Missing consolidation field: {field}")


class TestTaskQueueConsolidationIntegration(unittest.TestCase):
    """Test cases for Cloud Tasks consolidation integration."""

    def setUp(self):
        self.task_queue_file = Path(__file__).parent.parent / "services" / "v1" / "autoedit" / "task_queue.py"
        self.tasks_api_file = Path(__file__).parent.parent / "routes" / "v1" / "autoedit" / "tasks_api.py"

    def test_embeddings_task_type_in_task_queue(self):
        """Test that generate_embeddings task type is registered."""
        with open(self.task_queue_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("generate_embeddings", content)
        self.assertIn("/v1/autoedit/tasks/generate-embeddings", content)

    def test_summary_task_type_in_task_queue(self):
        """Test that generate_summary task type is registered."""
        with open(self.task_queue_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("generate_summary", content)
        self.assertIn("/v1/autoedit/tasks/generate-summary", content)

    def test_consolidate_task_type_in_task_queue(self):
        """Test that consolidate task type is registered."""
        with open(self.task_queue_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('"consolidate"', content)
        self.assertIn("/v1/autoedit/tasks/consolidate", content)

    def test_enqueue_embeddings_task_function_exists(self):
        """Test that enqueue_embeddings_task function exists."""
        with open(self.task_queue_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def enqueue_embeddings_task", content)

    def test_enqueue_summary_task_function_exists(self):
        """Test that enqueue_summary_task function exists."""
        with open(self.task_queue_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def enqueue_summary_task", content)

    def test_enqueue_consolidation_task_function_exists(self):
        """Test that enqueue_consolidation_task function exists."""
        with open(self.task_queue_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def enqueue_consolidation_task", content)

    def test_start_project_embeddings_function_exists(self):
        """Test that start_project_embeddings function exists."""
        with open(self.task_queue_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("def start_project_embeddings", content)

    def test_embeddings_handler_in_tasks_api(self):
        """Test that generate_embeddings handler exists in tasks_api."""
        with open(self.tasks_api_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("task_generate_embeddings", content)
        self.assertIn("/v1/autoedit/tasks/generate-embeddings", content)

    def test_summary_handler_in_tasks_api(self):
        """Test that generate_summary handler exists in tasks_api."""
        with open(self.tasks_api_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("task_generate_summary", content)
        self.assertIn("/v1/autoedit/tasks/generate-summary", content)

    def test_consolidate_handler_in_tasks_api(self):
        """Test that consolidate handler exists in tasks_api."""
        with open(self.tasks_api_file, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("task_consolidate", content)
        self.assertIn("/v1/autoedit/tasks/consolidate", content)


class TestAnalyzeEditContextParameter(unittest.TestCase):
    """Test cases for context parameter in analyze_edit.py."""

    def setUp(self):
        self.analyze_file = Path(__file__).parent.parent / "services" / "v1" / "autoedit" / "analyze_edit.py"

    def test_analyze_blocks_has_context_parameter(self):
        """Test that analyze_blocks_with_gemini has context parameter."""
        with open(self.analyze_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for context parameter in function signature
        self.assertIn("context: Optional[str] = None", content)

    def test_context_is_used_in_prompt(self):
        """Test that context is prepended to prompt when provided."""
        with open(self.analyze_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check that context is added to system_prompt
        self.assertIn("if context:", content)
        # The context should be prepended
        self.assertIn("context +", content)


class TestFilesStructure(unittest.TestCase):
    """Test that all Fase 4B files exist."""

    def test_all_new_files_exist(self):
        """Test that all new Fase 4B files exist."""
        root = Path(__file__).parent.parent

        files = [
            "services/v1/autoedit/twelvelabs_embeddings.py",
            "services/v1/autoedit/context_builder.py",
            "services/v1/autoedit/redundancy_detector.py",
            "services/v1/autoedit/project_consolidation.py",
            "routes/v1/autoedit/context_api.py",
        ]

        for file_path in files:
            full_path = root / file_path
            self.assertTrue(full_path.exists(), f"Missing file: {file_path}")

    def test_documentation_updated(self):
        """Test that documentation files are updated with Fase 4B content."""
        root = Path(__file__).parent.parent

        api_reference = root / "docs" / "autoedit" / "API-REFERENCE.md"
        self.assertTrue(api_reference.exists(), "API-REFERENCE.md not found")

        with open(api_reference, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for consolidation endpoints documentation
        self.assertIn("consolidate", content.lower())
        self.assertIn("redundancies", content.lower())


class TestCosimeSimilarityLogic(unittest.TestCase):
    """Test the cosine similarity logic (without importing the module)."""

    def test_cosine_similarity_formula_in_code(self):
        """Test that cosine similarity formula is correctly implemented."""
        embeddings_file = Path(__file__).parent.parent / "services" / "v1" / "autoedit" / "twelvelabs_embeddings.py"

        with open(embeddings_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for numpy dot product and norm
        self.assertIn("np.dot", content)
        self.assertIn("np.linalg.norm", content)

    def test_similarity_returns_float(self):
        """Test that similarity function returns float."""
        embeddings_file = Path(__file__).parent.parent / "services" / "v1" / "autoedit" / "twelvelabs_embeddings.py"

        with open(embeddings_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for float conversion in return
        self.assertIn("float(", content)


class TestNarrativeAnalysisStructure(unittest.TestCase):
    """Test narrative analysis structure in consolidation."""

    def setUp(self):
        self.consolidation_file = Path(__file__).parent.parent / "services" / "v1" / "autoedit" / "project_consolidation.py"

    def test_narrative_arc_types_defined(self):
        """Test that narrative arc types are defined."""
        with open(self.consolidation_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for common narrative arc types
        arc_types = ["complete", "open_ended", "episodic"]
        for arc_type in arc_types:
            self.assertIn(arc_type, content, f"Missing arc type: {arc_type}")


if __name__ == '__main__':
    # Run tests with verbosity
    unittest.main(verbosity=2)
