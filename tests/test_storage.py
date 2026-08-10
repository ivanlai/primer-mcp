"""
Frontmatter serialisation round-trip tests.
"""

from datetime import date

import pytest
from pydantic import ValidationError

from primer_mcp.models import Adr, Epic, Spike, Story, Task, Ticket
from primer_mcp.storage import dumps_ticket, loads_ticket

DAY = date(2026, 8, 8)

TICKETS: list[Ticket] = [
    Epic(id="EP-001", title="Build primer-mcp", created=DAY, updated=DAY, goals=["ship"]),
    Adr(
        id="ADR-001",
        title="Markdown as data store",
        created=DAY,
        updated=DAY,
        epic_id="EP-001",
        context="Need a store.",
        decision="Markdown files.",
        alternatives=["SQLite"],
        consequences="Git-native.",
    ),
    Story(
        id="ST-002",
        title="Schema and models",
        created=DAY,
        updated=DAY,
        epic_id="EP-001",
        acceptance_criteria=["models validate"],
        blocked_by=["ST-001"],
    ),
    Task(
        id="TK-001",
        title="Write models",
        created=DAY,
        updated=DAY,
        story_id="ST-002",
        testable_outcome="pytest passes",
        status="completed",
        completed_notes="Done in models.py",
    ),
    Spike(
        id="SP-001",
        title="vis.js size check",
        created=DAY,
        updated=DAY,
        story_id="ST-002",
        question="Small enough?",
        timebox="2 hours",
        external_ref={"jira": "PROJ-42"},
    ),
]

BODY = "## What to do\nImplement the thing.\n\n## Testable Outcome\nTests pass."


@pytest.mark.parametrize("ticket", TICKETS, ids=lambda t: t.id)
def test_round_trip_preserves_ticket_and_body(ticket: Ticket) -> None:
    loaded, body = loads_ticket(dumps_ticket(ticket, BODY))
    assert loaded == ticket
    assert body == BODY


def test_output_is_yaml_frontmatter_with_stable_order(ticket: Ticket = TICKETS[0]) -> None:
    text = dumps_ticket(ticket, BODY)
    assert text.startswith("---\n")
    loaded, body = loads_ticket(text)
    assert dumps_ticket(loaded, body) == text  # dump → load → dump is byte-identical


def test_dates_written_as_plain_iso_dates() -> None:
    text = dumps_ticket(TICKETS[0], BODY)
    assert "created: 2026-08-08" in text  # unquoted — YAML date, not a string


def test_hand_edited_file_parses() -> None:
    text = (
        "---\n"
        "id: TK-002\n"
        "type: task\n"
        "title: Hand-written ticket\n"
        "status: todo\n"
        "created: 2026-08-08\n"
        "updated: 2026-08-08\n"
        "story_id: ST-002\n"
        "testable_outcome: it parses\n"
        "---\n"
        "\n"
        "## What to do\nParse me.\n"
    )
    ticket, body = loads_ticket(text)
    assert isinstance(ticket, Task)
    assert ticket.created == date(2026, 8, 8)
    assert body.startswith("## What to do")


def test_invalid_frontmatter_raises_validation_error() -> None:
    bad = "---\nid: TK-003\ntype: task\ntitle: broken\n---\nbody"
    with pytest.raises(ValidationError):
        loads_ticket(bad)
