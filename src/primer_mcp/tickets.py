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
from primer_mcp.project import PRIMER_DIR, SUBDIR_FOR_TYPE, init_project, require_store
from primer_mcp.storage import dumps_ticket, loads_ticket
from primer_mcp.templates import adr_body, epic_body, spike_body, story_body, task_body


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
    match = re.search(rf"^{re.escape(marker)}$", body, re.MULTILINE)
    if not match:
        raise ValueError(f"Section not found: {marker}")
    start = match.end()
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
    init_lines: list[str] = []
    if not (project_dir / PRIMER_DIR).is_dir():
        init_lines = init_project(project_dir, project_dir.name)

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
    body = epic_body(
        why=why,
        goals=goals,
        constraints=constraints or [],
        non_goals=non_goals or [],
        success_criteria=success_criteria or [],
    )
    path = primer / "epics" / f"{epic_id}.md"
    path.write_text(dumps_ticket(epic, body), encoding="utf-8")
    return [
        *init_lines,
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
        hint = (
            f"Existing epics: {', '.join(existing)}."
            if existing
            else ("No epics exist yet — create one with plan_epic first.")
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
    body = adr_body(
        epic_id=epic_id,
        context=context,
        decision=decision,
        alternatives=alternatives,
        consequences=consequences,
    )
    path = primer / "adrs" / f"{adr_id}.md"
    path.write_text(dumps_ticket(adr, body), encoding="utf-8")
    return [
        f"Recorded {adr_id}: {title} (decision for {epic_id})",
        f"Decision captured. Record further ADRs or create stories under {epic_id}.",
    ]


def _validate_adr_ids(primer: Path, epic_id: str, adr_ids: list[str]) -> list[str]:
    for adr_id in adr_ids:
        path = primer / "adrs" / f"{adr_id}.md"
        if not path.is_file():
            raise GateError(
                f"Cannot link ADR: {adr_id!r} not found. "
                f'Record it first with record_adr(epic_id="{epic_id}", ...).'
            )
        meta = frontmatter.loads(path.read_text(encoding="utf-8")).metadata
        if meta.get("epic_id") != epic_id:
            raise GateError(
                f"Cannot link ADR: {adr_id} belongs to {meta.get('epic_id')}, "
                f"not {epic_id}. ADRs must belong to the same epic as the story."
            )
    return adr_ids


def create_story(
    project_dir: Path,
    epic_id: str,
    title: str,
    what: str,
    acceptance_criteria: list[str] | None = None,
    definition_of_done: list[str] | None = None,
    adr_ids: list[str] | None = None,
) -> list[str]:
    """
    Create a Story under an epic. The epic must exist. Suggests recording an
    ADR first if the epic has none, but does not block.
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

    validated_adr_ids = _validate_adr_ids(primer, epic_id, adr_ids or [])

    has_adr = any(
        frontmatter.loads(p.read_text(encoding="utf-8")).metadata.get("epic_id") == epic_id
        for p in (primer / "adrs").glob("ADR-*.md")
    )
    nudge: str | None = None
    if not has_adr:
        nudge = (
            f"Tip: {epic_id} has no recorded decisions yet. Consider calling "
            f'record_adr(epic_id="{epic_id}", ...) to capture the reasoning '
            f"before it gets lost — even a short one helps future readers."
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
        adr_ids=validated_adr_ids,
        acceptance_criteria=ac,
        definition_of_done=dod,
    )
    body = story_body(
        epic_id=epic_id,
        what=what,
        acceptance_criteria=ac,
        definition_of_done=dod,
        adr_ids=validated_adr_ids,
    )
    path = primer / "stories" / f"{story_id}.md"
    path.write_text(dumps_ticket(story, body), encoding="utf-8")
    lines = [
        f"Created {story_id}: {title} ({path})",
        f'Next: create tasks with create_task(story_id="{story_id}", ...).',
        *recompute_parents(project_dir, story_id),
    ]
    if nudge:
        lines.append(nudge)
    return lines


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
    body = task_body(
        story_id=story_id,
        what_to_do=what_to_do,
        testable_outcome=testable_outcome,
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
    body = spike_body(
        story_id=story_id,
        question=question,
        timebox=timebox,
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
    Transition a task to in-progress. Proceeds from any status with a nudge
    when the transition is unusual.
    """
    primer = require_store(project_dir)
    task_path = _require_ticket(primer, task_id, "task", "start task")

    ticket, body = loads_ticket(task_path.read_text(encoding="utf-8"))
    assert isinstance(ticket, Task)

    nudge: str | None = None
    if ticket.status == "in-progress":
        return [
            f"Task {task_id} is already in-progress.",
            f'Call complete_task(task_id="{task_id}", notes="...") when the work is done.',
        ]
    if ticket.status == "completed":
        nudge = (
            f"Note: {task_id} was already completed — setting it back to in-progress. "
            f"The completion notes are preserved."
        )
    elif ticket.status == "verified":
        nudge = (
            f"Note: {task_id} was already verified — reopening it. "
            f"Consider whether a follow-up task would be clearer."
        )

    today = datetime.now(tz=UTC).date()
    updated = ticket.model_copy(update={"status": "in-progress", "updated": today})
    task_path.write_text(dumps_ticket(updated, body), encoding="utf-8")
    lines = [
        f"Started {task_id}: {ticket.title} (status: in-progress)",
        f'Next: call complete_task(task_id="{task_id}", notes="...") when done.',
    ]
    if nudge:
        lines.append(nudge)
    return lines


def complete_task(
    project_dir: Path,
    task_id: str,
    notes: str,
) -> list[str]:
    """
    Complete a task with notes on what was done. Proceeds from any status
    with a nudge when the transition is unusual.
    """
    primer = require_store(project_dir)
    task_path = _require_ticket(primer, task_id, "task", "complete task")

    ticket, body = loads_ticket(task_path.read_text(encoding="utf-8"))
    assert isinstance(ticket, Task)

    nudge: str | None = None
    if ticket.status == "todo":
        nudge = (
            f"Tip: {task_id} hadn't been started yet — marking it completed directly. "
            f"Next time, start_task first so the timeline is accurate."
        )
    elif ticket.status == "blocked":
        nudge = (
            f"Note: {task_id} was marked as blocked — completing it anyway. "
            f"You may want to check whether the blocker was resolved."
        )
    elif ticket.status == "completed":
        nudge = f"Note: updating completion notes on {task_id} (was already completed)."
    elif ticket.status == "verified":
        nudge = (
            f"Note: {task_id} was already verified — reopening it as completed. "
            f"Consider whether a follow-up task would be clearer."
        )

    today = datetime.now(tz=UTC).date()
    updated = ticket.model_copy(
        update={"status": "completed", "completed_notes": notes, "updated": today}
    )
    body = _update_section(body, "Completion Notes", notes)
    task_path.write_text(dumps_ticket(updated, body), encoding="utf-8")
    lines = [
        f"Completed {task_id}: {ticket.title} (status: completed)",
        f'Next: call verify_task(task_id="{task_id}", evidence="...") to finalise.',
    ]
    if nudge:
        lines.append(nudge)
    return lines


def verify_task(
    project_dir: Path,
    task_id: str,
    evidence: str,
    commit: str | None = None,
) -> list[str]:
    """
    Verify a task with evidence that the work holds. Proceeds from any
    status with a nudge when the transition is unusual.
    """
    primer = require_store(project_dir)
    task_path = _require_ticket(primer, task_id, "task", "verify task")

    ticket, body = loads_ticket(task_path.read_text(encoding="utf-8"))
    assert isinstance(ticket, Task)

    nudge: str | None = None
    if ticket.status in ("todo", "in-progress"):
        nudge = (
            f"Tip: {task_id} wasn't completed first — verifying it directly. "
            f"Next time, complete_task first so the notes capture what was done."
        )
    elif ticket.status == "blocked":
        nudge = (
            f"Note: {task_id} was marked as blocked — verifying it anyway. "
            f"You may want to check whether the blocker was resolved."
        )
    elif ticket.status == "verified":
        nudge = f"Note: updating verification evidence on {task_id} (was already verified)."

    if commit:
        evidence = f"{evidence} (commit {commit})"

    today = datetime.now(tz=UTC).date()
    updated = ticket.model_copy(
        update={"status": "verified", "verified_evidence": evidence, "updated": today}
    )
    body = _update_section(body, "Verification Evidence", evidence)
    task_path.write_text(dumps_ticket(updated, body), encoding="utf-8")
    lines = [
        f"Verified {task_id}: {ticket.title} (status: verified — done)",
        f"Task {task_id} is complete. No further action needed.",
        *recompute_parents(project_dir, task_id),
    ]
    if nudge:
        lines.append(nudge)
    return lines


def complete_spike(
    project_dir: Path,
    spike_id: str,
    findings: str,
) -> list[str]:
    """
    Complete a spike with findings. Proceeds from any status with a nudge
    when the transition is unusual.
    """
    primer = require_store(project_dir)
    spike_path = _require_ticket(primer, spike_id, "spike", "complete spike")

    ticket, body = loads_ticket(spike_path.read_text(encoding="utf-8"))
    assert isinstance(ticket, Spike)

    nudge: str | None = None
    if ticket.status == "blocked":
        nudge = (
            f"Note: {spike_id} was marked as blocked — completing it anyway. "
            f"You may want to check whether the blocker was resolved."
        )
    elif ticket.status == "done":
        nudge = f"Note: updating findings on {spike_id} (was already done)."

    today = datetime.now(tz=UTC).date()
    updated = ticket.model_copy(update={"status": "done", "findings": findings, "updated": today})
    body = _update_section(body, "Findings", findings)
    spike_path.write_text(dumps_ticket(updated, body), encoding="utf-8")
    lines = [
        f"Completed {spike_id}: {ticket.title} (status: done)",
        f"Findings recorded. Spike {spike_id} is closed.",
        *recompute_parents(project_dir, spike_id),
    ]
    if nudge:
        lines.append(nudge)
    return lines
