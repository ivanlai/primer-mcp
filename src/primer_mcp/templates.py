"""Ticket body templates — one function per ticket type."""

from __future__ import annotations


def _bullets(items: list[str], empty: str = "(none)") -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"- {empty}"


def _checklist(items: list[str], empty: str = "(none)") -> str:
    return "\n".join(f"- [ ] {item}" for item in items) if items else f"- {empty}"


def epic_body(
    why: str,
    goals: list[str],
    constraints: list[str],
    non_goals: list[str],
    success_criteria: list[str],
) -> str:
    return (
        f"## Why\n{why}\n\n"
        f"## Goals\n{_bullets(goals)}\n\n"
        f"## Constraints\n{_bullets(constraints)}\n\n"
        f"## Non-Goals\n{_bullets(non_goals)}\n\n"
        f"## Success Criteria\n{_bullets(success_criteria)}\n\n"
        f"## Child ADRs\n- (none yet)\n\n"
        f"## Child Stories\n- (none yet)"
    )


def adr_body(
    epic_id: str,
    context: str,
    decision: str,
    alternatives: list[str],
    consequences: str,
) -> str:
    return (
        f"## Parent Epic\n[[{epic_id}]]\n\n"
        f"## Context\n{context}\n\n"
        f"## Decision\n{decision}\n\n"
        f"## Alternatives Considered\n{_bullets(alternatives, empty='(none considered)')}\n\n"
        f"## Consequences\n{consequences}"
    )


def story_body(
    epic_id: str,
    what: str,
    acceptance_criteria: list[str],
    definition_of_done: list[str],
    adr_ids: list[str] | None = None,
) -> str:
    adr_links = _bullets([f"[[{aid}]]" for aid in adr_ids], empty="(none)") if adr_ids else "- (none)"
    return (
        f"## Parent Epic\n[[{epic_id}]]\n\n"
        f"## Governing ADRs\n{adr_links}\n\n"
        f"## What\n{what}\n\n"
        f"## Acceptance Criteria\n{_checklist(acceptance_criteria)}\n\n"
        f"## Definition of Done\n{_checklist(definition_of_done)}\n\n"
        f"## Dependencies\n- (none)"
    )


def task_body(
    story_id: str,
    what_to_do: str,
    testable_outcome: str,
) -> str:
    return (
        f"## Parent Story\n[[{story_id}]]\n\n"
        f"## What to do\n{what_to_do}\n\n"
        f"## Testable Outcome\n{testable_outcome}\n\n"
        f"## Dependencies\n- (none)\n\n"
        f"## Completion Notes\n\n\n"
        f"## Verification Evidence"
    )


def spike_body(
    story_id: str,
    question: str,
    timebox: str,
) -> str:
    return (
        f"## Parent Story\n[[{story_id}]]\n\n"
        f"## Question\n{question}\n\n"
        f"## Timebox\n{timebox}\n\n"
        f"## Findings"
    )
