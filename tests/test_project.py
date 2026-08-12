"""
init_project tests: layout, config, CLAUDE.md handling, idempotency.
"""

from pathlib import Path

import yaml

from primer_mcp.models import SCHEMA_VERSION
from primer_mcp.project import (
    SNIPPET_HEADING,
    SUBDIRS,
    init_project,
    require_store,
)


def tree_snapshot(root: Path) -> dict[str, bytes]:
    """
    Relative path -> content for every file under root.
    """
    return {
        str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()
    }


class TestLayout:
    def test_creates_all_subdirs(self, tmp_path: Path) -> None:
        init_project(tmp_path, "demo")
        for subdir in SUBDIRS:
            assert (tmp_path / "primer" / subdir).is_dir()

    def test_reports_next_step(self, tmp_path: Path) -> None:
        lines = init_project(tmp_path, "demo")
        assert "plan_epic" in lines[-1]


class TestConfig:
    def test_config_without_jira_key(self, tmp_path: Path) -> None:
        init_project(tmp_path, "demo")
        config = yaml.safe_load((tmp_path / "primer" / "config.yaml").read_text())
        assert config == {"project_name": "demo", "schema_version": SCHEMA_VERSION}

    def test_config_with_jira_key(self, tmp_path: Path) -> None:
        init_project(tmp_path, "demo", jira_project_key="PROJ")
        config = yaml.safe_load((tmp_path / "primer" / "config.yaml").read_text())
        assert config == {
            "project_name": "demo",
            "schema_version": SCHEMA_VERSION,
            "jira": {"project_key": "PROJ"},
        }

    def test_existing_config_never_overwritten(self, tmp_path: Path) -> None:
        init_project(tmp_path, "demo")
        config_path = tmp_path / "primer" / "config.yaml"
        config_path.write_text("project_name: renamed-by-user\n")
        init_project(tmp_path, "demo", jira_project_key="NEW")
        assert config_path.read_text() == "project_name: renamed-by-user\n"


class TestClaudeMd:
    def test_created_when_missing(self, tmp_path: Path) -> None:
        init_project(tmp_path, "demo")
        content = (tmp_path / "CLAUDE.md").read_text()
        assert content.startswith(SNIPPET_HEADING)
        assert "list_actionable" in content

    def test_appended_preserving_existing_content(self, tmp_path: Path) -> None:
        existing = "# My project\n\nMy own rules.\n"
        (tmp_path / "CLAUDE.md").write_text(existing)
        init_project(tmp_path, "demo")
        content = (tmp_path / "CLAUDE.md").read_text()
        assert content.startswith(existing)  # verbatim prefix
        assert SNIPPET_HEADING in content

    def test_untouched_when_marker_present(self, tmp_path: Path) -> None:
        original = f"# Mine\n\n{SNIPPET_HEADING}\n\nCustomised by the user.\n"
        (tmp_path / "CLAUDE.md").write_text(original)
        init_project(tmp_path, "demo")
        assert (tmp_path / "CLAUDE.md").read_text() == original

    def test_append_handles_no_trailing_newline(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text("# Mine")
        init_project(tmp_path, "demo")
        content = (tmp_path / "CLAUDE.md").read_text()
        assert f"# Mine\n\n{SNIPPET_HEADING}" in content


class TestAgentsMd:
    def test_not_created_when_missing(self, tmp_path: Path) -> None:
        init_project(tmp_path, "demo")
        assert not (tmp_path / "AGENTS.md").exists()

    def test_appended_when_exists(self, tmp_path: Path) -> None:
        existing = "# Codex rules\n\nBe concise.\n"
        (tmp_path / "AGENTS.md").write_text(existing)
        init_project(tmp_path, "demo")
        content = (tmp_path / "AGENTS.md").read_text()
        assert content.startswith(existing)
        assert SNIPPET_HEADING in content

    def test_untouched_when_marker_present(self, tmp_path: Path) -> None:
        original = f"# Codex\n\n{SNIPPET_HEADING}\n\nCustomised.\n"
        (tmp_path / "AGENTS.md").write_text(original)
        init_project(tmp_path, "demo")
        assert (tmp_path / "AGENTS.md").read_text() == original


class TestIdempotency:
    def test_running_twice_equals_running_once(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text("# Existing project\n")
        init_project(tmp_path, "demo", jira_project_key="PROJ")
        first = tree_snapshot(tmp_path)
        init_project(tmp_path, "demo", jira_project_key="PROJ")
        assert tree_snapshot(tmp_path) == first


class TestSchemaVersion:
    def test_new_store_is_stamped(self, tmp_path: Path) -> None:
        # Recorded, never enforced — nothing gates on it. It exists only
        # because a stamp cannot be added retroactively.
        init_project(tmp_path, "demo")
        config = yaml.safe_load((tmp_path / "primer" / "config.yaml").read_text())
        assert config["schema_version"] == SCHEMA_VERSION

    def test_store_from_another_version_still_opens(self, tmp_path: Path) -> None:
        init_project(tmp_path, "demo")
        config = tmp_path / "primer" / "config.yaml"
        config.write_text(f"project_name: demo\nschema_version: {SCHEMA_VERSION + 100}\n")
        assert require_store(tmp_path).is_dir()
