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

# Any ticket may reference any other ticket in blocks/blocked_by,
# so edge entries accept every type prefix.
TICKET_ID_PATTERN = re.compile(r"^(EP|ADR|ST|TK|SP)-\d{3,}$")


class TicketBase(BaseModel):
    """Fields common to every ticket type, including graph edges."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    created: date
    updated: date
    blocks: list[str] = Field(default_factory=list)
    blocked_by: list[str] = Field(default_factory=list)
    external_ref: dict[str, str] = Field(default_factory=dict)

    @field_validator("blocks", "blocked_by")
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
    id: str = Field(pattern=r"^EP-\d{3,}$")
    status: Literal["todo", "in-progress", "blocked", "done"] = "todo"
    goals: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    non_goals: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)


class Adr(TicketBase):
    type: Literal["adr"] = "adr"
    id: str = Field(pattern=r"^ADR-\d{3,}$")
    # An ADR records a decision already made — created done, no active lifecycle.
    status: Literal["done"] = "done"
    epic_id: str = Field(pattern=r"^EP-\d{3,}$")
    context: str
    decision: str
    alternatives: list[str] = Field(default_factory=list)
    consequences: str


class Story(TicketBase):
    type: Literal["story"] = "story"
    id: str = Field(pattern=r"^ST-\d{3,}$")
    status: Literal["todo", "in-progress", "blocked", "done"] = "todo"
    epic_id: str = Field(pattern=r"^EP-\d{3,}$")
    acceptance_criteria: list[str] = Field(default_factory=list)
    definition_of_done: list[str] = Field(default_factory=list)


class Task(TicketBase):
    type: Literal["task"] = "task"
    id: str = Field(pattern=r"^TK-\d{3,}$")
    # Two-phase completion: complete_task sets "completed", verify_task sets "verified".
    status: Literal["todo", "in-progress", "blocked", "completed", "verified"] = "todo"
    story_id: str = Field(pattern=r"^ST-\d{3,}$")
    testable_outcome: str
    completed_notes: str = ""
    verified_evidence: str = ""


class Spike(TicketBase):
    type: Literal["spike"] = "spike"
    id: str = Field(pattern=r"^SP-\d{3,}$")
    status: Literal["todo", "in-progress", "blocked", "done"] = "todo"
    story_id: str = Field(pattern=r"^ST-\d{3,}$")
    question: str
    timebox: str
    findings: str = ""


Ticket = Annotated[Epic | Adr | Story | Task | Spike, Field(discriminator="type")]
