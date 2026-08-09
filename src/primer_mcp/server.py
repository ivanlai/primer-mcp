"""MCP layer: registers the primer-mcp tools on an MCPServer.

Thin by design — business logic lives in project.py, tickets.py and query.py.

Every docstring below is shipped to the model. MCPServer falls back to
`fn.__doc__` for a tool's description, so these are the text an agent reads
when deciding what to call: product copy, not developer notes. Rewording one
changes how agents behave, so treat them as you would any user-facing string —
and note the parameter schema is derived from the type hints, so signatures
steer too. Gate errors are the same surface after the fact: what failed, why,
and the exact next call.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from primer_mcp import project, query, tickets
from primer_mcp.errors import GateError

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
    except GateError as err:
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
            project_dir,
            title,
            why,
            goals,
            constraints,
            non_goals,
            success_criteria,
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
            project_dir,
            epic_id,
            title,
            context,
            decision,
            alternatives,
            consequences,
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
            project_dir,
            epic_id,
            title,
            what,
            acceptance_criteria,
            definition_of_done,
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

    @server.tool(name="complete_task")
    def complete_task(task_id: str, notes: str) -> str:
        """Mark a task as completed with notes on what was done. The task must
        be in-progress (call start_task first if it isn't). This is phase one
        of the two-phase completion gate — after this, call verify_task with
        evidence (test output, command run) to finalise."""

        return _gated(tickets.complete_task, project_dir, task_id, notes)

    @server.tool(name="verify_task")
    def verify_task(task_id: str, evidence: str) -> str:
        """Verify a completed task with evidence (test output, command run,
        screenshot reference). The task must already be completed via
        complete_task — this is the second phase of the two-phase gate.
        Sets the task to verified (terminal). Cannot be undone."""

        return _gated(tickets.verify_task, project_dir, task_id, evidence)

    @server.tool(name="complete_spike")
    def complete_spike(spike_id: str, findings: str) -> str:
        """Close a spike by recording its findings — the answer to the
        question it was investigating and any recommendations. The spike
        must be in todo or in-progress (not blocked or already done).
        Sets status to done (terminal)."""

        return _gated(tickets.complete_spike, project_dir, spike_id, findings)

    @server.tool(name="get_next_action")
    def get_next_action() -> str:
        """Ask what to do next. Returns exactly one instruction: the first
        unmet workflow gate, or the next ready ticket. Call this whenever you
        are unsure where to start, after finishing anything, or when picking a
        project back up — it reads the current state rather than guessing."""

        return _gated(query.get_next_action, project_dir)

    @server.tool(name="get_ticket")
    def get_ticket(ticket_id: str) -> str:
        """Read one ticket by ID, with its full body. Also reports which
        tickets it blocks — that direction is not stored on the ticket itself,
        so this is the only way to see it."""

        return _gated(query.get_ticket, project_dir, ticket_id)

    @server.tool(name="list_tickets")
    def list_tickets(ticket_type: str | None = None, status: str | None = None) -> str:
        """List tickets one per line, newest work last. Filter by type (epic,
        adr, story, task, spike) or status to narrow it. Use this to find an ID
        before calling another tool."""

        return _gated(query.list_tickets, project_dir, ticket_type, status)

    @server.tool(name="update_ticket")
    def update_ticket(
        ticket_id: str,
        status: str | None = None,
        blocked_by: list[str] | None = None,
        body_sections: dict[str, str] | None = None,
        external_ref: dict[str, str] | None = None,
    ) -> str:
        """Amend a ticket after creation; anything left out is left alone.
        status sets todo, in-progress or blocked — the finished states belong
        to complete_task, verify_task and complete_spike, which record why.
        blocked_by replaces the list of tickets this one waits on, and is
        refused if the referenced tickets do not exist or the edge would
        create a cycle. To say "A blocks B", set blocked_by on B.
        body_sections replaces whole markdown sections by heading."""

        return _gated(
            query.update_ticket,
            project_dir,
            ticket_id,
            status,
            blocked_by,
            body_sections,
            external_ref,
        )

    return server
