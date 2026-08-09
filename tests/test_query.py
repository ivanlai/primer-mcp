"""Read and update tools: listing, retrieval, and the gates on update_ticket."""

from pathlib import Path

import pytest

from primer_mcp.errors import GateError
from primer_mcp.graph import find_path
from primer_mcp.project import init_project
from primer_mcp.query import get_ticket, list_tickets, update_ticket
from primer_mcp.storage import loads_ticket
from primer_mcp.tickets import (
    complete_spike,
    complete_task,
    create_spike,
    create_story,
    create_task,
    plan_epic,
    record_adr,
    start_task,
    verify_task,
)


def _id(lines: list[str]) -> str:
    return lines[0].split()[1].rstrip(":")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """An epic with one ADR, one story, and two tasks under it."""
    init_project(tmp_path, "demo")
    epic_id = _id(plan_epic(tmp_path, "Epic", why="w", goals=["g"]))
    record_adr(
        tmp_path,
        epic_id,
        "Decision",
        context="c",
        decision="d",
        alternatives=[],
        consequences="q",
    )
    story_id = _id(create_story(tmp_path, epic_id, "Story", what="w"))
    for title in ("First", "Second"):
        create_task(tmp_path, story_id, title, what_to_do="w", testable_outcome="o")
    return tmp_path


def status_of(project: Path, ticket_id: str) -> str:
    ticket, _ = loads_ticket(find_path(project, ticket_id).read_text())
    return ticket.status


class TestListTickets:
    def test_lists_everything_in_hierarchy_order(self, project: Path) -> None:
        lines = list_tickets(project)
        assert [line.split()[0] for line in lines] == [
            "EP-001",
            "ADR-001",
            "ST-001",
            "TK-001",
            "TK-002",
        ]

    def test_filters_by_type(self, project: Path) -> None:
        assert [line.split()[0] for line in list_tickets(project, ticket_type="task")] == [
            "TK-001",
            "TK-002",
        ]

    def test_filters_by_status(self, project: Path) -> None:
        start_task(project, "TK-001")
        lines = list_tickets(project, status="in-progress")
        assert len(lines) == 1 and "TK-001" in lines[0]

    def test_no_match_says_so_rather_than_returning_nothing(self, project: Path) -> None:
        # An empty list would read as "the call failed" to an agent.
        lines = list_tickets(project, status="blocked")
        assert len(lines) == 1 and "list_tickets" in lines[0]

    def test_unknown_type_is_rejected_with_the_valid_ones(self, project: Path) -> None:
        with pytest.raises(GateError, match="story"):
            list_tickets(project, ticket_type="bug")


class TestGetTicket:
    def test_returns_the_file_verbatim(self, project: Path) -> None:
        body = "\n".join(get_ticket(project, "TK-001"))
        assert "## Testable Outcome" in body
        assert "id: TK-001" in body

    def test_reports_the_edge_it_does_not_store(self, project: Path) -> None:
        # TK-001 holds up TK-002, but only TK-002 records the edge.
        update_ticket(project, "TK-002", blocked_by=["TK-001"])
        assert "blocked_by: []" in "\n".join(get_ticket(project, "TK-001"))
        assert "Blocks (derived" in "\n".join(get_ticket(project, "TK-001"))

    def test_no_edges_means_no_extra_noise(self, project: Path) -> None:
        assert "Blocks" not in "\n".join(get_ticket(project, "TK-001"))

    def test_unknown_id_is_a_gate_error(self, project: Path) -> None:
        with pytest.raises(GateError, match="TK-404"):
            get_ticket(project, "TK-404")


class TestUpdateStatus:
    def test_sets_blocked(self, project: Path) -> None:
        update_ticket(project, "TK-001", status="blocked")
        assert status_of(project, "TK-001") == "blocked"

    def test_verified_is_rejected_pointing_at_verify_task(self, project: Path) -> None:
        with pytest.raises(GateError, match="verify_task"):
            update_ticket(project, "TK-001", status="verified")

    def test_completed_is_rejected_pointing_at_complete_task(self, project: Path) -> None:
        with pytest.raises(GateError, match="complete_task"):
            update_ticket(project, "TK-001", status="completed")

    def test_done_on_a_story_explains_it_is_derived(self, project: Path) -> None:
        with pytest.raises(GateError, match="derived"):
            update_ticket(project, "ST-001", status="done")

    def test_adr_has_no_lifecycle(self, project: Path) -> None:
        with pytest.raises(GateError, match="no lifecycle"):
            update_ticket(project, "ADR-001", status="blocked")

    def test_unknown_status_lists_the_settable_ones(self, project: Path) -> None:
        with pytest.raises(GateError, match="in-progress"):
            update_ticket(project, "TK-001", status="wibble")


