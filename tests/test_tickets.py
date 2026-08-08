"""Ticket creation tests: file output, templates, ID sequencing, and workflow gates."""

from pathlib import Path

import pytest

from primer_mcp.models import Adr, Epic, Spike, Story, Task
from primer_mcp.project import init_project
from primer_mcp.storage import dumps_ticket, loads_ticket
from primer_mcp.tickets import (
    GateError,
    create_spike,
    create_story,
    create_task,
    plan_epic,
    record_adr,
    start_task,
)

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


def make_adr(project: Path, epic_id: str) -> str:
    lines = record_adr(
        project, epic_id, title="Use markdown", context="Need a store.",
        decision="Markdown files.", alternatives=["SQLite"], consequences="Git-native.",
    )
    return lines[0].split()[1].rstrip(":")


def make_story(project: Path, epic_id: str, title: str = "First story") -> str:
    lines = create_story(project, epic_id, title, what="Build something")
    return lines[0].split()[1].rstrip(":")


STORY_HEADINGS = [
    "## Parent Epic",
    "## What",
    "## Acceptance Criteria",
    "## Definition of Done",
    "## Dependencies",
]

TASK_HEADINGS = [
    "## Parent Story",
    "## What to do",
    "## Testable Outcome",
    "## Dependencies",
    "## Completion Notes",
    "## Verification Evidence",
]

SPIKE_HEADINGS = [
    "## Parent Story",
    "## Question",
    "## Timebox",
    "## Findings",
]


class TestCreateStory:
    def test_writes_valid_story_file(self, project: Path) -> None:
        epic_id = make_epic(project)
        make_adr(project, epic_id)
        story_id = make_story(project, epic_id)
        ticket, body = loads_ticket(
            (project / f"primer/stories/{story_id}.md").read_text()
        )
        assert isinstance(ticket, Story)
        assert ticket.epic_id == epic_id
        assert ticket.status == "todo"
        assert f"[[{epic_id}]]" in body

    def test_body_follows_template_in_order(self, project: Path) -> None:
        epic_id = make_epic(project)
        make_adr(project, epic_id)
        make_story(project, epic_id)
        _, body = loads_ticket(
            (project / "primer/stories/ST-001.md").read_text()
        )
        positions = [body.find(h) for h in STORY_HEADINGS]
        assert -1 not in positions
        assert positions == sorted(positions)

    def test_acceptance_criteria_rendered_as_checklist(self, project: Path) -> None:
        epic_id = make_epic(project)
        make_adr(project, epic_id)
        create_story(project, epic_id, "s", what="w", acceptance_criteria=["passes", "fast"])
        _, body = loads_ticket(
            (project / "primer/stories/ST-001.md").read_text()
        )
        assert "- [ ] passes" in body
        assert "- [ ] fast" in body

    def test_sequential_ids(self, project: Path) -> None:
        epic_id = make_epic(project)
        make_adr(project, epic_id)
        assert make_story(project, epic_id, "one") == "ST-001"
        assert make_story(project, epic_id, "two") == "ST-002"

    def test_gate_epic_not_found(self, project: Path) -> None:
        make_epic(project)
        with pytest.raises(GateError) as exc:
            create_story(project, "EP-999", "s", what="w")
        msg = str(exc.value)
        assert "EP-999" in msg
        assert "EP-001" in msg

    def test_gate_epic_has_no_adrs(self, project: Path) -> None:
        epic_id = make_epic(project)
        with pytest.raises(GateError) as exc:
            create_story(project, epic_id, "s", what="w")
        msg = str(exc.value)
        assert "no ADRs" in msg
        assert "record_adr" in msg


class TestCreateTask:
    def test_writes_valid_task_file(self, project: Path) -> None:
        epic_id = make_epic(project)
        make_adr(project, epic_id)
        story_id = make_story(project, epic_id)
        lines = create_task(project, story_id, "Do thing", "Implement it", "test passes")
        task_id = lines[0].split()[1].rstrip(":")
        ticket, body = loads_ticket(
            (project / f"primer/tasks/{task_id}.md").read_text()
        )
        assert isinstance(ticket, Task)
        assert ticket.story_id == story_id
        assert ticket.testable_outcome == "test passes"
        assert ticket.status == "todo"
        assert f"[[{story_id}]]" in body

    def test_body_follows_template_in_order(self, project: Path) -> None:
        epic_id = make_epic(project)
        make_adr(project, epic_id)
        story_id = make_story(project, epic_id)
        create_task(project, story_id, "t", "do it", "done")
        _, body = loads_ticket(
            (project / "primer/tasks/TK-001.md").read_text()
        )
        positions = [body.find(h) for h in TASK_HEADINGS]
        assert -1 not in positions
        assert positions == sorted(positions)

    def test_gate_story_not_found(self, project: Path) -> None:
        with pytest.raises(GateError) as exc:
            create_task(project, "ST-999", "t", "w", "o")
        msg = str(exc.value)
        assert "ST-999" in msg
        assert "create_story" in msg


