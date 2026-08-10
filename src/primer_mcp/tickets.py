"""
Ticket creation: business logic for the planning tools.

No MCP imports here — this layer is tested directly (tmp_path) and the
server registers thin wrappers around it. Body templates follow
docs/architecture.md exactly.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import frontmatter

from primer_mcp.errors import GateError
from primer_mcp.graph import recompute_parents
from primer_mcp.models import ID_PREFIX, Adr, Epic, Spike, Story, Task
from primer_mcp.project import SUBDIR_FOR_TYPE, require_store
from primer_mcp.storage import dumps_ticket, loads_ticket


def next_id(primer: Path, ticket_type: str) -> str:
    """
    Allocate the next sequential ID for a ticket type by scanning existing
    files, e.g. tasks/ holding TK-001.md and TK-007.md -> "TK-008".

    Max+1 (not count+1) so deleted tickets never cause ID reuse; zero-padded
    to three digits but parsed unpadded, so numbering survives past 999.
    """
    prefix = ID_PREFIX[ticket_type]
    subdir = primer / SUBDIR_FOR_TYPE[ticket_type]
    pattern = re.compile(rf"^{prefix}-(\d+)$")
    highest = 0
    for path in subdir.glob(f"{prefix}-*.md"):
        match = pattern.match(path.stem)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}-{highest + 1:03d}"


def _bullets(items: list[str], empty: str = "(none)") -> str:
    """
    Render items as a markdown bullet list for ticket bodies,
    e.g. ["a", "b"] -> "- a\\n- b". An empty list becomes a single
    placeholder bullet so template sections are never blank.
    """
    return "\n".join(f"- {item}" for item in items) if items else f"- {empty}"


def _checklist(items: list[str], empty: str = "(none)") -> str:
    # Like _bullets but with markdown checkboxes: "- [ ] item"
    return "\n".join(f"- [ ] {item}" for item in items) if items else f"- {empty}"


def _require_ticket(primer: Path, ticket_id: str, ticket_type: str, action: str) -> Path:
    # Returns the ticket path or raises GateError with existing-ticket hints.
    subdir = SUBDIR_FOR_TYPE[ticket_type]
    prefix = ID_PREFIX[ticket_type]
    path = primer / subdir / f"{ticket_id}.md"
    if not path.is_file():
        existing = sorted(p.stem for p in (primer / subdir).glob(f"{prefix}-*.md"))
        hint = (
            f"Existing {subdir}: {', '.join(existing)}."
            if existing
            else f"No {subdir} exist yet — create one with create_{ticket_type} first."
        )
        raise GateError(f"Cannot {action}: {ticket_id!r} not found. {hint}")
    return path


def _update_section(body: str, heading: str, content: str) -> str:
    marker = f"## {heading}"
    start = body.index(marker) + len(marker)
    next_heading = body.find("\n## ", start)
    if next_heading == -1:
        return body[:start] + "\n" + content
    return body[:start] + "\n" + content + body[next_heading:]


def plan_epic(
    project_dir: Path,
    title: str,
    why: str,
    goals: list[str],
    constraints: list[str] | None = None,
    non_goals: list[str] | None = None,
    success_criteria: list[str] | None = None,
) -> list[str]:
    """
    Create an Epic ticket. Returns steering lines for the tool response.
    """
    primer = require_store(project_dir)
    epic_id = next_id(primer, "epic")
    today = datetime.now(tz=UTC).date()
    epic = Epic(
        id=epic_id,
        title=title,
        created=today,
        updated=today,
        goals=goals,
        constraints=constraints or [],
        non_goals=non_goals or [],
        success_criteria=success_criteria or [],
    )
    body = (
        f"## Why\n{why}\n\n"
        f"## Goals\n{_bullets(goals)}\n\n"
        f"## Constraints\n{_bullets(constraints or [])}\n\n"
        f"## Non-Goals\n{_bullets(non_goals or [])}\n\n"
        f"## Success Criteria\n{_bullets(success_criteria or [])}\n\n"
        f"## Child ADRs\n- (none yet)\n\n"
        f"## Child Stories\n- (none yet)"
    )
    path = primer / "epics" / f"{epic_id}.md"
    path.write_text(dumps_ticket(epic, body), encoding="utf-8")
    return [
        f"Created {epic_id}: {title} ({path})",
        (
            f"Next: record at least one architectural decision with "
            f'record_adr(epic_id="{epic_id}", ...) — stories are gated on it.'
        ),
    ]


def record_adr(
    project_dir: Path,
    epic_id: str,
    title: str,
    context: str,
    decision: str,
    alternatives: list[str],
    consequences: str,
) -> list[str]:
    """
    Record an ADR under an epic. Gate: the epic must exist.
    """
    primer = require_store(project_dir)
    epic_path = primer / "epics" / f"{epic_id}.md"
    if not epic_path.is_file():
        existing = sorted(p.stem for p in (primer / "epics").glob("EP-*.md"))
        hint = f"Existing epics: {', '.join(existing)}." if existing else (
            "No epics exist yet — create one with plan_epic first."
        )
        raise GateError(
            f"Cannot record ADR: epic {epic_id!r} not found. {hint} "
            f"Then call record_adr with a valid epic_id."
        )
    adr_id = next_id(primer, "adr")
    today = datetime.now(tz=UTC).date()
    adr = Adr(
        id=adr_id,
        title=title,
        created=today,
        updated=today,
        epic_id=epic_id,
        context=context,
        decision=decision,
        alternatives=alternatives,
        consequences=consequences,
    )
    body = (
        f"## Parent Epic\n[[{epic_id}]]\n\n"
        f"## Context\n{context}\n\n"
        f"## Decision\n{decision}\n\n"
        f"## Alternatives Considered\n{_bullets(alternatives, empty='(none considered)')}\n\n"
        f"## Consequences\n{consequences}"
    )
    path = primer / "adrs" / f"{adr_id}.md"
    path.write_text(dumps_ticket(adr, body), encoding="utf-8")
    return [
        f"Recorded {adr_id}: {title} (decision for {epic_id})",
        (
            f"{epic_id} now satisfies the ADR gate — create_story is unlocked "
            "once it lands, or record further ADRs."
        ),
    ]


def create_story(
    project_dir: Path,
    epic_id: str,
    title: str,
    what: str,
    acceptance_criteria: list[str] | None = None,
    definition_of_done: list[str] | None = None,
) -> list[str]:
    """
    Create a Story under an epic. Gate: epic must exist and have at least one ADR.
    """
    primer = require_store(project_dir)

    epic_path = primer / "epics" / f"{epic_id}.md"
    if not epic_path.is_file():
        existing = sorted(p.stem for p in (primer / "epics").glob("EP-*.md"))
        hint = (
            f"Existing epics: {', '.join(existing)}."
            if existing
            else "No epics exist yet — create one with plan_epic first."
        )
        raise GateError(
            f"Cannot create story: epic {epic_id!r} not found. {hint} "
            f"Then call create_story with a valid epic_id."
        )

    has_adr = any(
        frontmatter.loads(p.read_text(encoding="utf-8")).metadata.get("epic_id") == epic_id
        for p in (primer / "adrs").glob("ADR-*.md")
    )
    if not has_adr:
        raise GateError(
            f"Cannot create story: epic {epic_id} has no ADRs. "
            f"Record at least one architectural decision first: "
            f'record_adr(epic_id="{epic_id}", ...)'
        )

    story_id = next_id(primer, "story")
    today = datetime.now(tz=UTC).date()
    ac = acceptance_criteria or []
    dod = definition_of_done or []
    story = Story(
        id=story_id,
        title=title,
        created=today,
        updated=today,
        epic_id=epic_id,
        acceptance_criteria=ac,
        definition_of_done=dod,
    )
    body = (
        f"## Parent Epic\n[[{epic_id}]]\n\n"
        f"## What\n{what}\n\n"
        f"## Acceptance Criteria\n{_checklist(ac)}\n\n"
        f"## Definition of Done\n{_checklist(dod)}\n\n"
        f"## Dependencies\n- (none)"
    )
    path = primer / "stories" / f"{story_id}.md"
    path.write_text(dumps_ticket(story, body), encoding="utf-8")
    return [
        f"Created {story_id}: {title} ({path})",
        f'Next: create tasks with create_task(story_id="{story_id}", ...).',
        *recompute_parents(project_dir, story_id),
    ]


def create_task(
    project_dir: Path,
    story_id: str,
    title: str,
    what_to_do: str,
    testable_outcome: str,
) -> list[str]:
    """
    Create a Task under a story. Gate: story must exist.
    """
    primer = require_store(project_dir)
    _require_ticket(primer, story_id, "story", "create ticket")

    task_id = next_id(primer, "task")
    today = datetime.now(tz=UTC).date()
    task = Task(
        id=task_id,
        title=title,
        created=today,
        updated=today,
        story_id=story_id,
        testable_outcome=testable_outcome,
    )
    body = (
        f"## Parent Story\n[[{story_id}]]\n\n"
        f"## What to do\n{what_to_do}\n\n"
        f"## Testable Outcome\n{testable_outcome}\n\n"
        f"## Dependencies\n- (none)\n\n"
        f"## Completion Notes\n\n\n"
        f"## Verification Evidence"
    )
    path = primer / "tasks" / f"{task_id}.md"
    path.write_text(dumps_ticket(task, body), encoding="utf-8")
    return [
        f"Created {task_id}: {title} ({path})",
        f'Next: call start_task(task_id="{task_id}") when you begin work.',
        *recompute_parents(project_dir, task_id),
    ]


def create_spike(
    project_dir: Path,
    story_id: str,
    title: str,
    question: str,
    timebox: str,
) -> list[str]:
    """
    Create a Spike under a story. Gate: story must exist.
    """
    primer = require_store(project_dir)
    _require_ticket(primer, story_id, "story", "create ticket")

    spike_id = next_id(primer, "spike")
    today = datetime.now(tz=UTC).date()
    spike = Spike(
        id=spike_id,
        title=title,
        created=today,
        updated=today,
        story_id=story_id,
        question=question,
        timebox=timebox,
    )
    body = (
        f"## Parent Story\n[[{story_id}]]\n\n"
        f"## Question\n{question}\n\n"
        f"## Timebox\n{timebox}\n\n"
        f"## Findings"
    )
    path = primer / "spikes" / f"{spike_id}.md"
    path.write_text(dumps_ticket(spike, body), encoding="utf-8")
    return [
        f"Created {spike_id}: {title} ({path})",
        (
            f"Timebox: {timebox}. When done, call "
            f'complete_spike(spike_id="{spike_id}", findings="...").'
        ),
        *recompute_parents(project_dir, spike_id),
    ]


def start_task(
    project_dir: Path,
    task_id: str,
) -> list[str]:
    """
    Transition a task to in-progress. Gate: task must exist and be in todo or blocked.
    """
    primer = require_store(project_dir)
    task_path = _require_ticket(primer, task_id, "task", "start task")

    ticket, body = loads_ticket(task_path.read_text(encoding="utf-8"))
    assert isinstance(ticket, Task)

    if ticket.status == "in-progress":
        raise GateError(
            f"Task {task_id} is already in-progress. "
            f'Call complete_task(task_id="{task_id}", notes="...") when the work is done.'
        )
    if ticket.status in ("completed", "verified"):
        raise GateError(
            f"Cannot start task: {task_id} has status {ticket.status!r} "
            f"and cannot go back to in-progress. "
            f"Create a follow-up task under the same story if more work is needed."
        )

    today = datetime.now(tz=UTC).date()
    updated = ticket.model_copy(update={"status": "in-progress", "updated": today})
    task_path.write_text(dumps_ticket(updated, body), encoding="utf-8")
    return [
        f"Started {task_id}: {ticket.title} (status: in-progress)",
        f'Next: call complete_task(task_id="{task_id}", notes="...") when done.',
    ]


def complete_task(
    project_dir: Path,
    task_id: str,
    notes: str,
) -> list[str]:
    """
    Complete a task. Gate: task must be in-progress.
    """
    primer = require_store(project_dir)
    task_path = _require_ticket(primer, task_id, "task", "complete task")

    ticket, body = loads_ticket(task_path.read_text(encoding="utf-8"))
    assert isinstance(ticket, Task)

    if ticket.status == "todo":
        raise GateError(
            f"Cannot complete task: {task_id} has not been started. "
            f'Call start_task(task_id="{task_id}") first.'
        )
    if ticket.status == "blocked":
        raise GateError(
            f"Cannot complete task: {task_id} is blocked. "
            f'Call get_ticket(ticket_id="{task_id}") to see what blocks it, '
            f"then resolve or remove the edges with update_ticket."
        )
    if ticket.status == "completed":
        raise GateError(
            f"Task {task_id} is already completed. "
            f'Next: call verify_task(task_id="{task_id}", evidence="...").'
        )
    if ticket.status == "verified":
        raise GateError(
            f"Task {task_id} is already verified (terminal state). "
            f"Create a follow-up task if more work is needed."
        )

    today = datetime.now(tz=UTC).date()
    updated = ticket.model_copy(
        update={"status": "completed", "completed_notes": notes, "updated": today}
    )
    body = _update_section(body, "Completion Notes", notes)
    task_path.write_text(dumps_ticket(updated, body), encoding="utf-8")
    return [
        f"Completed {task_id}: {ticket.title} (status: completed)",
        f'Next: call verify_task(task_id="{task_id}", evidence="...") with test output or proof.',
    ]


def verify_task(
    project_dir: Path,
    task_id: str,
    evidence: str,
) -> list[str]:
    """
    Verify a completed task. Gate: task must be completed (two-phase gate).
    """
    primer = require_store(project_dir)
    task_path = _require_ticket(primer, task_id, "task", "verify task")

    ticket, body = loads_ticket(task_path.read_text(encoding="utf-8"))
    assert isinstance(ticket, Task)

    if ticket.status in ("todo", "in-progress"):
        raise GateError(
            f"Cannot verify task: {task_id} has status {ticket.status!r}. "
            f'Call complete_task(task_id="{task_id}", notes="...") first.'
        )
    if ticket.status == "blocked":
        raise GateError(
            f"Cannot verify task: {task_id} is blocked. "
            f'Call get_ticket(ticket_id="{task_id}") to see what blocks it, '
            f"then resolve the blockers and call complete_task before verifying."
        )
    if ticket.status == "verified":
        raise GateError(
            f"Task {task_id} is already verified (terminal state). "
            f"Create a follow-up task if more work is needed."
        )

    today = datetime.now(tz=UTC).date()
    updated = ticket.model_copy(
        update={"status": "verified", "verified_evidence": evidence, "updated": today}
    )
    body = _update_section(body, "Verification Evidence", evidence)
    task_path.write_text(dumps_ticket(updated, body), encoding="utf-8")
    return [
        f"Verified {task_id}: {ticket.title} (status: verified — done)",
        f"Task {task_id} is complete. No further action needed.",
        *recompute_parents(project_dir, task_id),
    ]


def complete_spike(
    project_dir: Path,
    spike_id: str,
    findings: str,
) -> list[str]:
    """
    Complete a spike with findings. Gate: spike must be todo or in-progress.
    """
    primer = require_store(project_dir)
    spike_path = _require_ticket(primer, spike_id, "spike", "complete spike")

    ticket, body = loads_ticket(spike_path.read_text(encoding="utf-8"))
    assert isinstance(ticket, Spike)

    if ticket.status == "blocked":
        raise GateError(
            f"Cannot complete spike: {spike_id} is blocked. "
            f'Call get_ticket(ticket_id="{spike_id}") to see what blocks it, '
            f"then resolve or remove the edges with update_ticket."
        )
    if ticket.status == "done":
        raise GateError(
            f"Spike {spike_id} is already done. "
            f"Create a follow-up spike under the same story if the question has changed."
        )

    today = datetime.now(tz=UTC).date()
    updated = ticket.model_copy(
        update={"status": "done", "findings": findings, "updated": today}
    )
    body = _update_section(body, "Findings", findings)
    spike_path.write_text(dumps_ticket(updated, body), encoding="utf-8")
    return [
        f"Completed {spike_id}: {ticket.title} (status: done)",
        f"Findings recorded. Spike {spike_id} is closed.",
        *recompute_parents(project_dir, spike_id),
    ]
