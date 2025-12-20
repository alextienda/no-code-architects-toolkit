# Copyright (c) 2025
# Tests for v1.5.0 features:
# - Aspect ratio preservation in preview/render
# - Creator global profile
# - Project context override
# - Updated blocks in consolidation

"""
Structural tests for v1.5.0 features.
These tests verify code structure using AST parsing without requiring imports.
This avoids the API_KEY environment variable requirement.
"""

import ast
import os
import pytest


def get_ast_tree(file_path: str) -> ast.Module:
    """Parse a Python file and return its AST."""
    with open(file_path, "r", encoding="utf-8") as f:
        return ast.parse(f.read(), filename=file_path)


def get_function_names(tree: ast.Module) -> list:
    """Get all top-level function names from AST."""
    return [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]


def get_class_names(tree: ast.Module) -> list:
    """Get all class names from AST."""
    return [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]


def get_function_params(tree: ast.Module, func_name: str) -> list:
    """Get parameter names for a specific function."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return [arg.arg for arg in node.args.args]
    return []


def get_method_params(tree: ast.Module, class_name: str, method_name: str) -> list:
    """Get parameter names for a class method."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return [arg.arg for arg in item.args.args]
    return []


def get_method_docstring(tree: ast.Module, class_name: str, method_name: str) -> str:
    """Get docstring for a class method."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return ast.get_docstring(item) or ""
    return ""


def has_class_method(tree: ast.Module, class_name: str, method_name: str) -> bool:
    """Check if a class has a specific method."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return True
    return False


def get_dict_assignment(tree: ast.Module, var_name: str) -> dict:
    """Extract a dictionary assignment from AST (simplified)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == var_name:
                    if isinstance(node.value, ast.Dict):
                        result = {}
                        for key, value in zip(node.value.keys, node.value.values):
                            if isinstance(key, ast.Constant):
                                key_val = key.value
                                if isinstance(value, ast.Constant):
                                    result[key_val] = value.value
                                elif isinstance(value, ast.Dict):
                                    result[key_val] = {"_is_dict": True}
                                elif isinstance(value, ast.List):
                                    result[key_val] = {"_is_list": True}
                        return result
    return {}


# =============================================================================
# Test 1: Aspect Ratio Preservation
# =============================================================================

class TestAspectRatioPreservation:
    """Tests for dynamic aspect ratio scaling in preview/render."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup file paths and AST trees."""
        self.ffmpeg_builder_path = "services/v1/autoedit/ffmpeg_builder.py"
        self.preview_path = "services/v1/autoedit/preview.py"

        with open(self.ffmpeg_builder_path, "r", encoding="utf-8") as f:
            self.ffmpeg_builder_content = f.read()
        self.ffmpeg_builder_tree = ast.parse(self.ffmpeg_builder_content)

        with open(self.preview_path, "r", encoding="utf-8") as f:
            self.preview_content = f.read()
        self.preview_tree = ast.parse(self.preview_content)

    def test_ffmpeg_builder_has_get_video_dimensions_function(self):
        """Verify get_video_dimensions_from_url exists."""
        func_names = get_function_names(self.ffmpeg_builder_tree)
        assert "get_video_dimensions_from_url" in func_names

    def test_ffmpeg_builder_has_get_dynamic_scale_function(self):
        """Verify get_dynamic_scale exists."""
        func_names = get_function_names(self.ffmpeg_builder_tree)
        assert "get_dynamic_scale" in func_names

    def test_render_profiles_have_target_short_side(self):
        """Verify render profiles use target_short_side."""
        assert "target_short_side" in self.ffmpeg_builder_content
        # Check for specific values
        assert '"target_short_side": 480' in self.ffmpeg_builder_content
        assert '"target_short_side": 720' in self.ffmpeg_builder_content

    def test_build_preview_payload_accepts_dimensions(self):
        """Verify build_preview_payload accepts video_width and video_height."""
        params = get_function_params(self.ffmpeg_builder_tree, "build_preview_payload")
        assert "video_width" in params
        assert "video_height" in params

    def test_build_final_render_payload_accepts_dimensions(self):
        """Verify build_final_render_payload accepts video_width and video_height."""
        params = get_function_params(self.ffmpeg_builder_tree, "build_final_render_payload")
        assert "video_width" in params
        assert "video_height" in params

    def test_build_ffmpeg_compose_payload_accepts_dimensions(self):
        """Verify build_ffmpeg_compose_payload accepts dimensions."""
        params = get_function_params(self.ffmpeg_builder_tree, "build_ffmpeg_compose_payload")
        assert "video_width" in params
        assert "video_height" in params

    def test_preview_generate_preview_accepts_dimensions(self):
        """Verify generate_preview in preview.py accepts dimensions."""
        params = get_function_params(self.preview_tree, "generate_preview")
        assert "video_width" in params
        assert "video_height" in params

    def test_preview_generate_final_render_accepts_dimensions(self):
        """Verify generate_final_render in preview.py accepts dimensions."""
        params = get_function_params(self.preview_tree, "generate_final_render")
        assert "video_width" in params
        assert "video_height" in params

    def test_get_dynamic_scale_has_target_short_side_param(self):
        """Verify get_dynamic_scale has target_short_side parameter."""
        params = get_function_params(self.ffmpeg_builder_tree, "get_dynamic_scale")
        assert "target_short_side" in params

    def test_get_dynamic_scale_has_width_height_params(self):
        """Verify get_dynamic_scale has width and height parameters."""
        params = get_function_params(self.ffmpeg_builder_tree, "get_dynamic_scale")
        assert "width" in params
        assert "height" in params

    def test_preview_imports_get_video_dimensions(self):
        """Verify preview.py imports the dimension detection function."""
        assert "get_video_dimensions_from_url" in self.preview_content


