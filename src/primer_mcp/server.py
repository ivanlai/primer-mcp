"""
MCP layer: registers the primer-mcp tools on an MCPServer.

Thin by design — business logic lives in project.py, tickets.py and store.py.

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

from primer_mcp import export as export_mod
from primer_mcp import project, store, tickets
from primer_mcp.errors import GateError

INSTRUCTIONS = """\
primer-mcp guides a planning-first workflow. The recommended hierarchy is
Epic -> ADR -> Story -> Task: start with why the work matters, record
decisions, then break it into stories and tasks. The tools suggest this
flow but do not block you from skipping steps — use your judgement.
Tickets are plain markdown with YAML frontmatter — read and edit them
directly where the tools fall short.
"""


def _call(fn: Callable[..., list[str]], *args: Any) -> str:
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
        """
        Initialise this project for primer-mcp: creates the primer/ ticket
        store and adds the workflow section to CLAUDE.md (and AGENTS.md if
        it exists). Non-destructive and idempotent. Call this once per
        project, before any other tool.
        Optionally pass jira_project_key if tickets may later be exported to Jira.
        """

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
        """
        Create an Epic — the top-level container for a body of work. Start
        here: state why the work matters, its goals, and how you'll know
        it's done. Consider recording decisions (record_adr) before creating
        stories — it captures reasoning that gets lost once implementation
        starts.
        """

        return _call(
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
        """
        Record an Architecture Decision Record under an epic: the context
        forcing a choice, the decision, alternatives rejected (with reasons),
        and consequences accepted. Recording decisions before creating stories
        is recommended — it captures reasoning that gets lost once
        implementation starts.
        """

        return _call(
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
        adr_ids: list[str] | None = None,
    ) -> str:
        """
        Create a Story under an epic — a deliverable with acceptance criteria.
        The epic must exist — if one hasn't been created yet, call plan_epic
        first. The user will have described their goals; use that to create
        the epic, asking for clarification if needed. If no ADR has been
        recorded, the response will suggest capturing decisions first, but
        the story is still created.

        Pass adr_ids to link the story to the architectural decisions that
        govern it. Each ADR must exist and belong to the same epic.

        After creating stories, present the plan to the user and wait for
        their agreement before creating tasks or starting work.
        """

        return _call(
            tickets.create_story,
            project_dir,
            epic_id,
            title,
            what,
            acceptance_criteria,
            definition_of_done,
            adr_ids,
        )

    @server.tool(name="create_task")
    def create_task(
        story_id: str,
        title: str,
        what_to_do: str,
        testable_outcome: str,
    ) -> str:
        """
        Create a Task under a story — a concrete unit of implementation work
        with a testable outcome. The parent story must already exist.

        After breaking a story into tasks, present the task list to the
        user before starting work — don't create tasks and immediately
        begin implementing.

        For small bug fixes (1–2 tasks), prefer adding a task under the
        standing bug-fix story rather than creating a new story. Suggest
        a dedicated story only when the fix spans 3+ tasks.
        """

        return _call(
            tickets.create_task, project_dir, story_id, title, what_to_do, testable_outcome
        )

    @server.tool(name="create_spike")
    def create_spike(
        story_id: str,
        title: str,
        question: str,
        timebox: str,
    ) -> str:
        """
        Create a Spike under a story — a timeboxed investigation to answer a
        specific question before committing to an implementation approach. The
        parent story must already exist. When done, call complete_spike with
        your findings.
        """

        return _call(tickets.create_spike, project_dir, story_id, title, question, timebox)

    @server.tool(name="start_task")
    def start_task(task_id: str) -> str:
        """
        Transition a task to in-progress — call this when you begin working
        on a task. Works from any status; you'll get a note if the transition
        is unusual. After finishing, call complete_task.
        """

        return _call(tickets.start_task, project_dir, task_id)

    @server.tool(name="complete_task")
    def complete_task(task_id: str, notes: str) -> str:
        """
        Mark a task as completed with notes on what was done. The notes
        parameter is a terse one-liner for the frontmatter field; write a
        fuller summary (approach, key changes, decisions) into the
        ## Completion Notes body section of the ticket separately.
        Ideally call start_task first, but this works from any status.
        After this, call verify_task with evidence to finalise.
        """

        return _call(tickets.complete_task, project_dir, task_id, notes)

    @server.tool(name="verify_task")
    def verify_task(task_id: str, evidence: str, commit: str = "") -> str:
        """
        Verify a task with evidence that the work holds (e.g. "218 passed,
        mypy clean"). Pass the short commit hash in the commit parameter
        so it is labelled consistently. Ideally call complete_task first
        to capture notes, but this works from any status. Sets the task
        to verified.
        """

        return _call(
            tickets.verify_task,
            project_dir,
            task_id,
            evidence,
            commit or None,
        )

    @server.tool(name="complete_spike")
    def complete_spike(spike_id: str, findings: str) -> str:
        """
        Close a spike by recording its findings — the answer to the
        question it was investigating and any recommendations. Works
        from any status.
        """

        return _call(tickets.complete_spike, project_dir, spike_id, findings)

    @server.tool(name="list_actionable")
    def list_actionable() -> str:
        """
        List what can be acted on right now, with epic context.

        Returns the epic's goals, story coverage, and a table of actionable
        items. Always show the full table to the user first, then add your
        recommendation below it. The table is the primary output — the user
        needs to see all options to make their own call.

        After showing the table, recommend what to do next:

        1. Check whether the stories cover the epic's goals. If goals are
           uncovered, recommend more planning (create_story) before
           execution.
        2. Urgent items (unverified or in-progress tasks) should usually
           be finished before starting new work.
        3. For the remaining items, read the tickets that look relevant
           (get_ticket) and recommend based on impact — what unblocks the
           most work, what aligns with current momentum, why now.
        4. If several items are genuinely equal, say so and explain why.
        """

        return _call(store.list_actionable, project_dir)

    @server.tool(name="get_ticket")
    def get_ticket(ticket_id: str) -> str:
        """
        Read one ticket by ID, with its full body. Also reports which
        tickets it blocks — that direction is not stored on the ticket itself,
        so this is the only way to see it.
        """

        return _call(store.get_ticket, project_dir, ticket_id)

    @server.tool(name="list_tickets")
    def list_tickets(
        ticket_type: str | None = None,
        status: str | None = None,
        parent_id: str | None = None,
    ) -> str:
        """
        List tickets one per line, newest work last. Filter by type (epic,
        adr, story, task, spike), status, or parent_id (show only children of
        that ticket). Use this to find an ID before calling another tool.
        """

        return _call(store.list_tickets, project_dir, ticket_type, status, parent_id)

    @server.tool(name="update_ticket")
    def update_ticket(
        ticket_id: str,
        status: str | None = None,
        blocked_by: list[str] | None = None,
        body_sections: dict[str, str] | None = None,
        external_ref: dict[str, str] | None = None,
    ) -> str:
        """
        Amend a ticket after creation; anything left out is left alone.
        status sets todo, in-progress or blocked — for finished states,
        prefer complete_task, verify_task or complete_spike as they also
        record notes. blocked_by replaces the dependency list and is
        refused if a referenced ticket does not exist or the edge would
        create a cycle. To say "A blocks B", set blocked_by on B.
        body_sections replaces whole markdown sections by heading.
        """

        return _call(
            store.update_ticket,
            project_dir,
            ticket_id,
            status,
            blocked_by,
            body_sections,
            external_ref,
        )

    @server.tool(name="delete_ticket")
    def delete_ticket(ticket_id: str) -> str:
        """
        Delete a ticket. Non-todo tickets are deleted with a warning.
        Children are reported but not deleted — call delete_ticket on
        each to cascade. After all deletions, call sweep_blocked_by to
        clean up dangling references. Recoverable from git history.
        """

        return _call(store.delete_ticket, project_dir, ticket_id)

    @server.tool(name="sweep_blocked_by")
    def sweep_blocked_by() -> str:
        """
        Remove blocked_by references that point to tickets that no
        longer exist. Call once after finishing a batch of delete_ticket
        calls.
        """

        return _call(store.sweep_blocked_by, project_dir)

    @server.tool(name="export_graph")
    def export_graph(output_path: str | None = None) -> str:
        """
        Generate a self-contained HTML file visualising the project as an
        interactive graph. Opens in any browser with no external requests.
        Nodes are coloured by type and status; edges show both hierarchy
        (epic -> story -> task) and dependencies (blocked_by). Click a node
        to see its details. On-demand — call when you want a snapshot.
        """

        return _call(
            export_mod.export_graph,
            project_dir,
            Path(output_path) if output_path else None,
        )

    # -- MCP Prompts -------------------------------------------------------

    @server.prompt(
        name="plan_story",
        description="Scaffold a planning conversation before creating a story.",
    )
    def plan_story(epic_id: str | None = None) -> str:
        parts = [
            (
                "You are about to plan a new story. Work through these points"
                " before calling create_story:\n"
            ),
        ]
        if epic_id:
            parts.append(
                f"Start by reading the parent epic for context:"
                f" get_ticket(ticket_id=\"{epic_id}\").\n"
            )
        parts.append(
            "## Placement check\n\n"
            "Before creating a new story, gauge the scope of the work:\n"
            "- **Small fix (1–2 tasks):** look for an existing bug-fix"
            " story under the epic (title contains 'bug fix' or similar)."
            " If one exists, add a task there instead of creating a new"
            " story. Suggest this to the user.\n"
            "- **Larger effort (3+ tasks):** create a dedicated story.\n\n"
            "If unsure, ask the user whether it fits as a task under the"
            " bug-fix story or deserves its own.\n\n"
            "## Story planning\n\n"
            "1. **Title** — one line summarising the deliverable.\n"
            "2. **What** — what will be built or changed, at overview level.\n"
            "3. **Acceptance criteria** — testable conditions that prove the"
            " story is done. Each criterion should be independently"
            " verifiable.\n"
            "4. **Definition of done** — checklist of quality gates (tests,"
            " docs, lint, etc.).\n"
            "5. **Dependencies** — other tickets this story is blocked_by,"
            " if any.\n"
            "\nOnce the plan is clear, call create_story with the agreed"
            " fields."
        )
        return "\n".join(parts)

    @server.prompt(
        name="export_jira",
        description="Scaffold exporting primer-mcp tickets to Jira.",
    )
    def export_jira(epic_id: str | None = None) -> str:
        scope = (
            f'Start by listing tickets under epic {epic_id}:'
            f' list_tickets() and filter to that epic.'
            if epic_id
            else "Start by listing all tickets: list_tickets()."
        )
        project_name = project_dir.name
        return (
            "Export primer-mcp tickets to Jira using the client's Jira MCP"
            " server.\n\n"
            "## Jira project key\n\n"
            "Before creating issues, confirm the Jira project key with"
            " the user. Suggest a key based on the project directory"
            f" name (`{project_name}`) — for example,"
            f" `{project_name[:5].upper().replace('-', '')}`. Ask the"
            " user to confirm or choose a different key.\n\n"
            f"{scope}\n\n"
            "## Field mapping\n\n"
            "| primer-mcp | Jira |\n"
            "|------------|------|\n"
            "| Epic | Epic |\n"
            "| Story | Story |\n"
            "| Task | Task (or Sub-task of the story) |\n"
            "| Spike | Spike (or Task labelled `spike`) |\n"
            "| ADR | Confluence page or issue labelled `adr`,"
            " linked to the Epic |\n"
            "| `title` | Summary |\n"
            "| markdown body | Description |\n"
            "| `acceptance_criteria` | Description checklist"
            " (or AC custom field) |\n"
            "| `blocked_by` | Issue links"
            ' "blocks" / "is blocked by" |\n'
            "| `status` | todo → To Do, in-progress → In Progress,"
            " completed/verified/done → Done, blocked → flagged |\n\n"
            "Jira workflows vary per instance — map each status to the"
            " nearest available column rather than assuming these exact"
            " names.\n\n"
            "## Export order\n\n"
            "Create in hierarchy order so parents exist before children:"
            " epics, then ADRs, then stories, then tasks and spikes.\n\n"
            "## Idempotent re-export\n\n"
            "Before creating a Jira issue, check the ticket's"
            " `external_ref.jira` field. If it already contains a Jira"
            " key, update that existing issue instead of creating a"
            " duplicate.\n\n"
            "After creating a new Jira issue, record its key back on"
            " the primer-mcp ticket:\n"
            '  update_ticket(ticket_id="XX-001",'
            ' external_ref={"jira": "PROJ-123"})\n\n'
            "This makes future re-exports update rather than duplicate."
        )

    @server.prompt(
        name="import_jira",
        description="Scaffold importing a Jira epic into primer-mcp.",
    )
    def import_jira(jira_epic_key: str | None = None) -> str:
        scope = (
            f"Start by reading the Jira epic {jira_epic_key} and its"
            " children."
            if jira_epic_key
            else "Identify the Jira epic to import and read it with its"
            " children."
        )
        return (
            "Import a Jira epic and its hierarchy into primer-mcp using"
            " the client's Jira MCP server.\n\n"
            f"{scope}\n\n"
            "## Type mapping\n\n"
            "| Jira | primer-mcp |\n"
            "|------|------------|\n"
            "| Epic | Epic (plan_epic) |\n"
            "| Issue labelled `adr` / Confluence page | ADR"
            " (record_adr) |\n"
            "| Story | Story (create_story) |\n"
            "| Task / Sub-task | Task (create_task) |\n"
            "| Spike / Task labelled `spike` | Spike"
            " (create_spike) |\n\n"
            "## Creation order (gate order)\n\n"
            "primer-mcp enforces a strict hierarchy. Create in this"
            " order:\n\n"
            "1. **Epic** — call plan_epic with the Jira epic's fields.\n"
            "2. **ADR** — call record_adr under the epic. If the Jira"
            " epic has no ADR equivalent, create a placeholder noting"
            " the import.\n"
            "3. **Stories** — call create_story for each Jira story.\n"
            "4. **Tasks and spikes** — call create_task or create_spike"
            " under the appropriate story.\n\n"
            "## Idempotent re-import\n\n"
            "Before creating a ticket, list existing tickets and check"
            " their `external_ref.jira` field. If a primer-mcp ticket"
            " already has the Jira key you are about to import, skip"
            " it or update it instead of creating a duplicate.\n\n"
            "## Record Jira keys\n\n"
            "After creating each primer-mcp ticket, record the"
            " original Jira key in external_ref:\n"
            '  update_ticket(ticket_id="XX-001",'
            ' external_ref={"jira": "PROJ-123"})\n\n'
            "This links the two systems so future imports and exports"
            " detect existing tickets rather than duplicating."
        )

    return server
