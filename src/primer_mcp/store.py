"""
The ticket store: reading, updating, deleting, and listing tickets.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import networkx as nx

from primer_mcp.errors import GateError
from primer_mcp.graph import (
    TERMINAL_STATUS,
    children_of,
    dependency_graph,
    derive_status,
    find_cycle,
    find_path,
    load_tickets,
    sort_key,
)
from primer_mcp.models import Adr, Epic, Spike, Story, Task, Ticket, TicketBase
from primer_mcp.project import SUBDIR_FOR_TYPE
from primer_mcp.storage import dumps_ticket, loads_ticket
from primer_mcp.tickets import _update_section

# Statuses update_ticket may set. The terminal ones are reached through the
SETTABLE_STATUS = ("todo", "in-progress", "blocked", "done")

_TYPE_ORDER = {ticket_type: i for i, ticket_type in enumerate(SUBDIR_FOR_TYPE)}


def _ordered(tickets: list[Ticket]) -> list[Ticket]:
    # Hierarchy order first (epic, adr, story, task, spike), then by ID.
    return sorted(tickets, key=lambda t: (_TYPE_ORDER[t.type], sort_key(t.id)))


def get_ticket(project_dir: Path, ticket_id: str) -> list[str]:
    """
    Return one ticket verbatim, plus the edges it does not store.
    """
    path = find_path(project_dir, ticket_id)
    lines = [f"{path}", "", path.read_text(encoding="utf-8").rstrip()]

    # "What does this ticket hold up?" is a graph lookup, not a field:
    # blocked_by is stored on the blocked ticket only (ADR-004).
    graph = dependency_graph(load_tickets(project_dir))
    blocks = sorted(graph.successors(ticket_id), key=sort_key) if ticket_id in graph else []
    if blocks:
        lines += ["", f"Blocks (derived from their blocked_by): {', '.join(blocks)}"]
    return lines


def list_tickets(
    project_dir: Path,
    ticket_type: str | None = None,
    status: str | None = None,
    parent_id: str | None = None,
) -> list[str]:
    """
    One line per ticket, filtered by type, status, and/or parent.
    """
    if ticket_type is not None and ticket_type not in SUBDIR_FOR_TYPE:
        raise GateError(
            f"Unknown ticket type {ticket_type!r}. Expected one of: {', '.join(SUBDIR_FOR_TYPE)}."
        )

    all_tickets = load_tickets(project_dir)

    if parent_id is not None:
        if parent_id not in all_tickets:
            raise GateError(f"Parent ticket {parent_id!r} does not exist.")
        pool = children_of(all_tickets, parent_id)
    else:
        pool = list(all_tickets.values())

    tickets = [
        t
        for t in pool
        if (ticket_type is None or t.type == ticket_type) and (status is None or t.status == status)
    ]
    if not tickets:
        scope = " ".join(filter(None, [ticket_type or "", status or ""])) or "any"
        return [f"No tickets match ({scope}). Call list_tickets with no filters to see all."]

    width = max(len(t.status) for t in tickets)
    return [f"{t.id:<8} {t.type:<6} {t.status:<{width}}  {t.title}" for t in _ordered(tickets)]


def _check_status(ticket: Ticket, status: str) -> str | None:
    # Hard errors for invalid values and types that have no lifecycle.
    # Soft nudges for unusual but allowed transitions.
    if status not in SETTABLE_STATUS:
        remedy = {
            "completed": f'complete_task(task_id="{ticket.id}", notes="...") records '
            "what was done, which is what makes completion mean anything.",
            "verified": f'verify_task(task_id="{ticket.id}", evidence="...") is the '
            "second half of the two-phase gate.",
        }.get(status)
        if remedy is None:
            raise GateError(
                f"Unknown status {status!r}. update_ticket sets one of: "
                f"{', '.join(SETTABLE_STATUS)}."
            )
        raise GateError(f"Cannot set status to {status!r} directly. {remedy}")

    if ticket.type == "adr":
        raise GateError(
            f"Cannot set a status on {ticket.id}: an ADR records a decision "
            "already made and has no lifecycle. Record a superseding ADR instead."
        )

    if ticket.status == TERMINAL_STATUS.get(ticket.type):
        return (
            f"Note: {ticket.id} is {ticket.status!r}, which is normally terminal. "
            f"Proceeding, but consider whether a follow-up ticket would be clearer."
        )
    return None


def _check_edges(tickets: dict[str, Ticket], ticket: Ticket, blocked_by: list[str]) -> None:
    # Validated against the whole store before anything is written, so a
    # rejected edge leaves the file untouched.
    unknown = [ref for ref in blocked_by if ref not in tickets]
    if unknown:
        raise GateError(
            f"Cannot set blocked_by on {ticket.id}: no such ticket "
            f"{', '.join(unknown)}. Call list_tickets to see what exists."
        )

    probe = dict(tickets)
    probe[ticket.id] = ticket.model_copy(update={"blocked_by": blocked_by})
    cycle = find_cycle(dependency_graph(probe))
    if cycle is not None:
        raise GateError(
            f"Cannot set blocked_by on {ticket.id}: that would create a "
            f"dependency cycle {' -> '.join([*cycle, cycle[0]])}. Nothing was "
            f"written. Remove one of those edges first."
        )


def _apply_sections(body: str, sections: dict[str, str], ticket_id: str) -> str:
    for heading, content in sections.items():
        try:
            body = _update_section(body, heading, content)
        except ValueError:
            existing = [line[3:] for line in body.splitlines() if line.startswith("## ")]
            raise GateError(
                f"Cannot update {ticket_id}: it has no '## {heading}' section. "
                f"Its sections are: {', '.join(existing)}."
            ) from None
    return body


def update_ticket(
    project_dir: Path,
    ticket_id: str,
    status: str | None = None,
    blocked_by: list[str] | None = None,
    body_sections: dict[str, str] | None = None,
    external_ref: dict[str, str] | None = None,
) -> list[str]:
    """
    Amend a ticket after creation. Every argument left out is left alone.
    Status changes on terminal tickets are allowed with a nudge.
    """
    if status is None and blocked_by is None and body_sections is None and external_ref is None:
        raise GateError(
            f"Nothing to update on {ticket_id}. Pass status, blocked_by, "
            "body_sections or external_ref."
        )

    path = find_path(project_dir, ticket_id)
    ticket, body = loads_ticket(path.read_text(encoding="utf-8"))
    tickets = load_tickets(project_dir)

    changes: dict[str, object] = {}
    reported: list[str] = []
    nudges: list[str] = []

    if status is not None:
        nudge = _check_status(ticket, status)
        if nudge:
            nudges.append(nudge)
        changes["status"] = status
        reported.append(f"status: {ticket.status} -> {status}")

    if blocked_by is not None:
        _check_edges(tickets, ticket, blocked_by)
        changes["blocked_by"] = blocked_by
        reported.append(f"blocked_by: {', '.join(blocked_by) or '(none)'}")

    if external_ref is not None:
        changes["external_ref"] = external_ref
        reported.append(f"external_ref: {external_ref or '(cleared)'}")

    if body_sections is not None:
        body = _apply_sections(body, body_sections, ticket_id)
        reported.append(f"sections: {', '.join(body_sections)}")

    changes["updated"] = datetime.now(tz=UTC).date()
    path.write_text(dumps_ticket(ticket.model_copy(update=changes), body), encoding="utf-8")
    return [
        f"Updated {ticket_id}: {ticket.title}",
        *(f"  {line}" for line in reported),
        *nudges,
    ]


def delete_ticket(project_dir: Path, ticket_id: str) -> list[str]:
    """
    Delete a ticket file. Warns if non-todo or if it has children.
    """
    path = find_path(project_dir, ticket_id)
    ticket, _ = loads_ticket(path.read_text(encoding="utf-8"))

    path.unlink()

    lines = [f"Deleted {ticket_id}: {ticket.title}"]

    if ticket.status != "todo":
        lines.append(f"Note: {ticket_id} was {ticket.status!r}.")

    all_tickets = load_tickets(project_dir)
    kids = children_of(all_tickets, ticket_id)
    if isinstance(ticket, Epic):
        kids += sorted(
            (t for t in all_tickets.values() if isinstance(t, Adr) and t.epic_id == ticket_id),
            key=lambda t: sort_key(t.id),
        )
    if kids:
        kid_ids = ", ".join(k.id for k in kids)
        lines.append(
            f"Note: {ticket_id} had children: {kid_ids}. Call delete_ticket on each to clean up."
        )

    return lines


def sweep_blocked_by(project_dir: Path) -> list[str]:
    """
    Remove blocked_by entries that point to tickets that no longer exist.
    """
    all_tickets = load_tickets(project_dir)
    existing_ids = set(all_tickets)
    cleaned: list[str] = []

    for ticket in all_tickets.values():
        dangling = [ref for ref in ticket.blocked_by if ref not in existing_ids]
        if not dangling:
            continue
        new_blocked_by = [ref for ref in ticket.blocked_by if ref in existing_ids]
        path = find_path(project_dir, ticket.id)
        _, body = loads_ticket(path.read_text(encoding="utf-8"))
        updated = ticket.model_copy(update={"blocked_by": new_blocked_by})
        path.write_text(dumps_ticket(updated, body), encoding="utf-8")
        cleaned.append(f"  {ticket.id}: removed {', '.join(dangling)}")

    if not cleaned:
        return ["No dangling references found."]
    return ["Cleaned blocked_by references:", *cleaned]


def _epic_scope(tickets: dict[str, Ticket], epic_id: str) -> dict[str, Ticket]:
    # Everything belonging to one epic: its stories, and their tasks and spikes.
    stories = {t.id for t in tickets.values() if isinstance(t, Story) and t.epic_id == epic_id}
    return {
        t.id: t
        for t in tickets.values()
        if (isinstance(t, Story) and t.epic_id == epic_id)
        or (isinstance(t, Task | Spike) and t.story_id in stories)
    }


def _is_terminal(ticket: Ticket) -> bool:
    return ticket.status == TERMINAL_STATUS[ticket.type]


def _unfinished_blockers(
    tickets: dict[str, Ticket], graph: nx.DiGraph[str], ticket_id: str
) -> list[str]:
    # Dangling references are skipped rather than treated as blockers: a
    # hand-edited ID that points nowhere should not stall the whole project.
    return sorted(
        (
            blocker
            for blocker in graph.predecessors(ticket_id)
            if blocker in tickets and not _is_terminal(tickets[blocker])
        ),
        key=sort_key,
    )


def _oldest(tickets: Sequence[TicketBase]) -> TicketBase:
    # Lowest ID = created first, so the ladder is deterministic.
    return min(tickets, key=lambda t: sort_key(t.id))


def _answer(situation: str, next_call: str) -> list[str]:
    # Every answer has the same shape: what is true, then the exact call.
    return [situation, f"Next: {next_call}"]


def _options_table(
    situation: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
) -> list[str]:
    lines = [situation, ""]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return lines


def list_actionable(project_dir: Path) -> list[str]:
    """
    Return everything that can be acted on right now, with epic context.

    Output has two sections:
    1. Epic context — goals, story coverage, and progress summary so the
       reader can judge whether more planning is needed before execution.
    2. Actionable items — a table of tickets that are ready to work on,
       after filtering out blocked, done, and dependency-gated items.

    Early gates (no store, cycles, missing epics) short-circuit with a
    single instruction since the list cannot be built yet.
    """
    try:
        tickets = load_tickets(project_dir)
    except GateError:
        return _answer(
            "No ticket store here yet — nothing is being tracked.",
            'init_project(project_name="...") creates primer/ and adds the workflow '
            "section to CLAUDE.md (and AGENTS.md if it exists).",
        )

    graph = dependency_graph(tickets)
    cycle = find_cycle(graph)
    if cycle is not None:
        return _answer(
            f"The dependency graph has a cycle: {' -> '.join([*cycle, cycle[0]])}. "
            "Those tickets each wait on the next, so none can ever start.",
            f'update_ticket(ticket_id="{cycle[0]}", blocked_by=[...]) to drop one of those edges.',
        )

    epics = [t for t in tickets.values() if isinstance(t, Epic)]
    if not epics:
        return _answer(
            "No epics yet — planning starts here.",
            "plan_epic(title=..., why=..., goals=[...]) states what the work is for "
            "before any of it happens.",
        )

    open_epics = [e for e in epics if derive_status(tickets, e.id) != "done"]
    if not open_epics:
        return _answer(
            "Every epic is done. Nothing is outstanding.",
            "plan_epic(...) if there is new work to start.",
        )

    # One epic at a time: newer epics stay invisible until this one closes.
    epic = _oldest(open_epics)
    scope = _epic_scope(tickets, epic.id)

    has_adrs = any(isinstance(t, Adr) and t.epic_id == epic.id for t in tickets.values())
    stories = [t for t in scope.values() if isinstance(t, Story)]

    if not has_adrs and not stories:
        return _answer(
            f"{epic.id} ({epic.title}) has no recorded decisions yet.",
            f'Consider record_adr(epic_id="{epic.id}", ...) to capture the reasoning '
            "before it gets lost. You can also create stories directly if the "
            "decisions are straightforward.",
        )

    if not stories:
        return _answer(
            f"{epic.id} has decisions recorded but no stories.",
            f'create_story(epic_id="{epic.id}", ...) — a deliverable with acceptance criteria.',
        )

    # --- Epic context: goals, story coverage, progress ---
    assert isinstance(epic, Epic)
    lines: list[str] = []
    lines.append(f"## {epic.id}: {epic.title}")
    lines.append("")
    lines.append("**Goals:**")
    for g in epic.goals:
        lines.append(f"  - {g}")
    lines.append("")

    done_stories = [s for s in stories if derive_status(tickets, s.id) == "done"]
    open_stories = [s for s in stories if derive_status(tickets, s.id) != "done"]
    lines.append(f"**Stories:** {len(done_stories)} done, {len(open_stories)} open")
    for s in sorted(stories, key=lambda t: sort_key(t.id)):
        mark = "x" if derive_status(tickets, s.id) == "done" else " "
        lines.append(f"  - [{mark}] {s.id} {s.title}")
    lines.append("")

    # --- Status drift detection ---
    drift: list[str] = []
    for parent in sorted(
        [p for p in scope.values() if isinstance(p, Epic | Story)],
        key=lambda p: sort_key(p.id),
    ):
        derived = derive_status(tickets, parent.id)
        stored_done = parent.status == "done"
        derived_done = derived == "done"
        if stored_done and not derived_done:
            drift.append(
                f"  - {parent.id} ({parent.title}): marked done but has unfinished children"
                f' — update_ticket(ticket_id="{parent.id}", status="todo") to fix'
            )
        elif not stored_done and derived_done:
            drift.append(
                f"  - {parent.id} ({parent.title}): all children finished but status is {parent.status}"
                f' — update_ticket(ticket_id="{parent.id}", status="done") to fix'
            )
    if drift:
        lines.append(f"**Status drift:** {len(drift)} ticket(s) out of sync")
        lines.extend(drift)
        lines.append("")

    # --- Urgent gates ---
    completed = sorted(
        (t for t in scope.values() if isinstance(t, Task) and t.status == "completed"),
        key=lambda t: sort_key(t.id),
    )
    if completed:
        lines.append(f"**Urgent:** {len(completed)} task(s) completed but not verified")
        for t in completed:
            lines.append(f"  - {t.id} ({t.title})")
        lines.append("")

    started = sorted(
        (t for t in scope.values() if isinstance(t, Task | Spike) and t.status == "in-progress"),
        key=lambda t: sort_key(t.id),
    )
    if started:
        lines.append(f"**In progress:** {len(started)} task(s)")
        for item in started:
            lines.append(f"  - {item.id} ({item.title})")
        lines.append("")

    # --- Actionable items table ---
    options: list[list[str]] = []

    childless = sorted(
        (s for s in stories if s.status == "todo" and not children_of(tickets, s.id)),
        key=lambda s: sort_key(s.id),
    )
    for s in childless:
        if _unfinished_blockers(tickets, graph, s.id):
            continue
        summary = s.acceptance_criteria[0] if s.acceptance_criteria else "needs tasks"
        options.append([s.id, "—", s.title, summary])

    for ticket_id in nx.lexicographical_topological_sort(graph, key=sort_key):
        ticket = scope.get(ticket_id)
        if (
            ticket is None
            or not isinstance(ticket, Task | Spike)
            or ticket.status != "todo"
            or _unfinished_blockers(tickets, graph, ticket_id)
        ):
            continue
        if isinstance(ticket, Spike):
            options.append(
                [
                    ticket.story_id,
                    ticket.id,
                    ticket.title,
                    f"{ticket.question} (timebox: {ticket.timebox})",
                ]
            )
        else:
            assert isinstance(ticket, Task)
            options.append(
                [
                    ticket.story_id,
                    ticket.id,
                    ticket.title,
                    ticket.testable_outcome,
                ]
            )

    if options:
        lines += _options_table(
            f"**Actionable:** {len(options)} item(s)",
            ("Story", "Item", "Title", "Summary"),
            options,
        )
    else:
        lines.append("Nothing is ready to start. What is in the way:")
        for ticket in _ordered(list(scope.values())):
            if _is_terminal(ticket):
                continue
            if ticket.status == "blocked":
                lines.append(f"  {ticket.id} is blocked — see the ticket for why.")
                continue
            blockers = _unfinished_blockers(tickets, graph, ticket.id)
            if blockers:
                lines.append(f"  {ticket.id} waits on {', '.join(blockers)}")
        if lines[-1].startswith("Nothing"):
            lines.append(
                f"  Nothing outstanding in {epic.id}, but it is not done — check its stories."
            )

    if not has_adrs:
        lines.append("")
        lines.append(f"Note: {epic.id} has no ADRs — consider record_adr to capture decisions.")

    return lines
