"""Ticket creation: business logic for the planning tools.

No MCP imports here — this layer is tested directly (tmp_path) and the
server registers thin wrappers around it. Body templates follow
docs/architecture.md exactly.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from primer_mcp.models import ID_PREFIX, Adr, Epic
from primer_mcp.project import PRIMER_DIR
from primer_mcp.storage import dumps_ticket

SUBDIR_FOR_TYPE = {
    "epic": "epics",
    "adr": "adrs",
    "story": "stories",
    "task": "tasks",
    "spike": "spikes",
}


class GateError(ValueError):
    """A workflow gate blocked the operation.

    The message is agent-steering: what failed, why, and the exact
    next call to make. Surfaced verbatim as the tool response.
    """


def _primer_dir(project_dir: Path) -> Path:
    primer = project_dir / PRIMER_DIR
    if not primer.is_dir():
        raise GateError(
            f"Project not initialised: {primer} does not exist. "
            "Run init_project first, then retry."
        )
    return primer


def next_id(primer_dir: Path, ticket_type: str) -> str:
    prefix = ID_PREFIX[ticket_type]
    subdir = primer_dir / SUBDIR_FOR_TYPE[ticket_type]
    pattern = re.compile(rf"^{prefix}-(\d+)$")
    highest = 0
    for path in subdir.glob(f"{prefix}-*.md"):
        match = pattern.match(path.stem)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}-{highest + 1:03d}"


def _bullets(items: list[str], empty: str = "(none)") -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"- {empty}"


def plan_epic(
    project_dir: Path,
    title: str,
    why: str,
    goals: list[str],
    constraints: list[str] | None = None,
    non_goals: list[str] | None = None,
    success_criteria: list[str] | None = None,
) -> list[str]:
    """Create an Epic ticket. Returns steering lines for the tool response."""
    primer = _primer_dir(project_dir)
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
    """Record an ADR under an epic. Gate: the epic must exist."""
    primer = _primer_dir(project_dir)
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
