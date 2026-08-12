"""
Ticket creation tests: file output, templates, ID sequencing, and workflow gates.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from primer_mcp.graph import find_path
from primer_mcp.models import Adr, Epic, Spike, Story, Task
from primer_mcp.storage import dumps_ticket, loads_ticket
from primer_mcp.tickets import (
    GateError,
    _update_section,
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



class TestUpdateSection:
    BODY = (
        "## What to do\nfix the bug\n\n"
        "## Completion Notes\nold notes\n\n"
        "## Verification Evidence\n"
    )

    def test_replaces_exact_heading(self) -> None:
        result = _update_section(self.BODY, "Completion Notes", "new notes")
        assert "new notes" in result
        assert "old notes" not in result
        assert "## What to do\nfix the bug" in result

    def test_prefix_heading_raises(self) -> None:
        with pytest.raises(ValueError, match="Section not found"):
            _update_section(self.BODY, "What", "oops")

    def test_heading_like_text_mid_line_not_matched(self) -> None:
        body = "see ## Findings in the other ticket\n\n## Findings\nreal stuff\n"
        result = _update_section(body, "Findings", "updated")
        assert "see ## Findings in the other ticket" in result
        assert "updated" in result
        assert "real stuff" not in result

    def test_missing_heading_raises(self) -> None:
        with pytest.raises(ValueError, match="Section not found"):
            _update_section(self.BODY, "Nonexistent", "content")


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
    "## Governing ADRs",
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

    def test_no_adr_creates_story_with_nudge(self, project: Path) -> None:
        epic_id = make_epic(project)
        result = create_story(project, epic_id, "s", what="w")
        assert any("record_adr" in line for line in result)
        assert any("ST-" in line for line in result)

    def test_create_story_with_adr_ids(self, project: Path) -> None:
        epic_id = make_epic(project)
        adr_id = make_adr(project, epic_id)
        create_story(project, epic_id, "s", what="w", adr_ids=[adr_id])
        ticket, body = loads_ticket(
            (project / "primer/stories/ST-001.md").read_text()
        )
        assert isinstance(ticket, Story)
        assert ticket.adr_ids == [adr_id]
        assert f"[[{adr_id}]]" in body

    def test_create_story_rejects_unknown_adr(self, project: Path) -> None:
        epic_id = make_epic(project)
        make_adr(project, epic_id)
        with pytest.raises(GateError, match="ADR-999"):
            create_story(project, epic_id, "s", what="w", adr_ids=["ADR-999"])

    def test_create_story_rejects_adr_from_other_epic(self, project: Path) -> None:
        ep1 = make_epic(project, "First")
        ep2 = make_epic(project, "Second")
        adr_id = make_adr(project, ep2)
        with pytest.raises(GateError, match="belongs to"):
            create_story(project, ep1, "s", what="w", adr_ids=[adr_id])

    def test_create_story_accepts_empty_adr_ids(self, project: Path) -> None:
        epic_id = make_epic(project)
        make_adr(project, epic_id)
        result = create_story(project, epic_id, "s", what="w", adr_ids=[])
        assert any("ST-" in line for line in result)
        ticket, _ = loads_ticket(
            (project / "primer/stories/ST-001.md").read_text()
        )
        assert isinstance(ticket, Story)
        assert ticket.adr_ids == []


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

    def test_already_in_progress_is_idempotent(self, project: Path) -> None:
        task_id = self._make_task(project)
        start_task(project, task_id)
        result = start_task(project, task_id)
        assert any("already in-progress" in line for line in result)
        reloaded, _ = loads_ticket(
            (project / f"primer/tasks/{task_id}.md").read_text()
        )
        assert isinstance(reloaded, Task)
        assert reloaded.status == "in-progress"

    def test_completed_reopens_with_nudge(self, project: Path) -> None:
        task_id = self._make_task(project)
        path = project / f"primer/tasks/{task_id}.md"
        ticket, body = loads_ticket(path.read_text())
        assert isinstance(ticket, Task)
        completed = ticket.model_copy(update={"status": "completed"})
        path.write_text(dumps_ticket(completed, body), encoding="utf-8")

        result = start_task(project, task_id)
        assert any("already completed" in line for line in result)
        reloaded, _ = loads_ticket(path.read_text())
        assert isinstance(reloaded, Task)
        assert reloaded.status == "in-progress"

    def test_verified_reopens_with_nudge(self, project: Path) -> None:
        task_id = self._make_task(project)
        path = project / f"primer/tasks/{task_id}.md"
        ticket, body = loads_ticket(path.read_text())
        assert isinstance(ticket, Task)
        verified = ticket.model_copy(update={"status": "verified"})
        path.write_text(dumps_ticket(verified, body), encoding="utf-8")

        result = start_task(project, task_id)
        assert any("already verified" in line for line in result)
        reloaded, _ = loads_ticket(path.read_text())
        assert isinstance(reloaded, Task)
        assert reloaded.status == "in-progress"

    def test_gate_task_not_found(self, project: Path) -> None:
        with pytest.raises(GateError, match="TK-999"):
            start_task(project, "TK-999")

    def test_updated_date_refreshed(self, project: Path) -> None:
        task_id = self._make_task(project)
        path = project / f"primer/tasks/{task_id}.md"
        ticket, body = loads_ticket(path.read_text())
        yesterday = datetime.now(tz=UTC).date() - timedelta(days=1)
        path.write_text(dumps_ticket(ticket.model_copy(update={"updated": yesterday}), body))
        start_task(project, task_id)
        reloaded, _ = loads_ticket(path.read_text())
        assert reloaded.updated == datetime.now(tz=UTC).date()


def _make_in_progress_task(project: Path) -> str:
    epic_id = make_epic(project)
    make_adr(project, epic_id)
    story_id = make_story(project, epic_id)
    lines = create_task(project, story_id, "Do thing", "impl", "test passes")
    task_id = lines[0].split()[1].rstrip(":")
    start_task(project, task_id)
    return task_id


def _make_spike(project: Path) -> str:
    epic_id = make_epic(project)
    make_adr(project, epic_id)
    story_id = make_story(project, epic_id)
    lines = create_spike(project, story_id, "Investigate X", "Is X feasible?", "2 hours")
    return lines[0].split()[1].rstrip(":")


class TestCompleteTask:
    def test_transitions_in_progress_to_completed(self, project: Path) -> None:
        task_id = _make_in_progress_task(project)
        lines = complete_task(project, task_id, "Implemented the feature")
        assert "completed" in lines[0]
        ticket, body = loads_ticket(
            (project / f"primer/tasks/{task_id}.md").read_text()
        )
        assert isinstance(ticket, Task)
        assert ticket.status == "completed"
        assert ticket.completed_notes == "Implemented the feature"
        assert "Implemented the feature" in body

    def test_body_completion_notes_updated(self, project: Path) -> None:
        task_id = _make_in_progress_task(project)
        complete_task(project, task_id, "All tests pass")
        _, body = loads_ticket(
            (project / f"primer/tasks/{task_id}.md").read_text()
        )
        notes_pos = body.find("## Completion Notes")
        evidence_pos = body.find("## Verification Evidence")
        assert notes_pos < evidence_pos
        section = body[notes_pos:evidence_pos]
        assert "All tests pass" in section

    def test_todo_completes_with_nudge(self, project: Path) -> None:
        epic_id = make_epic(project)
        make_adr(project, epic_id)
        story_id = make_story(project, epic_id)
        lines = create_task(project, story_id, "t", "w", "o")
        task_id = lines[0].split()[1].rstrip(":")
        result = complete_task(project, task_id, "notes")
        assert any("start_task" in line for line in result)
        reloaded, _ = loads_ticket(
            (project / f"primer/tasks/{task_id}.md").read_text()
        )
        assert isinstance(reloaded, Task)
        assert reloaded.status == "completed"
        assert reloaded.completed_notes == "notes"

    def test_blocked_completes_with_nudge(self, project: Path) -> None:
        task_id = _make_in_progress_task(project)
        path = project / f"primer/tasks/{task_id}.md"
        ticket, body = loads_ticket(path.read_text())
        assert isinstance(ticket, Task)
        path.write_text(
            dumps_ticket(ticket.model_copy(update={"status": "blocked"}), body)
        )
        result = complete_task(project, task_id, "notes")
        assert any("blocked" in line for line in result)
        reloaded, _ = loads_ticket(path.read_text())
        assert isinstance(reloaded, Task)
        assert reloaded.status == "completed"

    def test_already_completed_updates_notes(self, project: Path) -> None:
        task_id = _make_in_progress_task(project)
        complete_task(project, task_id, "done")
        result = complete_task(project, task_id, "updated notes")
        assert any("already completed" in line for line in result)
        reloaded, _ = loads_ticket(
            (project / f"primer/tasks/{task_id}.md").read_text()
        )
        assert isinstance(reloaded, Task)
        assert reloaded.completed_notes == "updated notes"

    def test_verified_reopens_with_nudge(self, project: Path) -> None:
        task_id = _make_in_progress_task(project)
        complete_task(project, task_id, "done")
        verify_task(project, task_id, "proof")
        result = complete_task(project, task_id, "again")
        assert any("already verified" in line for line in result)
        reloaded, _ = loads_ticket(
            (project / f"primer/tasks/{task_id}.md").read_text()
        )
        assert isinstance(reloaded, Task)
        assert reloaded.status == "completed"

    def test_task_not_found(self, project: Path) -> None:
        with pytest.raises(GateError, match="TK-999"):
            complete_task(project, "TK-999", "notes")

    def test_updated_date_refreshed(self, project: Path) -> None:
        task_id = _make_in_progress_task(project)
        path = project / f"primer/tasks/{task_id}.md"
        ticket, body = loads_ticket(path.read_text())
        yesterday = datetime.now(tz=UTC).date() - timedelta(days=1)
        path.write_text(dumps_ticket(ticket.model_copy(update={"updated": yesterday}), body))
        complete_task(project, task_id, "done")
        reloaded, _ = loads_ticket(path.read_text())
        assert reloaded.updated == datetime.now(tz=UTC).date()


class TestVerifyTask:
    def test_transitions_completed_to_verified(self, project: Path) -> None:
        task_id = _make_in_progress_task(project)
        complete_task(project, task_id, "done")
        lines = verify_task(project, task_id, "pytest output: 5 passed")
        assert "verified" in lines[0]
        ticket, body = loads_ticket(
            (project / f"primer/tasks/{task_id}.md").read_text()
        )
        assert isinstance(ticket, Task)
        assert ticket.status == "verified"
        assert ticket.verified_evidence == "pytest output: 5 passed"
        assert "pytest output: 5 passed" in body

    def test_body_verification_evidence_updated(self, project: Path) -> None:
        task_id = _make_in_progress_task(project)
        complete_task(project, task_id, "done")
        verify_task(project, task_id, "All green")
        _, body = loads_ticket(
            (project / f"primer/tasks/{task_id}.md").read_text()
        )
        evidence_pos = body.find("## Verification Evidence")
        assert evidence_pos != -1
        section = body[evidence_pos:]
        assert "All green" in section

    def test_todo_verifies_with_nudge(self, project: Path) -> None:
        epic_id = make_epic(project)
        make_adr(project, epic_id)
        story_id = make_story(project, epic_id)
        lines = create_task(project, story_id, "t", "w", "o")
        task_id = lines[0].split()[1].rstrip(":")
        result = verify_task(project, task_id, "evidence")
        assert any("complete_task" in line for line in result)
        reloaded, _ = loads_ticket(
            (project / f"primer/tasks/{task_id}.md").read_text()
        )
        assert isinstance(reloaded, Task)
        assert reloaded.status == "verified"
        assert reloaded.verified_evidence == "evidence"

    def test_in_progress_verifies_with_nudge(self, project: Path) -> None:
        task_id = _make_in_progress_task(project)
        result = verify_task(project, task_id, "evidence")
        assert any("complete_task" in line for line in result)
        reloaded, _ = loads_ticket(
            (project / f"primer/tasks/{task_id}.md").read_text()
        )
        assert isinstance(reloaded, Task)
        assert reloaded.status == "verified"

    def test_blocked_verifies_with_nudge(self, project: Path) -> None:
        task_id = _make_in_progress_task(project)
        path = project / f"primer/tasks/{task_id}.md"
        ticket, body = loads_ticket(path.read_text())
        assert isinstance(ticket, Task)
        path.write_text(
            dumps_ticket(ticket.model_copy(update={"status": "blocked"}), body)
        )
        result = verify_task(project, task_id, "evidence")
        assert any("blocked" in line for line in result)
        reloaded, _ = loads_ticket(path.read_text())
        assert isinstance(reloaded, Task)
        assert reloaded.status == "verified"

    def test_already_verified_updates_evidence(self, project: Path) -> None:
        task_id = _make_in_progress_task(project)
        complete_task(project, task_id, "done")
        verify_task(project, task_id, "proof")
        result = verify_task(project, task_id, "better proof")
        assert any("already verified" in line for line in result)
        reloaded, _ = loads_ticket(
            (project / f"primer/tasks/{task_id}.md").read_text()
        )
        assert isinstance(reloaded, Task)
        assert reloaded.verified_evidence == "better proof"

    def test_task_not_found(self, project: Path) -> None:
        with pytest.raises(GateError, match="TK-999"):
            verify_task(project, "TK-999", "evidence")

    def test_updated_date_refreshed(self, project: Path) -> None:
        task_id = _make_in_progress_task(project)
        complete_task(project, task_id, "done")
        path = project / f"primer/tasks/{task_id}.md"
        ticket, body = loads_ticket(path.read_text())
        yesterday = datetime.now(tz=UTC).date() - timedelta(days=1)
        path.write_text(dumps_ticket(ticket.model_copy(update={"updated": yesterday}), body))
        verify_task(project, task_id, "proof")
        reloaded, _ = loads_ticket(path.read_text())
        assert reloaded.updated == datetime.now(tz=UTC).date()


class TestCompleteSpike:
    def test_transitions_todo_to_done(self, project: Path) -> None:
        spike_id = _make_spike(project)
        lines = complete_spike(project, spike_id, "X is feasible")
        assert "done" in lines[0]
        ticket, body = loads_ticket(
            (project / f"primer/spikes/{spike_id}.md").read_text()
        )
        assert isinstance(ticket, Spike)
        assert ticket.status == "done"
        assert ticket.findings == "X is feasible"
        assert "X is feasible" in body

    def test_transitions_in_progress_to_done(self, project: Path) -> None:
        spike_id = _make_spike(project)
        path = project / f"primer/spikes/{spike_id}.md"
        ticket, body = loads_ticket(path.read_text())
        assert isinstance(ticket, Spike)
        path.write_text(
            dumps_ticket(ticket.model_copy(update={"status": "in-progress"}), body)
        )
        complete_spike(project, spike_id, "Findings here")
        reloaded, _ = loads_ticket(path.read_text())
        assert isinstance(reloaded, Spike)
        assert reloaded.status == "done"

    def test_body_findings_updated(self, project: Path) -> None:
        spike_id = _make_spike(project)
        complete_spike(project, spike_id, "Answer: yes it works")
        _, body = loads_ticket(
            (project / f"primer/spikes/{spike_id}.md").read_text()
        )
        findings_pos = body.find("## Findings")
        assert findings_pos != -1
        section = body[findings_pos:]
        assert "Answer: yes it works" in section

    def test_blocked_completes_with_nudge(self, project: Path) -> None:
        spike_id = _make_spike(project)
        path = project / f"primer/spikes/{spike_id}.md"
        ticket, body = loads_ticket(path.read_text())
        assert isinstance(ticket, Spike)
        path.write_text(
            dumps_ticket(ticket.model_copy(update={"status": "blocked"}), body)
        )
        result = complete_spike(project, spike_id, "findings")
        assert any("blocked" in line for line in result)
        reloaded, _ = loads_ticket(path.read_text())
        assert isinstance(reloaded, Spike)
        assert reloaded.status == "done"

    def test_already_done_updates_findings(self, project: Path) -> None:
        spike_id = _make_spike(project)
        complete_spike(project, spike_id, "findings")
        result = complete_spike(project, spike_id, "updated findings")
        assert any("already done" in line for line in result)
        reloaded, _ = loads_ticket(
            (project / f"primer/spikes/{spike_id}.md").read_text()
        )
        assert isinstance(reloaded, Spike)
        assert reloaded.findings == "updated findings"

    def test_spike_not_found(self, project: Path) -> None:
        with pytest.raises(GateError, match="SP-999"):
            complete_spike(project, "SP-999", "findings")

    def test_updated_date_refreshed(self, project: Path) -> None:
        spike_id = _make_spike(project)
        path = project / f"primer/spikes/{spike_id}.md"
        ticket, body = loads_ticket(path.read_text())
        yesterday = datetime.now(tz=UTC).date() - timedelta(days=1)
        path.write_text(dumps_ticket(ticket.model_copy(update={"updated": yesterday}), body))
        complete_spike(project, spike_id, "findings")
        reloaded, _ = loads_ticket(path.read_text())
        assert reloaded.updated == datetime.now(tz=UTC).date()


def status_of(project: Path, ticket_id: str) -> str:
    ticket, _ = loads_ticket(find_path(project, ticket_id).read_text())
    return ticket.status


class TestDerivedStatusCascade:
    """
    Completing the last child settles its parents; adding a new one reopens
    them. Both directions run from the write tools, so disk stays honest
    without any read tool having to derive anything.
    """

    def scaffold(self, project: Path) -> tuple[str, str, str]:
        epic_id = make_epic(project)
        make_adr(project, epic_id)
        story_id = make_story(project, epic_id)
        task_id = create_task(
            project, story_id, "Only task", what_to_do="w", testable_outcome="o"
        )[0].split()[1].rstrip(":")
        return epic_id, story_id, task_id

    def finish(self, project: Path, task_id: str) -> list[str]:
        start_task(project, task_id)
        complete_task(project, task_id, "notes")
        return verify_task(project, task_id, "evidence")

    def test_last_verified_task_settles_story_and_epic(self, project: Path) -> None:
        epic_id, story_id, task_id = self.scaffold(project)
        self.finish(project, task_id)
        assert status_of(project, story_id) == "done"
        assert status_of(project, epic_id) == "done"

    def test_cascade_is_reported_to_the_agent(self, project: Path) -> None:
        # The agent needs to know the parents moved; it did not ask for it.
        _, story_id, task_id = self.scaffold(project)
        lines = self.finish(project, task_id)
        assert any(story_id in line and "done" in line for line in lines)

    def test_new_task_reopens_a_finished_story_and_epic(self, project: Path) -> None:
        epic_id, story_id, task_id = self.scaffold(project)
        self.finish(project, task_id)
        create_task(project, story_id, "More work", what_to_do="w", testable_outcome="o")
        assert status_of(project, story_id) == "in-progress"
        assert status_of(project, epic_id) == "in-progress"

    def test_new_story_reopens_a_finished_epic(self, project: Path) -> None:
        epic_id, _, task_id = self.scaffold(project)
        self.finish(project, task_id)
        make_story(project, epic_id, "Second story")
        assert status_of(project, epic_id) == "in-progress"

    def test_completed_but_unverified_leaves_the_story_alone(self, project: Path) -> None:
        # `completed` is the intermediate half of the two-phase gate.
        _, story_id, task_id = self.scaffold(project)
        start_task(project, task_id)
        complete_task(project, task_id, "notes")
        assert status_of(project, story_id) == "todo"

    def test_spike_completion_settles_its_story(self, project: Path) -> None:
        epic_id = make_epic(project)
        make_adr(project, epic_id)
        story_id = make_story(project, epic_id)
        spike_id = create_spike(
            project, story_id, "Investigate", question="?", timebox="1h"
        )[0].split()[1].rstrip(":")
        complete_spike(project, spike_id, "findings")
        assert status_of(project, story_id) == "done"

    def test_a_sibling_still_open_holds_the_story_back(self, project: Path) -> None:
        _, story_id, first = self.scaffold(project)
        create_task(project, story_id, "Second", what_to_do="w", testable_outcome="o")
        self.finish(project, first)
        assert status_of(project, story_id) == "todo"
