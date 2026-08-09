"""Schema validation tests: valid and invalid inputs for each ticket model."""

from datetime import date
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from primer_mcp.models import Adr, Epic, Spike, Story, Task, Ticket

TICKET_ADAPTER: TypeAdapter[Ticket] = TypeAdapter(Ticket)

BASE: dict[str, Any] = {
    "title": "A ticket",
    "created": date(2026, 8, 8),
    "updated": date(2026, 8, 8),
}


def valid_kwargs(model: type) -> dict[str, Any]:
    extras: dict[type, dict[str, Any]] = {
        Epic: {"id": "EP-001", "goals": ["ship it"]},
        Adr: {
            "id": "ADR-001",
            "epic_id": "EP-001",
            "context": "We must choose a data store.",
            "decision": "Markdown files.",
            "consequences": "No query engine; git-native history.",
        },
        Story: {"id": "ST-001", "epic_id": "EP-001", "acceptance_criteria": ["it works"]},
        Task: {"id": "TK-001", "story_id": "ST-001", "testable_outcome": "pytest passes"},
        Spike: {
            "id": "SP-001",
            "story_id": "ST-001",
            "question": "Is vis.js small enough?",
            "timebox": "2 hours",
        },
    }
    return {**BASE, **extras[model]}


@pytest.mark.parametrize("model", [Epic, Adr, Story, Task, Spike])
def test_valid_instance_validates(model: type) -> None:
    ticket = model(**valid_kwargs(model))
    assert ticket.type == model.__name__.lower()


class TestPerTypeStatus:
    def test_task_lifecycle_statuses_accepted(self) -> None:
        for status in ("todo", "in-progress", "blocked", "completed", "verified"):
            assert Task(**valid_kwargs(Task), status=status).status == status

    def test_task_rejects_done(self) -> None:
        with pytest.raises(ValidationError):
            Task(**valid_kwargs(Task), status="done")

    def test_epic_rejects_verified(self) -> None:
        with pytest.raises(ValidationError):
            Epic(**valid_kwargs(Epic), status="verified")

    def test_adr_is_born_done(self) -> None:
        assert Adr(**valid_kwargs(Adr)).status == "done"

    def test_adr_rejects_todo(self) -> None:
        with pytest.raises(ValidationError):
            Adr(**valid_kwargs(Adr), status="todo")


class TestIdPatterns:
    def test_unpadded_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Epic(**{**valid_kwargs(Epic), "id": "EP-1"})

    def test_wrong_prefix_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Task(**{**valid_kwargs(Task), "id": "TASK-001"})

    def test_ids_beyond_999_accepted(self) -> None:
        assert Story(**{**valid_kwargs(Story), "id": "ST-1234"}).id == "ST-1234"

    def test_parent_id_pattern_enforced(self) -> None:
        with pytest.raises(ValidationError):
            Story(**{**valid_kwargs(Story), "epic_id": "ST-001"})


class TestEdges:
    def test_cross_type_edges_accepted(self) -> None:
        epic = Epic(**valid_kwargs(Epic), blocked_by=["ST-002", "TK-010", "ADR-003"])
        assert epic.blocked_by == ["ST-002", "TK-010", "ADR-003"]

    def test_malformed_edge_rejected(self) -> None:
        with pytest.raises(ValidationError, match="dependency edge"):
            Task(**valid_kwargs(Task), blocked_by=["banana"])

    def test_blocks_field_is_gone(self) -> None:
        # blocked_by is the only stored edge; "A blocks B" is recorded on B.
        # extra="forbid" turns a stale `blocks:` key into a clear failure
        # rather than a silently ignored field.
        with pytest.raises(ValidationError):
            Task(**valid_kwargs(Task), blocks=["TK-002"])


class TestStrictness:
    def test_missing_parent_id_rejected(self) -> None:
        kwargs = valid_kwargs(Adr)
        del kwargs["epic_id"]
        with pytest.raises(ValidationError):
            Adr(**kwargs)

    def test_unknown_extra_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Epic(**valid_kwargs(Epic), priority="high")


class TestDiscriminatedUnion:
    def test_type_field_selects_model(self) -> None:
        data = {**valid_kwargs(Task), "type": "task"}
        data["created"] = "2026-08-08"
        data["updated"] = "2026-08-08"
        assert isinstance(TICKET_ADAPTER.validate_python(data), Task)

    def test_unknown_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TICKET_ADAPTER.validate_python({**valid_kwargs(Epic), "type": "initiative"})