# =============================================================================
# Test 2: Creator Global Profile
# =============================================================================

class TestCreatorGlobalProfile:
    """Tests for CREATOR_GLOBAL_PROFILE in config."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup file paths and content."""
        self.config_path = "config.py"
        self.context_builder_path = "services/v1/autoedit/context_builder.py"

        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config_content = f.read()
        self.config_tree = ast.parse(self.config_content)

        with open(self.context_builder_path, "r", encoding="utf-8") as f:
            self.context_builder_content = f.read()
        self.context_builder_tree = ast.parse(self.context_builder_content)

    def test_creator_global_profile_exists_in_config(self):
        """Verify CREATOR_GLOBAL_PROFILE is defined in config."""
        assert "CREATOR_GLOBAL_PROFILE" in self.config_content
        assert "CREATOR_GLOBAL_PROFILE = {" in self.config_content

    def test_creator_profile_has_required_fields(self):
        """Verify profile has all required fields."""
        required_fields = ["name", "brand", "audience", "style", "tone"]
        for field in required_fields:
            assert f'"{field}"' in self.config_content, f"Missing field: {field}"

    def test_creator_profile_has_optional_fields(self):
        """Verify profile has optional list fields."""
        assert '"typical_content"' in self.config_content
        assert '"avoid"' in self.config_content

    def test_creator_profile_default_name_uses_env(self):
        """Verify default creator name uses environment variable."""
        assert 'CREATOR_NAME' in self.config_content
        assert '"Alex"' in self.config_content  # Default value

    def test_context_builder_has_get_effective_profile_function(self):
        """Verify get_effective_creator_profile exists."""
        func_names = get_function_names(self.context_builder_tree)
        assert "get_effective_creator_profile" in func_names

    def test_get_effective_profile_accepts_project_context(self):
        """Verify get_effective_creator_profile accepts project_context."""
        params = get_function_params(self.context_builder_tree, "get_effective_creator_profile")
        assert "project_context" in params

    def test_generate_video_summary_accepts_project_context(self):
        """Verify generate_video_summary accepts project_context."""
        params = get_function_params(self.context_builder_tree, "generate_video_summary")
        assert "project_context" in params

    def test_build_context_for_video_accepts_project_context(self):
        """Verify build_context_for_video accepts project_context."""
        params = get_function_params(self.context_builder_tree, "build_context_for_video")
        assert "project_context" in params

    def test_context_builder_imports_creator_profile(self):
        """Verify context_builder imports CREATOR_GLOBAL_PROFILE."""
        assert "CREATOR_GLOBAL_PROFILE" in self.context_builder_content
        assert "from config import CREATOR_GLOBAL_PROFILE" in self.context_builder_content


# =============================================================================
# Test 3: Project Context Override
# =============================================================================

class TestProjectContextOverride:
    """Tests for project_context in project creation."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup file paths and AST trees."""
        self.project_path = "services/v1/autoedit/project.py"
        self.project_api_path = "routes/v1/autoedit/project_api.py"

        with open(self.project_path, "r", encoding="utf-8") as f:
            self.project_content = f.read()
        self.project_tree = ast.parse(self.project_content)

        with open(self.project_api_path, "r", encoding="utf-8") as f:
            self.project_api_content = f.read()
        self.project_api_tree = ast.parse(self.project_api_content)

    def test_create_project_accepts_project_context(self):
        """Verify create_project accepts project_context parameter."""
        params = get_function_params(self.project_tree, "create_project")
        assert "project_context" in params

    def test_project_manager_create_accepts_project_context(self):
        """Verify ProjectManager.create accepts project_context."""
        params = get_method_params(self.project_tree, "ProjectManager", "create")
        assert "project_context" in params

    def test_create_project_schema_has_project_context(self):
        """Verify CREATE_PROJECT_SCHEMA includes project_context."""
        assert "CREATE_PROJECT_SCHEMA" in self.project_api_content
        assert '"project_context"' in self.project_api_content

    def test_project_context_schema_has_expected_fields(self):
        """Verify project_context schema has all expected fields."""
        expected_fields = [
            "campaign", "sponsor", "specific_audience", "tone_override",
            "style_override", "focus", "call_to_action", "keywords_to_keep",
            "keywords_to_avoid", "creator_name"
        ]

        for field in expected_fields:
            assert f'"{field}"' in self.project_api_content, f"Missing field in schema: {field}"

    def test_tone_override_has_enum_values(self):
        """Verify tone_override has predefined enum values."""
        # Check for enum definition in the schema
        assert '"enum"' in self.project_api_content
        # Check for at least one enum value (Spanish values)
        assert '"más técnico"' in self.project_api_content or '"más casual"' in self.project_api_content

    def test_project_api_passes_project_context(self):
        """Verify project API passes project_context to create_project."""
        assert 'project_context = data.get("project_context")' in self.project_api_content
        assert "create_project(name, description, options, project_context)" in self.project_api_content


