"""
Reading the store and editing tickets after creation.

The three tools an agent needs to work without filesystem access: read one
ticket, list what exists, and amend a ticket the creation tools already wrote.

Status is read straight from disk rather than derived — the write tools
cascade derived done-ness (ADR-002), so what is stored is already true.
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
# tools that record why — complete_task, verify_task, complete_spike — or
# derived from children, never asserted here.
SETTABLE_STATUS = ("todo", "in-progress", "blocked")

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
) -> list[str]:
    """
    One line per ticket, filtered by type and status.
    """
    if ticket_type is not None and ticket_type not in SUBDIR_FOR_TYPE:
        raise GateError(
            f"Unknown ticket type {ticket_type!r}. Expected one of: {', '.join(SUBDIR_FOR_TYPE)}."
        )

    tickets = [
        t
        for t in load_tickets(project_dir).values()
        if (ticket_type is None or t.type == ticket_type) and (status is None or t.status == status)
    ]
    if not tickets:
        scope = " ".join(filter(None, [ticket_type or "", status or ""])) or "any"
        return [f"No tickets match ({scope}). Call list_tickets with no filters to see all."]

    width = max(len(t.status) for t in tickets)
    return [f"{t.id:<8} {t.type:<6} {t.status:<{width}}  {t.title}" for t in _ordered(tickets)]


def _check_status(ticket: Ticket, status: str) -> None:
    # Two separate rules: the value must be one update_ticket owns, and the
    # ticket must not already be finished.
    if status not in SETTABLE_STATUS:
        remedy = {
            "completed": f'complete_task(task_id="{ticket.id}", notes="...") records '
            "what was done, which is what makes completion mean anything.",
            "verified": f'verify_task(task_id="{ticket.id}", evidence="...") is the '
            "second half of the two-phase gate.",
            "done": f'complete_spike(spike_id="{ticket.id}", findings="...") for a '
            "spike. For a story or epic, done is derived from its children — "
            "finish them and it follows.",
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

    if ticket.status == TERMINAL_STATUS[ticket.type]:
        raise GateError(
            f"Cannot change the status of {ticket.id}: it is {ticket.status!r}, "
            f"which is terminal. Reopening would strand its parents, whose status "
            f"is derived. Create a follow-up ticket instead."
        )


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

    Needs no cascade of its own: the terminal-status guard means it can never
    change whether a parent's children are all finished.
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

    if status is not None:
        _check_status(ticket, status)
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
    return [f"Updated {ticket_id}: {ticket.title}", *(f"  {line}" for line in reported)]


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


def _oldest[T: TicketBase](tickets: Sequence[T]) -> T:
    # Generic so the caller keeps the narrow type: list is invariant, so a
    # plain list[Ticket] parameter would reject list[Epic].
    return min(tickets, key=lambda t: sort_key(t.id))


def _answer(situation: str, next_call: str) -> list[str]:
    # Every answer has the same shape: what is true, then the exact call.
    return [situation, f"Next: {next_call}"]


def get_next_action(project_dir: Path) -> list[str]:
    """
    Answer "what should I do next?" with exactly one instruction.

    Checks run in a fixed order and the first match returns, so the answer is
    deterministic rather than a list of options:

        1. no store                 -> init_project
           dependency cycle         -> report the loop (also: the sort below
                                       cannot run on a cyclic graph)
        2. no epics                 -> plan_epic
           every epic done          -> nothing outstanding
           -- from here, only the oldest open epic is considered --
        3. no ADR                   -> record_adr
        4. a task is completed      -> verify_task      | task state before
        5. a task is in progress    -> complete_task    | creating anything
        6. no stories               -> create_story
        7. a ready task or spike    -> start_task / complete_spike
        8. a story with no tasks    -> create_task
        9. nothing ready            -> name what is in the way

    Two of those orderings were decisions rather than accidents (ADR-001):
    4 and 5 above 6, because a half-open two-phase gate is the dangling state
    the workflow exists to prevent; and 7 above 8, because a real backlog is
    mostly stories without tasks yet, so the other order proposes planning
    forever while a ready task sits idle.
    """
    try:
        tickets = load_tickets(project_dir)
    except GateError:
        return _answer(
            "No ticket store here yet — nothing is being tracked.",
            'init_project(project_name="...") creates primer/ and adds the workflow '
            "section to CLAUDE.md.",
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

    open_epics = [e for e in epics if e.status != "done"]
    if not open_epics:
        return _answer(
            "Every epic is done. Nothing is outstanding.",
            "plan_epic(...) if there is new work to start.",
        )

    # One epic at a time: newer epics stay invisible until this one closes.
    epic = _oldest(open_epics)
    scope = _epic_scope(tickets, epic.id)

    if not any(isinstance(t, Adr) and t.epic_id == epic.id for t in tickets.values()):
        return _answer(
            f"{epic.id} ({epic.title}) has no recorded decisions.",
            f'record_adr(epic_id="{epic.id}", ...) — stories are gated on at least '
            "one, because decisions come before implementation.",
        )

    # Task-state gates first: a half-open two-phase gate is the dangling state
    # the workflow exists to prevent.
    completed = [t for t in scope.values() if isinstance(t, Task) and t.status == "completed"]
    if completed:
        task = _oldest(completed)
        return _answer(
            f"{task.id} ({task.title}) is completed but not verified.",
            f'verify_task(task_id="{task.id}", evidence="...") closes the two-phase '
            "gate. Point at the commit rather than restating it.",
        )

    started = [t for t in scope.values() if isinstance(t, Task) and t.status == "in-progress"]
    if started:
        task = _oldest(started)
        return _answer(
            f"{task.id} ({task.title}) is in progress.",
            f'complete_task(task_id="{task.id}", notes="...") when the work is done.',
        )

    stories = [t for t in scope.values() if isinstance(t, Story)]
    if not stories:
        return _answer(
            f"{epic.id} has decisions recorded but no stories.",
            f'create_story(epic_id="{epic.id}", ...) — a deliverable with acceptance criteria.',
        )

    # Ready work before planning more of it.
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
            return _answer(
                f"{ticket.id} ({ticket.title}) is the next open question. "
                f"Timebox: {ticket.timebox}.",
                f'complete_spike(spike_id="{ticket.id}", findings="...") once you can answer it.',
            )
        return _answer(
            f"{ticket.id} ({ticket.title}) is ready.",
            f'start_task(task_id="{ticket.id}") when you begin.',
        )

    childless = [s for s in stories if not children_of(tickets, s.id)]
    if childless:
        story = _oldest(childless)
        return _answer(
            f"{story.id} ({story.title}) has no tasks yet.",
            f'create_task(story_id="{story.id}", ...) — small enough for one session, '
            "with a testable outcome.",
        )

    # Nothing is ready, so say what is in the way rather than going quiet.
    lines = ["Nothing is ready to start. What is in the way:"]
    for ticket in _ordered(list(scope.values())):
        if _is_terminal(ticket):
            continue
        if ticket.status == "blocked":
            lines.append(f"  {ticket.id} is blocked — see the ticket for why.")
            continue
        blockers = _unfinished_blockers(tickets, graph, ticket.id)
        if blockers:
            lines.append(f"  {ticket.id} waits on {', '.join(blockers)}")
    if len(lines) == 1:
        lines.append(f"  Nothing outstanding in {epic.id}, but it is not done — check its stories.")
    return lines
