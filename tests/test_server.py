"""
MCP integration: tools and prompts registered and callable via the in-memory client.
"""

from pathlib import Path

import anyio
from mcp.client import Client

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

EXPECTED_PROMPTS = {"plan_story", "export_jira", "import_jira"}


def _text(result: object) -> str:
    return result.content[0].text  # type: ignore[union-attr]


class TestRegistration:
    def test_every_tool_is_registered(self, tmp_path: Path) -> None:
        async def _test() -> None:
            async with Client(create_server(tmp_path)) as client:
                result = await client.list_tools()
                assert {t.name for t in result.tools} == EXPECTED_TOOLS

        anyio.run(_test)

    def test_descriptions_are_present(self, tmp_path: Path) -> None:
        async def _test() -> None:
            async with Client(create_server(tmp_path)) as client:
                result = await client.list_tools()
                for tool in result.tools:
                    assert tool.description, f"{tool.name} has no description"

        anyio.run(_test)


class TestGateErrorsBecomeResponses:
    def test_gate_error_is_returned_not_raised(self, tmp_path: Path) -> None:
        init_project(tmp_path, "demo")

        async def _test() -> None:
            async with Client(create_server(tmp_path)) as client:
                result = await client.call_tool(
                    "record_adr",
                    {
                        "epic_id": "EP-404",
                        "title": "t",
                        "context": "c",
                        "decision": "d",
                        "alternatives": [],
                        "consequences": "q",
                    },
                )
                text = _text(result)
                assert "EP-404" in text
                assert "plan_epic" in text

        anyio.run(_test)

    def test_uninitialised_project_steers_to_init(self, tmp_path: Path) -> None:
        async def _test() -> None:
            async with Client(create_server(tmp_path)) as client:
                result = await client.call_tool("get_next_action", {})
                assert "init_project" in _text(result)

        anyio.run(_test)


class TestPromptRegistration:
    def test_every_prompt_is_registered(self, tmp_path: Path) -> None:
        async def _test() -> None:
            async with Client(create_server(tmp_path)) as client:
                result = await client.list_prompts()
                assert {p.name for p in result.prompts} == EXPECTED_PROMPTS

        anyio.run(_test)

    def test_prompt_descriptions_are_present(self, tmp_path: Path) -> None:
        async def _test() -> None:
            async with Client(create_server(tmp_path)) as client:
                result = await client.list_prompts()
                for prompt in result.prompts:
                    assert prompt.description, f"{prompt.name} has no description"

        anyio.run(_test)

    def test_plan_story_has_optional_epic_id(self, tmp_path: Path) -> None:
        async def _test() -> None:
            async with Client(create_server(tmp_path)) as client:
                result = await client.list_prompts()
                prompt = next(p for p in result.prompts if p.name == "plan_story")
                args = {a.name: a for a in (prompt.arguments or [])}
                assert "epic_id" in args
                assert args["epic_id"].required is False

        anyio.run(_test)

    def test_export_jira_has_optional_epic_id(self, tmp_path: Path) -> None:
        async def _test() -> None:
            async with Client(create_server(tmp_path)) as client:
                result = await client.list_prompts()
                prompt = next(p for p in result.prompts if p.name == "export_jira")
                args = {a.name: a for a in (prompt.arguments or [])}
                assert "epic_id" in args
                assert args["epic_id"].required is False

        anyio.run(_test)

    def test_import_jira_has_optional_jira_epic_key(self, tmp_path: Path) -> None:
        async def _test() -> None:
            async with Client(create_server(tmp_path)) as client:
                result = await client.list_prompts()
                prompt = next(p for p in result.prompts if p.name == "import_jira")
                args = {a.name: a for a in (prompt.arguments or [])}
                assert "jira_epic_key" in args
                assert args["jira_epic_key"].required is False

        anyio.run(_test)


class TestPromptContent:
    def _render(self, tmp_path: Path, name: str, **kwargs: str) -> str:
        result: object = None

        async def _test() -> None:
            nonlocal result
            async with Client(create_server(tmp_path)) as client:
                result = await client.get_prompt(name, kwargs or None)

        anyio.run(_test)
        return result.messages[0].content.text  # type: ignore[union-attr]

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


class TestToolLifecycle:
    def test_happy_path_through_client(self, tmp_path: Path) -> None:
        async def _test() -> None:
            async with Client(create_server(tmp_path)) as client:
                r = await client.call_tool("init_project", {"project_name": "demo"})
                assert not r.is_error
                assert "primer/" in _text(r)

                r = await client.call_tool(
                    "plan_epic",
                    {"title": "E", "why": "because", "goals": ["ship"]},
                )
                assert not r.is_error
                assert "EP-001" in _text(r)

                r = await client.call_tool(
                    "record_adr",
                    {
                        "epic_id": "EP-001",
                        "title": "Choose X",
                        "context": "ctx",
                        "decision": "X",
                        "alternatives": ["Y"],
                        "consequences": "fast",
                    },
                )
                assert not r.is_error
                assert "ADR-001" in _text(r)

                r = await client.call_tool(
                    "create_story",
                    {
                        "epic_id": "EP-001",
                        "title": "S",
                        "what": "Build it",
                        "acceptance_criteria": ["works"],
                        "definition_of_done": ["merged"],
                    },
                )
                assert not r.is_error
                assert "ST-001" in _text(r)

                r = await client.call_tool(
                    "create_task",
                    {
                        "story_id": "ST-001",
                        "title": "T",
                        "what_to_do": "impl",
                        "testable_outcome": "green",
                    },
                )
                assert not r.is_error
                assert "TK-001" in _text(r)

                r = await client.call_tool("start_task", {"task_id": "TK-001"})
                assert not r.is_error
                assert "in-progress" in _text(r)

                r = await client.call_tool(
                    "complete_task", {"task_id": "TK-001", "notes": "done"}
                )
                assert not r.is_error
                assert "completed" in _text(r)

                r = await client.call_tool(
                    "verify_task", {"task_id": "TK-001", "evidence": "proof"}
                )
                assert not r.is_error
                assert "verified" in _text(r)

        anyio.run(_test)