# =============================================================================
# Test 4: Updated Blocks in Consolidation
# =============================================================================

class TestUpdatedBlocksInConsolidation:
    """Tests for updated_blocks in consolidation response."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup file paths and content."""
        self.consolidation_path = "services/v1/autoedit/project_consolidation.py"

        with open(self.consolidation_path, "r", encoding="utf-8") as f:
            self.consolidation_content = f.read()
        self.consolidation_tree = ast.parse(self.consolidation_content)

    def test_project_consolidator_has_generate_updated_blocks(self):
        """Verify ProjectConsolidator has _generate_updated_blocks method."""
        assert has_class_method(self.consolidation_tree, "ProjectConsolidator", "_generate_updated_blocks")

    def test_consolidation_uses_copy_module(self):
        """Verify project_consolidation imports copy for deep copying blocks."""
        assert "import copy" in self.consolidation_content

    def test_generate_updated_blocks_accepts_recommendations(self):
        """Verify _generate_updated_blocks accepts recommendations parameter."""
        params = get_method_params(self.consolidation_tree, "ProjectConsolidator", "_generate_updated_blocks")
        assert "recommendations" in params

    def test_run_full_consolidation_returns_updated_blocks(self):
        """Verify run_full_consolidation includes updated_blocks in its logic."""
        # Check that updated_blocks is set in results
        assert 'results["updated_blocks"]' in self.consolidation_content
        assert '_generate_updated_blocks' in self.consolidation_content

    def test_run_full_consolidation_calculates_total_savings(self):
        """Verify consolidation calculates total_savings_sec."""
        assert 'total_savings_sec' in self.consolidation_content

    def test_updated_blocks_structure_in_docstring(self):
        """Verify _generate_updated_blocks documents the expected structure."""
        docstring = get_method_docstring(self.consolidation_tree, "ProjectConsolidator", "_generate_updated_blocks")

        assert "blocks" in docstring
        assert "changes_applied" in docstring
        assert "original_keep_count" in docstring
        assert "new_keep_count" in docstring
        assert "savings_sec" in docstring

    def test_consolidation_uses_deepcopy(self):
        """Verify consolidation uses deepcopy for block manipulation."""
        assert "deepcopy" in self.consolidation_content or "copy.deepcopy" in self.consolidation_content


# =============================================================================
# Test 5: File Existence and Integration
# =============================================================================

class TestIntegration:
    """Integration tests verifying all components work together."""

    def test_all_files_exist(self):
        """Verify all modified files exist."""
        files = [
            "services/v1/autoedit/ffmpeg_builder.py",
            "services/v1/autoedit/preview.py",
            "services/v1/autoedit/context_builder.py",
            "services/v1/autoedit/project.py",
            "services/v1/autoedit/project_consolidation.py",
            "routes/v1/autoedit/project_api.py",
            "config.py"
        ]

        for file_path in files:
            assert os.path.exists(file_path), f"File not found: {file_path}"

    def test_ffmpeg_builder_uses_subprocess_for_ffprobe(self):
        """Verify ffmpeg_builder uses subprocess to call ffprobe."""
        with open("services/v1/autoedit/ffmpeg_builder.py", "r") as f:
            content = f.read()

        assert "subprocess" in content
        assert "ffprobe" in content

    def test_project_stores_project_context(self):
        """Verify project.py stores project_context in project data."""
        with open("services/v1/autoedit/project.py", "r") as f:
            content = f.read()

        assert '"project_context"' in content

    def test_context_builder_merges_profiles(self):
        """Verify context_builder merges global profile with project context."""
        with open("services/v1/autoedit/context_builder.py", "r") as f:
            content = f.read()

        # Check for profile copying/merging pattern
        assert ".copy()" in content
        assert "creator_name" in content

    def test_ffmpeg_builder_handles_vertical_video(self):
        """Verify ffmpeg_builder handles vertical video orientation."""
        with open("services/v1/autoedit/ffmpeg_builder.py", "r") as f:
            content = f.read()

        # Check for vertical video detection logic
        assert "height > width" in content or "is_vertical" in content

    def test_ffmpeg_builder_ensures_even_dimensions(self):
        """Verify ffmpeg_builder ensures H.264 compatible even dimensions."""
        with open("services/v1/autoedit/ffmpeg_builder.py", "r") as f:
            content = f.read()

        # Check for even dimension adjustment
        assert "% 2" in content
