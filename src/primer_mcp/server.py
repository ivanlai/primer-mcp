"""MCP layer: registers the primer-mcp tools on an MCPServer.

Thin by design — business logic lives in project.py and tickets.py.
Tool descriptions and gate errors are written as agent steering: every
failure message states what failed, why, and the exact next call.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from primer_mcp import project, tickets

INSTRUCTIONS = """\
primer-mcp enforces a planning-first workflow. The hierarchy is
Epic -> ADR -> Story -> Task, gated in that order: an epic needs at least
one recorded ADR before stories can be created, and tasks need a parent
story. Start a new project with init_project, then plan_epic, then
record_adr. Gate violations return instructions for the correct next call.
"""


def _gated(fn: Callable[..., list[str]], *args: Any) -> str:
    # Joins the list[str] response and converts GateError to a tool response.

    try:
        return "\n".join(fn(*args))
    except tickets.GateError as err:
        return str(err)


def create_server(project_dir: Path) -> MCPServer:
    server = MCPServer(
        name="primer-mcp",
        version="0.1.0",
        instructions=INSTRUCTIONS,
    )

    @server.tool(name="init_project")
    def init_project(project_name: str, jira_project_key: str | None = None) -> str:
        """Initialise this project for primer-mcp: creates the primer/ ticket
        store and adds the workflow section to CLAUDE.md (non-destructive,
        idempotent). Call this once per project, before any other tool.
        Optionally pass jira_project_key if tickets may later be exported to Jira."""
        return "\n".join(project.init_project(project_dir, project_name, jira_project_key))

    @server.tool(name="plan_epic")
    def plan_epic(
        title: str,
        why: str,
        goals: list[str],
        constraints: list[str] | None = None,
        non_goals: list[str] | None = None,
        success_criteria: list[str] | None = None,
    ) -> str:
        """Create an Epic — the top-level container for a body of work. Do this
        BEFORE writing any code: state why the work matters, its goals, and how
        you'll know it's done. Stories cannot be created until the epic also has
        at least one ADR (record_adr)."""
        return _gated(
            tickets.plan_epic,
            project_dir, title, why, goals, constraints, non_goals, success_criteria,
        )

    @server.tool(name="record_adr")
    def record_adr(
        epic_id: str,
        title: str,
        context: str,
        decision: str,
        alternatives: list[str],
        consequences: str,
    ) -> str:
        """Record an Architecture Decision Record under an epic: the context
        forcing a choice, the decision, alternatives rejected (with reasons),
        and consequences accepted. At least one ADR is required per epic before
        create_story will work — decisions come before implementation."""
        return _gated(
            tickets.record_adr,
            project_dir, epic_id, title, context, decision, alternatives, consequences,
        )

    @server.tool(name="create_story")
    def create_story(
        epic_id: str,
        title: str,
        what: str,
        acceptance_criteria: list[str] | None = None,
        definition_of_done: list[str] | None = None,
    ) -> str:
        """Create a Story under an epic — a deliverable with acceptance criteria.
        Requires the epic to have at least one recorded ADR (architectural
        decisions come before implementation). If gated, the error tells you
        what to call instead."""
        return _gated(
            tickets.create_story,
            project_dir, epic_id, title, what, acceptance_criteria, definition_of_done,
        )

    @server.tool(name="create_task")
    def create_task(
        story_id: str,
        title: str,
        what_to_do: str,
        testable_outcome: str,
    ) -> str:
        """Create a Task under a story — a concrete unit of implementation work
        with a testable outcome. The parent story must already exist. After
        creation, call start_task to begin work."""
        return _gated(
            tickets.create_task, project_dir, story_id, title, what_to_do, testable_outcome
        )

    @server.tool(name="create_spike")
    def create_spike(
        story_id: str,
        title: str,
        question: str,
        timebox: str,
    ) -> str:
        """Create a Spike under a story — a timeboxed investigation to answer a
        specific question before committing to an implementation approach. The
        parent story must already exist. When done, call complete_spike with
        your findings."""
        return _gated(tickets.create_spike, project_dir, story_id, title, question, timebox)

    @server.tool(name="start_task")
    def start_task(task_id: str) -> str:
        """Transition a task from todo (or blocked) to in-progress — call this
        when you begin working on a task. The task must exist and not already
        be completed or verified. After finishing, call complete_task."""
        return _gated(tickets.start_task, project_dir, task_id)

    return server
