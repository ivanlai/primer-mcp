"""MCP layer: registers the primer-mcp tools on an MCPServer.

Thin by design — business logic lives in project.py and tickets.py.
Tool descriptions and gate errors are written as agent steering: every
failure message states what failed, why, and the exact next call.
"""

from __future__ import annotations

from pathlib import Path

from mcp.server.mcpserver import MCPServer

from primer_mcp.project import init_project as _init_project
from primer_mcp.tickets import GateError
from primer_mcp.tickets import plan_epic as _plan_epic
from primer_mcp.tickets import record_adr as _record_adr

INSTRUCTIONS = """\
primer-mcp enforces a planning-first workflow. The hierarchy is
Epic -> ADR -> Story -> Task, gated in that order: an epic needs at least
one recorded ADR before stories can be created, and tasks need a parent
story. Start a new project with init_project, then plan_epic, then
record_adr. Gate violations return instructions for the correct next call.
"""


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
        return "\n".join(_init_project(project_dir, project_name, jira_project_key))

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
        try:
            return "\n".join(
                _plan_epic(project_dir, title, why, goals, constraints, non_goals, success_criteria)
            )
        except GateError as err:
            return str(err)

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
        try:
            return "\n".join(
                _record_adr(project_dir, epic_id, title, context, decision, alternatives, consequences)
            )
        except GateError as err:
            return str(err)

    return server