class TestTerminalGuard:
    """Either side of the line that keeps the derived-status cascade sound."""

    def finish(self, project: Path, task_id: str) -> None:
        start_task(project, task_id)
        complete_task(project, task_id, "notes")
        verify_task(project, task_id, "evidence")

    def test_a_verified_task_cannot_be_reopened(self, project: Path) -> None:
        self.finish(project, "TK-001")
        with pytest.raises(GateError, match="terminal"):
            update_ticket(project, "TK-001", status="in-progress")

    def test_a_completed_task_can_go_back_to_in_progress(self, project: Path) -> None:
        # `completed` is intermediate: no evidence recorded yet, nothing to
        # contradict, and no parent's criteria change.
        start_task(project, "TK-001")
        complete_task(project, "TK-001", "notes")
        update_ticket(project, "TK-001", status="in-progress")
        assert status_of(project, "TK-001") == "in-progress"

    def test_a_done_spike_cannot_be_reopened(self, project: Path) -> None:
        spike_id = _id(create_spike(project, "ST-001", "S", question="?", timebox="1h"))
        complete_spike(project, spike_id, "findings")
        with pytest.raises(GateError, match="terminal"):
            update_ticket(project, spike_id, status="todo")

    def test_a_done_story_cannot_be_reopened(self, project: Path) -> None:
        self.finish(project, "TK-001")
        self.finish(project, "TK-002")
        assert status_of(project, "ST-001") == "done"
        with pytest.raises(GateError, match="terminal"):
            update_ticket(project, "ST-001", status="in-progress")


class TestUpdateEdges:
    def test_records_a_dependency(self, project: Path) -> None:
        update_ticket(project, "TK-002", blocked_by=["TK-001"])
        ticket, _ = loads_ticket(find_path(project, "TK-002").read_text())
        assert ticket.blocked_by == ["TK-001"]

    def test_replaces_rather_than_appends(self, project: Path) -> None:
        update_ticket(project, "TK-002", blocked_by=["TK-001"])
        update_ticket(project, "TK-002", blocked_by=[])
        ticket, _ = loads_ticket(find_path(project, "TK-002").read_text())
        assert ticket.blocked_by == []

    def test_unknown_reference_is_rejected(self, project: Path) -> None:
        with pytest.raises(GateError, match="TK-404"):
            update_ticket(project, "TK-002", blocked_by=["TK-404"])

    def test_cycle_is_rejected_and_the_file_is_untouched(self, project: Path) -> None:
        update_ticket(project, "TK-002", blocked_by=["TK-001"])
        before = find_path(project, "TK-001").read_bytes()
        with pytest.raises(GateError, match="cycle"):
            update_ticket(project, "TK-001", blocked_by=["TK-002"])
        assert find_path(project, "TK-001").read_bytes() == before

    def test_self_reference_is_a_cycle(self, project: Path) -> None:
        with pytest.raises(GateError, match="cycle"):
            update_ticket(project, "TK-001", blocked_by=["TK-001"])

    def test_cross_type_edges_are_allowed(self, project: Path) -> None:
        # Any ticket may block any other; the hierarchy is not the graph.
        update_ticket(project, "TK-001", blocked_by=["ST-001"])
        ticket, _ = loads_ticket(find_path(project, "TK-001").read_text())
        assert ticket.blocked_by == ["ST-001"]


class TestUpdateBodyAndRefs:
    def test_replaces_a_section(self, project: Path) -> None:
        update_ticket(project, "TK-001", body_sections={"What to do": "Something else"})
        assert "Something else" in "\n".join(get_ticket(project, "TK-001"))

    def test_other_sections_survive(self, project: Path) -> None:
        update_ticket(project, "TK-001", body_sections={"What to do": "Something else"})
        assert "## Testable Outcome" in "\n".join(get_ticket(project, "TK-001"))

    def test_unknown_heading_lists_the_real_ones(self, project: Path) -> None:
        with pytest.raises(GateError, match="Testable Outcome"):
            update_ticket(project, "TK-001", body_sections={"Nonexistent": "x"})

    def test_records_an_external_ref(self, project: Path) -> None:
        update_ticket(project, "ST-001", external_ref={"jira": "PROJ-123"})
        ticket, _ = loads_ticket(find_path(project, "ST-001").read_text())
        assert ticket.external_ref == {"jira": "PROJ-123"}

    def test_empty_update_is_rejected(self, project: Path) -> None:
        with pytest.raises(GateError, match="Nothing to update"):
            update_ticket(project, "TK-001")

    def test_updated_date_is_bumped(self, project: Path) -> None:
        before, _ = loads_ticket(find_path(project, "TK-001").read_text())
        update_ticket(project, "TK-001", status="blocked")
        after, _ = loads_ticket(find_path(project, "TK-001").read_text())
        assert after.updated >= before.updated
