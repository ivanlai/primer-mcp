"""Ticket body templates — one function per ticket type."""

from __future__ import annotations

from textwrap import dedent


def _bullets(items: list[str], empty: str = "(none)") -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"- {empty}"


def epic_body(
    why: str,
    goals: list[str],
    constraints: list[str],
    non_goals: list[str],
    success_criteria: list[str],
) -> str:
    return dedent(f"""\
        ## Why
        {why}

        ## Goals
        {_bullets(goals)}

        ## Constraints
        {_bullets(constraints)}

        ## Non-Goals
        {_bullets(non_goals)}

        ## Success Criteria
        {_bullets(success_criteria)}""")


def adr_body(
    epic_id: str,
    context: str,
    decision: str,
    alternatives: list[str],
    consequences: str,
) -> str:
    return dedent(f"""\
        ## Parent Epic
        [[{epic_id}]]

        ## Context
        {context}

        ## Decision
        {decision}

        ## Alternatives Considered
        {_bullets(alternatives, empty="(none considered)")}

        ## Consequences
        {consequences}""")


def story_body(
    epic_id: str,
    what: str,
    acceptance_criteria: list[str],
    definition_of_done: list[str],
    adr_ids: list[str] | None = None,
) -> str:
    adr_links = (
        _bullets([f"[[{aid}]]" for aid in adr_ids], empty="(none)") if adr_ids else "- (none)"
    )
    return dedent(f"""\
        ## Parent Epic
        [[{epic_id}]]

        ## Governing ADRs
        {adr_links}

        ## What
        {what}

        ## Acceptance Criteria
        {_bullets(acceptance_criteria)}

        ## Definition of Done
        {_bullets(definition_of_done)}

        ## Dependencies
        - (none)""")


def task_body(
    story_id: str,
    what_to_do: str,
    testable_outcome: str,
) -> str:
    return dedent(f"""\
        ## Parent Story
        [[{story_id}]]

        ## What to do
        {what_to_do}

        ## Testable Outcome
        {testable_outcome}

        ## Dependencies
        - (none)

        ## Completion Notes


        ## Verification Evidence""")


def spike_body(
    story_id: str,
    question: str,
    timebox: str,
) -> str:
    return dedent(f"""\
        ## Parent Story
        [[{story_id}]]

        ## Question
        {question}

        ## Timebox
        {timebox}

        ## Findings""")
