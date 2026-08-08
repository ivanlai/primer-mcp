"""plan_epic / record_adr tests: file output, templates, ID sequencing, gate #1."""

from pathlib import Path

import pytest

from primer_mcp.models import Adr, Epic
from primer_mcp.project import init_project
from primer_mcp.storage import loads_ticket
from primer_mcp.tickets import GateError, plan_epic, record_adr

EPIC_HEADINGS = [
    "## Why",
    "## Goals",
    "## Constraints",
    "## Non-Goals",
    "## Success Criteria",
    "## Child ADRs",
    "## Child Stories",
]
ADR_HEADINGS = [
    "## Parent Epic",
    "## Context",
    "## Decision",
    "## Alternatives Considered",
    "## Consequences",
]


@pytest.fixture
def project(tmp_path: Path) -> Path:
    init_project(tmp_path, "demo")
    return tmp_path


def make_epic(project: Path, title: str = "First epic") -> str:
    lines = plan_epic(project, title, why="Because reasons", goals=["goal one"])
    return lines[0].split()[1].rstrip(":")  # "Created EP-001: ..." -> EP-001


class TestPlanEpic:
    def test_writes_valid_epic_file(self, project: Path) -> None:
        make_epic(project)
        ticket, _ = loads_ticket((project / "primer/epics/EP-001.md").read_text())
        assert isinstance(ticket, Epic)
        assert ticket.goals == ["goal one"]
        assert ticket.status == "todo"

    def test_body_follows_template_in_order(self, project: Path) -> None:
        make_epic(project)
        _, body = loads_ticket((project / "primer/epics/EP-001.md").read_text())
        positions = [body.find(h) for h in EPIC_HEADINGS]
        assert -1 not in positions
        assert positions == sorted(positions)

    def test_sequential_ids(self, project: Path) -> None:
        assert make_epic(project, "one") == "EP-001"
        assert make_epic(project, "two") == "EP-002"

    def test_uninitialised_project_gated(self, tmp_path: Path) -> None:
        with pytest.raises(GateError, match="init_project"):
            plan_epic(tmp_path / "nowhere", "t", why="w", goals=[])


class TestRecordAdr:
    def record(self, project: Path, epic_id: str) -> list[str]:
        return record_adr(
            project,
            epic_id,
            title="Use markdown",
            context="Need a store.",
            decision="Markdown files.",
            alternatives=["SQLite — needs a driver"],
            consequences="Git-native history.",
        )

    def test_writes_valid_adr_linked_to_epic(self, project: Path) -> None:
        epic_id = make_epic(project)
        self.record(project, epic_id)
        ticket, body = loads_ticket((project / "primer/adrs/ADR-001.md").read_text())
        assert isinstance(ticket, Adr)
        assert ticket.epic_id == epic_id
        assert ticket.status == "done"  # ADRs are born done
        assert f"[[{epic_id}]]" in body

    def test_body_follows_template_in_order(self, project: Path) -> None:
        self.record(project, make_epic(project))
        _, body = loads_ticket((project / "primer/adrs/ADR-001.md").read_text())
        positions = [body.find(h) for h in ADR_HEADINGS]
        assert -1 not in positions
        assert positions == sorted(positions)

    def test_id_sequence_independent_of_epics(self, project: Path) -> None:
        make_epic(project, "one")
        make_epic(project, "two")
        lines = self.record(project, "EP-002")
        assert lines[0].startswith("Recorded ADR-001")

    def test_gate_missing_epic_steers_agent(self, project: Path) -> None:
        make_epic(project)
        with pytest.raises(GateError) as exc:
            self.record(project, "EP-999")
        message = str(exc.value)
        assert "EP-999" in message  # what failed
        assert "EP-001" in message  # existing epics hint
        assert "record_adr" in message  # exact next call

    def test_gate_no_epics_points_at_plan_epic(self, project: Path) -> None:
        with pytest.raises(GateError, match="plan_epic"):
            self.record(project, "EP-001")
