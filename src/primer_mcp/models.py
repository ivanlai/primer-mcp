"""Pydantic models for all primer-mcp ticket types.

The schema and per-type status sets are defined in docs/architecture.md
(see "Ticket Schema" and "Ticket Lifecycle"). Frontmatter carries the
machine-readable data validated here; the markdown body is free-form.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Ticket ID prefix per type. Single source of truth: the per-model ID
# patterns below and ID generation both derive from it.
ID_PREFIX = {
    "epic": "EP",
    "adr": "ADR",   # Architecture Decision Record (context/decision/consequences)
    "story": "ST",
    "task": "TK",
    "spike": "SP",  # spike = timeboxed investigation (question/timebox/findings)
}


def _id_pattern(ticket_type: str) -> str:
    # e.g. _id_pattern("task") -> r"^TK-\d{3,}$"
    return rf"^{ID_PREFIX[ticket_type]}-\d{{3,}}$"


# Any ticket may reference any other ticket in blocked_by,
# so edge entries accept every type prefix.
TICKET_ID_PATTERN = re.compile(rf"^({'|'.join(ID_PREFIX.values())})-\d{{3,}}$")


class TicketBase(BaseModel):
    """Fields common to every ticket type, including graph edges.

    `blocked_by` is the only stored dependency edge: "A blocks B" and
    "B is blocked by A" are one directed edge stated from two ends, so
    storing both invites drift. The reverse direction is a graph lookup
    at read time, never a field.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    created: date
    updated: date
    blocked_by: list[str] = Field(default_factory=list)
    external_ref: dict[str, str] = Field(default_factory=dict)

    @field_validator("blocked_by")
    @classmethod
    def _validate_edge_ids(cls, value: list[str]) -> list[str]:
        for ticket_id in value:
            if not TICKET_ID_PATTERN.match(ticket_id):
                raise ValueError(
                    f"invalid ticket id in dependency edge: {ticket_id!r} "
                    "(expected e.g. EP-001, ADR-001, ST-001, TK-001, SP-001)"
                )
        return value


class Epic(TicketBase):
    type: Literal["epic"] = "epic"
    id: str = Field(pattern=_id_pattern("epic"))
    status: Literal["todo", "in-progress", "blocked", "done"] = "todo"
    goals: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    non_goals: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)


class Adr(TicketBase):
    type: Literal["adr"] = "adr"
    id: str = Field(pattern=_id_pattern("adr"))
    # An ADR records a decision already made — created done, no active lifecycle.
    status: Literal["done"] = "done"
    epic_id: str = Field(pattern=_id_pattern("epic"))
    context: str
    decision: str
    alternatives: list[str] = Field(default_factory=list)
    consequences: str


class Story(TicketBase):
    type: Literal["story"] = "story"
    id: str = Field(pattern=_id_pattern("story"))
    status: Literal["todo", "in-progress", "blocked", "done"] = "todo"
    epic_id: str = Field(pattern=_id_pattern("epic"))
    acceptance_criteria: list[str] = Field(default_factory=list)
    definition_of_done: list[str] = Field(default_factory=list)


class Task(TicketBase):
    type: Literal["task"] = "task"
    id: str = Field(pattern=_id_pattern("task"))
    # Two-phase completion: complete_task sets "completed", verify_task sets "verified".
    status: Literal["todo", "in-progress", "blocked", "completed", "verified"] = "todo"
    story_id: str = Field(pattern=_id_pattern("story"))
    testable_outcome: str
    completed_notes: str = ""
    verified_evidence: str = ""


class Spike(TicketBase):
    type: Literal["spike"] = "spike"
    id: str = Field(pattern=_id_pattern("spike"))
    status: Literal["todo", "in-progress", "blocked", "done"] = "todo"
    story_id: str = Field(pattern=_id_pattern("story"))
    question: str
    timebox: str
    findings: str = ""


Ticket = Annotated[Epic | Adr | Story | Task | Spike, Field(discriminator="type")]
