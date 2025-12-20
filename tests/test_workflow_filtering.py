# Copyright (c) 2025
# Tests for Workflow Filtering Feature in Project Start Endpoint

"""
Test suite for the workflow filtering feature in POST /v1/autoedit/project/{id}/start

Tests verify:
1. Schema accepts new parameters (workflow_ids, include_failed)
2. start_project_pipeline() has correct signature
3. Response includes skipped_by_status field
4. Backward compatibility maintained
"""

import pytest
import os
import sys
import ast
import re

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


class TestSchemaUpdate:
    """Test that START_PROJECT_SCHEMA accepts new parameters."""

    def test_project_api_exists(self):
        """Verify project_api.py exists."""
        api_path = os.path.join(PROJECT_ROOT, "routes", "v1", "autoedit", "project_api.py")
        assert os.path.exists(api_path), f"project_api.py not found at {api_path}"

    def test_schema_has_workflow_ids_property(self):
        """Verify schema includes workflow_ids property."""
        api_path = os.path.join(PROJECT_ROOT, "routes", "v1", "autoedit", "project_api.py")
        with open(api_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for workflow_ids in START_PROJECT_SCHEMA
        assert '"workflow_ids"' in content or "'workflow_ids'" in content, \
            "workflow_ids not found in START_PROJECT_SCHEMA"

    def test_schema_has_include_failed_property(self):
        """Verify schema includes include_failed property."""
        api_path = os.path.join(PROJECT_ROOT, "routes", "v1", "autoedit", "project_api.py")
        with open(api_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for include_failed in START_PROJECT_SCHEMA
        assert '"include_failed"' in content or "'include_failed'" in content, \
            "include_failed not found in START_PROJECT_SCHEMA"

    def test_workflow_ids_is_array_type(self):
        """Verify workflow_ids is defined as array type."""
        api_path = os.path.join(PROJECT_ROOT, "routes", "v1", "autoedit", "project_api.py")
        with open(api_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Look for array definition near workflow_ids
        # Pattern: "workflow_ids": { ... "type": "array"
        pattern = r'"workflow_ids"[^}]*"type":\s*"array"'
        assert re.search(pattern, content, re.DOTALL), \
            "workflow_ids should be defined as array type"

    def test_include_failed_is_boolean_type(self):
        """Verify include_failed is defined as boolean type."""
        api_path = os.path.join(PROJECT_ROOT, "routes", "v1", "autoedit", "project_api.py")
        with open(api_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Look for boolean definition near include_failed
        pattern = r'"include_failed"[^}]*"type":\s*"boolean"'
        assert re.search(pattern, content, re.DOTALL), \
            "include_failed should be defined as boolean type"


class TestStartProjectPipelineSignature:
    """Test that start_project_pipeline has correct function signature."""

    def test_task_queue_exists(self):
        """Verify task_queue.py exists."""
        queue_path = os.path.join(PROJECT_ROOT, "services", "v1", "autoedit", "task_queue.py")
        assert os.path.exists(queue_path), f"task_queue.py not found at {queue_path}"

    def test_function_accepts_workflow_ids_param(self):
        """Verify start_project_pipeline accepts workflow_ids parameter."""
        queue_path = os.path.join(PROJECT_ROOT, "services", "v1", "autoedit", "task_queue.py")
        with open(queue_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Parse AST to find function definition
        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "start_project_pipeline":
                arg_names = [arg.arg for arg in node.args.args]
                assert "workflow_ids" in arg_names, \
                    "start_project_pipeline should accept workflow_ids parameter"
                return

        pytest.fail("start_project_pipeline function not found")

    def test_function_accepts_include_failed_param(self):
        """Verify start_project_pipeline accepts include_failed parameter."""
        queue_path = os.path.join(PROJECT_ROOT, "services", "v1", "autoedit", "task_queue.py")
        with open(queue_path, "r", encoding="utf-8") as f:
            content = f.read()

        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "start_project_pipeline":
                arg_names = [arg.arg for arg in node.args.args]
                assert "include_failed" in arg_names, \
                    "start_project_pipeline should accept include_failed parameter"
                return

        pytest.fail("start_project_pipeline function not found")


class TestResponseEnhancement:
    """Test that response includes enhanced fields."""

    def test_response_includes_skipped_by_status(self):
        """Verify response construction includes skipped_by_status."""
        queue_path = os.path.join(PROJECT_ROOT, "services", "v1", "autoedit", "task_queue.py")
        with open(queue_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "skipped_by_status" in content, \
            "Response should include skipped_by_status field"

    def test_response_includes_skipped_count(self):
        """Verify response construction includes skipped_count."""
        queue_path = os.path.join(PROJECT_ROOT, "services", "v1", "autoedit", "task_queue.py")
        with open(queue_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "skipped_count" in content, \
            "Response should include skipped_count field"

    def test_response_includes_invalid_workflow_ids(self):
        """Verify response construction includes invalid_workflow_ids."""
        queue_path = os.path.join(PROJECT_ROOT, "services", "v1", "autoedit", "task_queue.py")
        with open(queue_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "invalid_workflow_ids" in content, \
            "Response should include invalid_workflow_ids field"


class TestStartableStatesLogic:
    """Test that startable states logic is correct."""

    def test_created_is_startable_state(self):
        """Verify 'created' is a startable state."""
        queue_path = os.path.join(PROJECT_ROOT, "services", "v1", "autoedit", "task_queue.py")
        with open(queue_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Look for startable_states definition with "created"
        assert 'startable_states = ["created"]' in content or \
               "startable_states = ['created']" in content, \
            "startable_states should include 'created'"

    def test_error_added_when_include_failed(self):
        """Verify 'error' is added to startable_states when include_failed=True."""
        queue_path = os.path.join(PROJECT_ROOT, "services", "v1", "autoedit", "task_queue.py")
        with open(queue_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Look for logic that adds "error" to startable_states
        pattern = r'if include_failed:\s*\n\s*startable_states\.append\(["\']error["\']\)'
        assert re.search(pattern, content), \
            "Should add 'error' to startable_states when include_failed=True"


class TestHandlerPassesParams:
    """Test that endpoint handler passes new params to pipeline function."""

    def test_handler_extracts_workflow_ids(self):
        """Verify handler extracts workflow_ids from request data."""
        api_path = os.path.join(PROJECT_ROOT, "routes", "v1", "autoedit", "project_api.py")
        with open(api_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert 'data.get("workflow_ids")' in content or \
               "data.get('workflow_ids')" in content, \
            "Handler should extract workflow_ids from data"

    def test_handler_extracts_include_failed(self):
        """Verify handler extracts include_failed from request data."""
        api_path = os.path.join(PROJECT_ROOT, "routes", "v1", "autoedit", "project_api.py")
        with open(api_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert 'data.get("include_failed"' in content or \
               "data.get('include_failed'" in content, \
            "Handler should extract include_failed from data"

    def test_handler_passes_workflow_ids_to_pipeline(self):
        """Verify handler passes workflow_ids to start_project_pipeline."""
        api_path = os.path.join(PROJECT_ROOT, "routes", "v1", "autoedit", "project_api.py")
        with open(api_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "workflow_ids=workflow_ids" in content or \
               "workflow_ids = workflow_ids" in content, \
            "Handler should pass workflow_ids to start_project_pipeline"

    def test_handler_passes_include_failed_to_pipeline(self):
        """Verify handler passes include_failed to start_project_pipeline."""
        api_path = os.path.join(PROJECT_ROOT, "routes", "v1", "autoedit", "project_api.py")
        with open(api_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "include_failed=include_failed" in content or \
               "include_failed = include_failed" in content, \
            "Handler should pass include_failed to start_project_pipeline"


class TestBackwardCompatibility:
    """Test that backward compatibility is maintained."""

    def test_existing_params_still_work(self):
        """Verify parallel_limit and webhook_url still in schema."""
        api_path = os.path.join(PROJECT_ROOT, "routes", "v1", "autoedit", "project_api.py")
        with open(api_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert '"parallel_limit"' in content, "parallel_limit should still be in schema"
        assert '"webhook_url"' in content, "webhook_url should still be in schema"

    def test_function_has_default_for_workflow_ids(self):
        """Verify workflow_ids has default value (None)."""
        queue_path = os.path.join(PROJECT_ROOT, "services", "v1", "autoedit", "task_queue.py")
        with open(queue_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for default value in function signature
        assert "workflow_ids: Optional[list] = None" in content or \
               "workflow_ids=None" in content, \
            "workflow_ids should have default value None"

    def test_function_has_default_for_include_failed(self):
        """Verify include_failed has default value (False)."""
        queue_path = os.path.join(PROJECT_ROOT, "services", "v1", "autoedit", "task_queue.py")
        with open(queue_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "include_failed: bool = False" in content or \
               "include_failed=False" in content, \
            "include_failed should have default value False"


class TestStatusGroupingLogic:
    """Test that status grouping logic is implemented."""

    def test_skipped_workflows_grouped_by_status(self):
        """Verify skipped workflows are grouped by their status."""
        queue_path = os.path.join(PROJECT_ROOT, "services", "v1", "autoedit", "task_queue.py")
        with open(queue_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Look for dictionary grouping logic
        assert "skipped_by_status[status]" in content, \
            "Skipped workflows should be grouped by status in dict"

    def test_workflow_ids_validation(self):
        """Verify invalid workflow_ids are tracked."""
        queue_path = os.path.join(PROJECT_ROOT, "services", "v1", "autoedit", "task_queue.py")
        with open(queue_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for validation that workflow_ids belong to project
        assert "project_workflow_ids" in content, \
            "Should validate workflow_ids against project's workflow_ids"
        assert "invalid_workflow_ids" in content, \
            "Should track invalid workflow_ids"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
