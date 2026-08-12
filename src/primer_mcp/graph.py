"""
The dependency graph and derived status over the ticket store.

Imports only errors, models, project and storage — never tickets or query —
so tickets.py can call the cascade and query.py can import both without a
cycle.

Only dependency edges live in the graph. Hierarchy (epic -> story -> task)
is a plain lookup over the loaded tickets; nothing here needs it in a
DiGraph, and cycle detection must run on dependency edges alone: a child
story blocking its parent epic is a cycle in the combined graph but is
semantically fine (docs/architecture.md).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import networkx as nx
from pydantic import ValidationError

from primer_mcp.errors import GateError
from primer_mcp.models import ID_PREFIX, Epic, Spike, Story, Task, Ticket
from primer_mcp.project import SUBDIR_FOR_TYPE, require_store
from primer_mcp.storage import dumps_ticket, loads_ticket

# The status at which a ticket stops holding up its parent.
TERMINAL_STATUS = {"task": "verified", "spike": "done", "story": "done", "adr": "done"}


def sort_key(ticket_id: str) -> tuple[str, int]:
    """
    Order IDs by prefix then numeric value.

    Plain string sort puts TK-010 before TK-002 without zero padding, and
    TK-1000 before TK-999 even with it — next_id explicitly supports IDs
    past 999, so the numeric part has to be compared as a number.
    """
    prefix, _, number = ticket_id.partition("-")
    return prefix, int(number)


def find_path(project_dir: Path, ticket_id: str) -> Path:
    """
    Resolve a bare ticket ID to its file: TK-001 -> primer/tasks/TK-001.md.

    Callers that take an ID without a type (get_ticket, update_ticket) need
    this; the prefix is what identifies the subdirectory.
    """
    primer = require_store(project_dir)
    for ticket_type, prefix in ID_PREFIX.items():
        if ticket_id.startswith(f"{prefix}-"):
            path = primer / SUBDIR_FOR_TYPE[ticket_type] / f"{ticket_id}.md"
            if not path.is_file():
                raise GateError(
                    f"Ticket {ticket_id!r} not found. Call list_tickets to see what exists."
                )
            return path
    raise GateError(
        f"{ticket_id!r} is not a ticket ID. Expected one of the prefixes "
        f"{', '.join(f'{p}-' for p in ID_PREFIX.values())} — e.g. TK-001."
    )


def load_tickets(project_dir: Path) -> dict[str, Ticket]:
    """
    Read every ticket in the store, keyed by ID.

    Missing subdirectories are tolerated rather than treated as corruption:
    git does not track empty directories, so a fresh clone of a store with no
    spikes has no spikes/ at all. glob on a missing directory yields nothing.
    """
    primer = require_store(project_dir)
    tickets: dict[str, Ticket] = {}
    for subdir in SUBDIR_FOR_TYPE.values():
        for path in sorted((primer / subdir).glob("*.md")):
            try:
                ticket, _ = loads_ticket(path.read_text(encoding="utf-8"))
            except ValidationError as err:
                raise GateError(
                    f"Cannot read the ticket store: {path} does not match the "
                    f"schema this primer-mcp expects. If it was edited by hand, "
                    f"restore it from version control (git checkout -- {path}). "
                    f"Details: {err}"
                ) from err
            tickets[ticket.id] = ticket
    return tickets


def dependency_graph(tickets: dict[str, Ticket]) -> nx.DiGraph[str]:
    """
    Build the dependency graph: an edge blocker -> blocked for each
    `blocked_by` entry. Nodes are ticket IDs.
    """
    graph: nx.DiGraph[str] = nx.DiGraph()
    graph.add_nodes_from(tickets)
    for ticket in tickets.values():
        for blocker in ticket.blocked_by:
            graph.add_edge(blocker, ticket.id)
    return graph


def find_cycle(graph: nx.DiGraph[str]) -> list[str] | None:
    """
    Return one dependency cycle, or None. A ticket blocking itself is a
    cycle of length one and is caught here too.

    Picks the shortest cycle, ties broken by ID, so the message is stable
    across runs rather than dependent on traversal order.
    """
    cycles = list(nx.simple_cycles(graph))
    if not cycles:
        return None
    return min(cycles, key=lambda cycle: (len(cycle), [sort_key(n) for n in cycle]))


def children_of(tickets: dict[str, Ticket], parent_id: str) -> list[Ticket]:
    """
    Tickets one level below `parent_id` in the hierarchy: an epic's stories,
    or a story's tasks and spikes. ADRs are excluded — they are born `done`
    and record a decision rather than tracking work, so they never bear on
    whether their epic is finished.
    """
    result = [
        ticket
        for ticket in tickets.values()
        if (isinstance(ticket, Story) and ticket.epic_id == parent_id)
        or (isinstance(ticket, Task | Spike) and ticket.story_id == parent_id)
    ]
    return sorted(result, key=lambda t: sort_key(t.id))


def derive_status(tickets: dict[str, Ticket], parent_id: str) -> str | None:
    """
    Return "done" when every child has reached its terminal status, else None.

    Requires at least one child: "all children are finished" is vacuously
    true of a childless story, which would make a freshly created story
    instantly done. None means "not done", not "unknown".

    For epics the check is recursive: a story is considered terminal only
    when its own children are all terminal, so a reopened task under a
    stored-done story correctly makes the epic non-done.
    """
    parent = tickets.get(parent_id)
    if not isinstance(parent, Epic | Story):
        return None
    children = children_of(tickets, parent_id)
    if not children:
        return None

    def _is_terminal(child: Ticket) -> bool:
        if child.status != TERMINAL_STATUS[child.type]:
            return False
        if isinstance(child, Story) and children_of(tickets, child.id):
            return derive_status(tickets, child.id) == "done"
        return True

    if all(_is_terminal(child) for child in children):
        return "done"
    return None


def _parent_chain(tickets: dict[str, Ticket], ticket_id: str) -> list[str]:
    # Ancestors nearest-first: a task yields [its story, that story's epic].
    ticket = tickets.get(ticket_id)
    if isinstance(ticket, Task | Spike):
        story = tickets.get(ticket.story_id)
        if isinstance(story, Story):
            return [story.id, story.epic_id]
        return [ticket.story_id]
    if isinstance(ticket, Story):
        return [ticket.epic_id]
    return []


def recompute_parents(project_dir: Path, ticket_id: str) -> list[str]:
    """
    Push derived done-ness up the hierarchy after a write, and pull it back
    down when a new child undoes it. Returns a line per file changed.

    Rules, in order:
      - criteria met  -> write `done`, overwriting `blocked` (nothing is left
        to proceed with, so a blocked flag would strand the story forever)
      - criteria lost and stored is `done` -> revert to `in-progress`
      - anything else -> leave alone, so an explicit `blocked` on a story
        with unfinished children survives
    """
    primer = require_store(project_dir)
    tickets = load_tickets(project_dir)
    changed: list[str] = []
    today = datetime.now(tz=UTC).date()

    for parent_id in _parent_chain(tickets, ticket_id):
        parent = tickets.get(parent_id)
        if not isinstance(parent, Epic | Story):
            continue
        derived = derive_status(tickets, parent_id)
        if derived == "done" and parent.status != "done":
            new_status = "done"
        elif derived is None and parent.status == "done":
            new_status = "in-progress"
        else:
            continue

        path = primer / SUBDIR_FOR_TYPE[parent.type] / f"{parent.id}.md"
        _, body = loads_ticket(path.read_text(encoding="utf-8"))
        updated = parent.model_copy(update={"status": new_status, "updated": today})
        path.write_text(dumps_ticket(updated, body), encoding="utf-8")
        # Keep the in-memory store current so the epic sees its story's new
        # status when we reach it on the next pass of this loop.
        tickets[parent_id] = updated
        changed.append(f"{parent.id} is now {new_status} ({parent.type} status is derived)")

    return changed