class TestCreateSpike:
    def test_writes_valid_spike_file(self, project: Path) -> None:
        epic_id = make_epic(project)
        make_adr(project, epic_id)
        story_id = make_story(project, epic_id)
        lines = create_spike(project, story_id, "Investigate X", "Is X feasible?", "2 hours")
        spike_id = lines[0].split()[1].rstrip(":")
        ticket, body = loads_ticket(
            (project / f"primer/spikes/{spike_id}.md").read_text()
        )
        assert isinstance(ticket, Spike)
        assert ticket.story_id == story_id
        assert ticket.question == "Is X feasible?"
        assert ticket.timebox == "2 hours"
        assert f"[[{story_id}]]" in body

    def test_body_follows_template_in_order(self, project: Path) -> None:
        epic_id = make_epic(project)
        make_adr(project, epic_id)
        story_id = make_story(project, epic_id)
        create_spike(project, story_id, "s", "q?", "1 hour")
        _, body = loads_ticket(
            (project / "primer/spikes/SP-001.md").read_text()
        )
        positions = [body.find(h) for h in SPIKE_HEADINGS]
        assert -1 not in positions
        assert positions == sorted(positions)

    def test_gate_story_not_found(self, project: Path) -> None:
        with pytest.raises(GateError) as exc:
            create_spike(project, "ST-999", "s", "q?", "1h")
        msg = str(exc.value)
        assert "ST-999" in msg

    def test_timebox_in_response(self, project: Path) -> None:
        epic_id = make_epic(project)
        make_adr(project, epic_id)
        story_id = make_story(project, epic_id)
        lines = create_spike(project, story_id, "s", "q?", "3 hours")
        assert "3 hours" in lines[1]


class TestStartTask:
    def _make_task(self, project: Path) -> str:
        epic_id = make_epic(project)
        make_adr(project, epic_id)
        story_id = make_story(project, epic_id)
        lines = create_task(project, story_id, "Do thing", "impl", "test passes")
        return lines[0].split()[1].rstrip(":")

    def test_transitions_todo_to_in_progress(self, project: Path) -> None:
        task_id = self._make_task(project)
        lines = start_task(project, task_id)
        assert "in-progress" in lines[0]
        ticket, _ = loads_ticket(
            (project / f"primer/tasks/{task_id}.md").read_text()
        )
        assert isinstance(ticket, Task)
        assert ticket.status == "in-progress"

    def test_transitions_blocked_to_in_progress(self, project: Path) -> None:
        task_id = self._make_task(project)
        path = project / f"primer/tasks/{task_id}.md"
        ticket, body = loads_ticket(path.read_text())
        assert isinstance(ticket, Task)
        blocked = ticket.model_copy(update={"status": "blocked"})
        path.write_text(dumps_ticket(blocked, body), encoding="utf-8")

        start_task(project, task_id)
        reloaded, _ = loads_ticket(path.read_text())
        assert isinstance(reloaded, Task)
        assert reloaded.status == "in-progress"

    def test_rejects_already_in_progress(self, project: Path) -> None:
        task_id = self._make_task(project)
        start_task(project, task_id)
        with pytest.raises(GateError, match="already in-progress"):
            start_task(project, task_id)

    def test_rejects_completed(self, project: Path) -> None:
        task_id = self._make_task(project)
        path = project / f"primer/tasks/{task_id}.md"
        ticket, body = loads_ticket(path.read_text())
        assert isinstance(ticket, Task)
        completed = ticket.model_copy(update={"status": "completed"})
        path.write_text(dumps_ticket(completed, body), encoding="utf-8")

        with pytest.raises(GateError, match="cannot go back"):
            start_task(project, task_id)

    def test_rejects_verified(self, project: Path) -> None:
        task_id = self._make_task(project)
        path = project / f"primer/tasks/{task_id}.md"
        ticket, body = loads_ticket(path.read_text())
        assert isinstance(ticket, Task)
        verified = ticket.model_copy(update={"status": "verified"})
        path.write_text(dumps_ticket(verified, body), encoding="utf-8")

        with pytest.raises(GateError, match="cannot go back"):
            start_task(project, task_id)

    def test_gate_task_not_found(self, project: Path) -> None:
        with pytest.raises(GateError, match="TK-999"):
            start_task(project, "TK-999")

    def test_updated_date_refreshed(self, project: Path) -> None:
        task_id = self._make_task(project)
        ticket_before, _ = loads_ticket(
            (project / f"primer/tasks/{task_id}.md").read_text()
        )
        start_task(project, task_id)
        ticket_after, _ = loads_ticket(
            (project / f"primer/tasks/{task_id}.md").read_text()
        )
        assert isinstance(ticket_before, Task)
        assert isinstance(ticket_after, Task)
        assert ticket_after.updated >= ticket_before.updated
