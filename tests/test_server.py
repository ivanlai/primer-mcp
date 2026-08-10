"""
The MCP layer: every tool registered, and gate errors surfaced as responses.
"""

from pathlib import Path

from primer_mcp.project import init_project
from primer_mcp.server import create_server

EXPECTED_TOOLS = {
    "init_project",
    "plan_epic",
    "record_adr",
    "create_story",
    "create_task",
    "create_spike",
    "start_task",
    "complete_task",
    "verify_task",
    "complete_spike",
    "get_next_action",
    "get_ticket",
    "list_tickets",
    "update_ticket",
    "export_graph",
}


def tool_names(project_dir: Path) -> set[str]:
    server = create_server(project_dir)
    return {tool.name for tool in server._tool_manager.list_tools()}


class TestRegistration:
    def test_every_tool_is_registered(self, tmp_path: Path) -> None:
        assert tool_names(tmp_path) == EXPECTED_TOOLS

    def test_descriptions_are_present(self, tmp_path: Path) -> None:
        # Tool descriptions are the steering surface an agent reads when
        # choosing what to call, so an undescribed tool is a broken one.
        server = create_server(tmp_path)
        for tool in server._tool_manager.list_tools():
            assert tool.description, f"{tool.name} has no description"


class TestGateErrorsBecomeResponses:
    def test_gate_error_is_returned_not_raised(self, tmp_path: Path) -> None:
        # An exception crossing the MCP boundary is a protocol error the agent
        # cannot act on; the steering text has to come back as the response.
        init_project(tmp_path, "demo")
        server = create_server(tmp_path)
        record_adr = server._tool_manager._tools["record_adr"].fn
        answer = record_adr(
            epic_id="EP-404",
            title="t",
            context="c",
            decision="d",
            alternatives=[],
            consequences="q",
        )
        assert "EP-404" in answer and "plan_epic" in answer

    def test_uninitialised_project_steers_to_init(self, tmp_path: Path) -> None:
        server = create_server(tmp_path)
        answer = server._tool_manager._tools["get_next_action"].fn()
        assert "init_project" in answer


EXPECTED_PROMPTS = {"plan_story", "export_jira", "import_jira"}


class TestPromptRegistration:
    def test_every_prompt_is_registered(self, tmp_path: Path) -> None:
        server = create_server(tmp_path)
        names = {p.name for p in server._prompt_manager.list_prompts()}
        assert names == EXPECTED_PROMPTS

    def test_prompt_descriptions_are_present(self, tmp_path: Path) -> None:
        server = create_server(tmp_path)
        for prompt in server._prompt_manager.list_prompts():
            assert prompt.description, f"{prompt.name} has no description"

    def test_plan_story_has_optional_epic_id(self, tmp_path: Path) -> None:
        server = create_server(tmp_path)
        prompt = server._prompt_manager.get_prompt("plan_story")
        assert prompt is not None
        args = {a.name: a for a in (prompt.arguments or [])}
        assert "epic_id" in args
        assert args["epic_id"].required is False

    def test_export_jira_has_optional_epic_id(self, tmp_path: Path) -> None:
        server = create_server(tmp_path)
        prompt = server._prompt_manager.get_prompt("export_jira")
        assert prompt is not None
        args = {a.name: a for a in (prompt.arguments or [])}
        assert "epic_id" in args
        assert args["epic_id"].required is False

    def test_import_jira_has_optional_jira_epic_key(self, tmp_path: Path) -> None:
        server = create_server(tmp_path)
        prompt = server._prompt_manager.get_prompt("import_jira")
        assert prompt is not None
        args = {a.name: a for a in (prompt.arguments or [])}
        assert "jira_epic_key" in args
        assert args["jira_epic_key"].required is False


class TestPromptContent:
    def _render(self, tmp_path: Path, name: str, **kwargs: str) -> str:
        server = create_server(tmp_path)
        return server._prompt_manager._prompts[name].fn(**kwargs)

    def test_plan_story_mentions_create_story(self, tmp_path: Path) -> None:
        text = self._render(tmp_path, "plan_story")
        assert "create_story" in text
        assert "acceptance_criteria" in text.lower() or "Acceptance criteria" in text

    def test_plan_story_with_epic_id(self, tmp_path: Path) -> None:
        text = self._render(tmp_path, "plan_story", epic_id="EP-001")
        assert "EP-001" in text
        assert "get_ticket" in text

    def test_export_jira_mentions_external_ref(self, tmp_path: Path) -> None:
        text = self._render(tmp_path, "export_jira")
        assert "external_ref" in text

    def test_export_jira_suggests_project_key(self, tmp_path: Path) -> None:
        text = self._render(tmp_path, "export_jira")
        assert tmp_path.name in text

    def test_export_jira_includes_field_mapping(self, tmp_path: Path) -> None:
        text = self._render(tmp_path, "export_jira")
        assert "acceptance_criteria" in text
        assert "blocked_by" in text
        assert "To Do" in text

    def test_export_jira_update_not_duplicate(self, tmp_path: Path) -> None:
        text = self._render(tmp_path, "export_jira")
        assert "update" in text.lower()
        assert "duplicate" in text.lower()

    def test_import_jira_gate_order(self, tmp_path: Path) -> None:
        text = self._render(tmp_path, "import_jira")
        assert text.index("plan_epic") < text.index("record_adr")
        assert text.index("record_adr") < text.index("create_story")
        assert text.index("create_story") < text.index("create_task")

    def test_import_jira_mentions_external_ref(self, tmp_path: Path) -> None:
        text = self._render(tmp_path, "import_jira")
        assert "external_ref" in text

    def test_import_jira_idempotent_reimport(self, tmp_path: Path) -> None:
        text = self._render(tmp_path, "import_jira")
        assert "duplicate" in text.lower()
        assert "existing" in text.lower()
