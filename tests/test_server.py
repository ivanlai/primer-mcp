"""The MCP layer: every tool registered, and gate errors surfaced as responses."""

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
