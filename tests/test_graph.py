"""Dependency graph, cycle detection, derived done-ness and the parent cascade."""

from datetime import date
from pathlib import Path

import pytest

from primer_mcp.errors import GateError
from primer_mcp.graph import (
    children_of,
    dependency_graph,
    derive_status,
    find_cycle,
    find_path,
    load_tickets,
    recompute_parents,
    sort_key,
)
from primer_mcp.models import Adr, Epic, Spike, Story, Task, Ticket
from primer_mcp.project import SUBDIR_FOR_TYPE, init_project
from primer_mcp.storage import dumps_ticket

TODAY = date(2026, 1, 1)


def write(primer: Path, ticket: Ticket, body: str = "## Body\ntext") -> Ticket:
    path = primer / SUBDIR_FOR_TYPE[ticket.type] / f"{ticket.id}.md"
    path.write_text(dumps_ticket(ticket, body), encoding="utf-8")
    return ticket


def epic(id: str = "EP-001", **kw: object) -> Epic:
    return Epic(id=id, title=id, created=TODAY, updated=TODAY, **kw)  # type: ignore[arg-type]


def story(id: str, epic_id: str = "EP-001", **kw: object) -> Story:
    return Story(id=id, title=id, created=TODAY, updated=TODAY, epic_id=epic_id, **kw)  # type: ignore[arg-type]


def task(id: str, story_id: str = "ST-001", **kw: object) -> Task:
    return Task(
        id=id,
        title=id,
        created=TODAY,
        updated=TODAY,
        story_id=story_id,
        testable_outcome="it works",
        **kw,  # type: ignore[arg-type]
    )


def spike(id: str, story_id: str = "ST-001", **kw: object) -> Spike:
    return Spike(
        id=id,
        title=id,
        created=TODAY,
        updated=TODAY,
        story_id=story_id,
        question="?",
        timebox="1h",
        **kw,  # type: ignore[arg-type]
    )


def adr(id: str = "ADR-001", epic_id: str = "EP-001") -> Adr:
    return Adr(
        id=id,
        title=id,
        created=TODAY,
        updated=TODAY,
        epic_id=epic_id,
        context="c",
        decision="d",
        consequences="q",
    )


@pytest.fixture
def primer(tmp_path: Path) -> Path:
    init_project(tmp_path, "demo")
    return tmp_path / "primer"


class TestSortKey:
    def test_orders_numerically_not_lexically(self) -> None:
        # Plain string sort gets both of these wrong: "TK-010" < "TK-002" is
        # False but "TK-1000" < "TK-999" is True. next_id supports IDs past 999.
        assert sorted(["TK-010", "TK-002"], key=sort_key) == ["TK-002", "TK-010"]
        assert sorted(["TK-1000", "TK-999"], key=sort_key) == ["TK-999", "TK-1000"]

    def test_groups_by_prefix(self) -> None:
        ids = ["TK-001", "EP-001", "ST-002", "ST-001"]
        assert sorted(ids, key=sort_key) == ["EP-001", "ST-001", "ST-002", "TK-001"]


class TestLoadTickets:
    def test_loads_every_type_keyed_by_id(self, primer: Path) -> None:
        write(primer, epic())
        write(primer, adr())
        write(primer, story("ST-001"))
        write(primer, task("TK-001"))
        write(primer, spike("SP-001"))
        tickets = load_tickets(primer)
        assert set(tickets) == {"EP-001", "ADR-001", "ST-001", "TK-001", "SP-001"}

    def test_empty_store_is_not_an_error(self, primer: Path) -> None:
        assert load_tickets(primer) == {}

    def test_invalid_file_names_the_path(self, primer: Path) -> None:
        bad = primer / "tasks" / "TK-001.md"
        bad.write_text("---\nid: TK-001\ntype: task\n---\n", encoding="utf-8")
        with pytest.raises(GateError) as exc:
            load_tickets(primer)
        # The agent needs to know which file to fix, not just that one is broken.
        assert "TK-001.md" in str(exc.value)


class TestFindPath:
    def test_resolves_id_to_file_by_prefix(self, primer: Path) -> None:
        write(primer, task("TK-007"))
        assert find_path(primer, "TK-007") == primer / "tasks" / "TK-007.md"

    def test_missing_ticket_is_a_gate_error(self, primer: Path) -> None:
        with pytest.raises(GateError, match="TK-007"):
            find_path(primer, "TK-007")

    def test_unrecognised_prefix_lists_the_valid_ones(self, primer: Path) -> None:
        with pytest.raises(GateError) as exc:
            find_path(primer, "XX-001")
        assert "TK-" in str(exc.value)


class TestDependencyGraph:
    def test_blocked_by_becomes_a_blocker_to_blocked_edge(self, primer: Path) -> None:
        write(primer, story("ST-001"))
        write(primer, task("TK-001"))
        write(primer, task("TK-002", blocked_by=["TK-001"]))
        graph = dependency_graph(load_tickets(primer))
        assert graph.has_edge("TK-001", "TK-002")
        assert not graph.has_edge("TK-002", "TK-001")

    def test_reverse_direction_is_a_successor_lookup(self, primer: Path) -> None:
        # TK-001 stores nothing about blocking TK-002 — the removal of the
        # `blocks` field is invisible because the graph answers it.
        write(primer, story("ST-001"))
        write(primer, task("TK-001"))
        write(primer, task("TK-002", blocked_by=["TK-001"]))
        graph = dependency_graph(load_tickets(primer))
        assert list(graph.successors("TK-001")) == ["TK-002"]

    def test_hierarchy_is_not_an_edge(self, primer: Path) -> None:
        # Only dependency edges belong here; parent/child is a plain lookup.
        write(primer, epic())
        write(primer, story("ST-001"))
        write(primer, task("TK-001"))
        assert dependency_graph(load_tickets(primer)).number_of_edges() == 0


class TestFindCycle:
    def test_no_cycle_returns_none(self, primer: Path) -> None:
        write(primer, story("ST-001"))
        write(primer, task("TK-001"))
        write(primer, task("TK-002", blocked_by=["TK-001"]))
        assert find_cycle(dependency_graph(load_tickets(primer))) is None

    def test_two_ticket_cycle_detected(self, primer: Path) -> None:
        write(primer, story("ST-001"))
        write(primer, task("TK-001", blocked_by=["TK-002"]))
        write(primer, task("TK-002", blocked_by=["TK-001"]))
        cycle = find_cycle(dependency_graph(load_tickets(primer)))
        assert cycle is not None
        assert set(cycle) == {"TK-001", "TK-002"}

    def test_self_edge_is_a_cycle(self, primer: Path) -> None:
        write(primer, story("ST-001"))
        write(primer, task("TK-001", blocked_by=["TK-001"]))
        assert find_cycle(dependency_graph(load_tickets(primer))) == ["TK-001"]

    def test_child_story_blocking_its_parent_epic_is_not_a_cycle(self, primer: Path) -> None:
        # The whole reason hierarchy edges are excluded: this is a cycle in the
        # combined graph but semantically fine (docs/architecture.md).
        write(primer, epic())
        write(primer, story("ST-001", blocked_by=["EP-001"]))
        write(primer, epic("EP-002", blocked_by=["ST-001"]))
        assert find_cycle(dependency_graph(load_tickets(primer))) is None


class TestChildrenOf:
    def test_story_children_are_tasks_and_spikes(self, primer: Path) -> None:
        write(primer, story("ST-001"))
        write(primer, task("TK-001"))
        write(primer, spike("SP-001"))
        assert [c.id for c in children_of(load_tickets(primer), "ST-001")] == [
            "SP-001",
            "TK-001",
        ]

    def test_adrs_are_not_epic_children(self, primer: Path) -> None:
        # ADRs are born `done`, so counting them would let an epic with one ADR
        # and no stories derive to done.
        write(primer, epic())
        write(primer, adr())
        assert children_of(load_tickets(primer), "EP-001") == []


class TestDeriveStatus:
    def test_story_done_when_tasks_verified_and_spikes_done(self, primer: Path) -> None:
        write(primer, story("ST-001"))
        write(primer, task("TK-001", status="verified"))
        write(primer, spike("SP-001", status="done"))
        assert derive_status(load_tickets(primer), "ST-001") == "done"

    def test_story_not_done_while_one_task_is_only_completed(self, primer: Path) -> None:
        # `completed` is the intermediate half of the two-phase gate.
        write(primer, story("ST-001"))
        write(primer, task("TK-001", status="verified"))
        write(primer, task("TK-002", status="completed"))
        assert derive_status(load_tickets(primer), "ST-001") is None

    def test_childless_story_is_not_vacuously_done(self, primer: Path) -> None:
        write(primer, story("ST-001"))
        assert derive_status(load_tickets(primer), "ST-001") is None

    def test_storyless_epic_is_not_vacuously_done(self, primer: Path) -> None:
        write(primer, epic())
        assert derive_status(load_tickets(primer), "EP-001") is None

    def test_epic_done_when_all_stories_done(self, primer: Path) -> None:
        write(primer, epic())
        write(primer, story("ST-001", status="done"))
        write(primer, story("ST-002", status="done"))
        assert derive_status(load_tickets(primer), "EP-001") == "done"

    def test_epic_with_one_open_story_is_not_done(self, primer: Path) -> None:
        write(primer, epic())
        write(primer, story("ST-001", status="done"))
        write(primer, story("ST-002", status="todo"))
        assert derive_status(load_tickets(primer), "EP-001") is None

    def test_spike_only_story_is_done_when_the_spike_closes(self, primer: Path) -> None:
        write(primer, story("ST-001"))
        write(primer, spike("SP-001", status="done"))
        assert derive_status(load_tickets(primer), "ST-001") == "done"

    def test_task_status_is_never_derived(self, primer: Path) -> None:
        write(primer, task("TK-001"))
        assert derive_status(load_tickets(primer), "TK-001") is None


class TestRecomputeParents:
    def test_last_verified_task_marks_story_and_epic_done(self, primer: Path) -> None:
        write(primer, epic())
        write(primer, story("ST-001"))
        write(primer, task("TK-001", status="verified"))
        recompute_parents(primer, "TK-001")
        tickets = load_tickets(primer)
        assert tickets["ST-001"].status == "done"
        assert tickets["EP-001"].status == "done"

    def test_new_child_reverts_a_done_story_and_epic(self, primer: Path) -> None:
        write(primer, epic(status="done"))
        write(primer, story("ST-001", status="done"))
        write(primer, task("TK-001", status="verified"))
        write(primer, task("TK-002", status="todo"))
        recompute_parents(primer, "TK-002")
        tickets = load_tickets(primer)
        assert tickets["ST-001"].status == "in-progress"
        assert tickets["EP-001"].status == "in-progress"

    def test_derived_done_overwrites_blocked(self, primer: Path) -> None:
        # `blocked` means "cannot proceed"; with every child finished there is
        # nothing left to proceed with, so the flag would strand the story.
        write(primer, epic())
        write(primer, story("ST-001", status="blocked"))
        write(primer, task("TK-001", status="verified"))
        recompute_parents(primer, "TK-001")
        assert load_tickets(primer)["ST-001"].status == "done"

    def test_blocked_story_with_unfinished_children_keeps_blocked(self, primer: Path) -> None:
        write(primer, epic())
        write(primer, story("ST-001", status="blocked"))
        write(primer, task("TK-001", status="todo"))
        recompute_parents(primer, "TK-001")
        assert load_tickets(primer)["ST-001"].status == "blocked"

    def test_reports_each_file_it_changed(self, primer: Path) -> None:
        write(primer, epic())
        write(primer, story("ST-001"))
        write(primer, task("TK-001", status="verified"))
        changed = recompute_parents(primer, "TK-001")
        assert len(changed) == 2
        assert "ST-001" in changed[0] and "EP-001" in changed[1]

    def test_no_change_writes_nothing(self, primer: Path) -> None:
        write(primer, epic())
        write(primer, story("ST-001"))
        write(primer, task("TK-001", status="todo"))
        before = (primer / "stories" / "ST-001.md").read_text()
        assert recompute_parents(primer, "TK-001") == []
        assert (primer / "stories" / "ST-001.md").read_text() == before

    def test_body_survives_the_status_rewrite(self, primer: Path) -> None:
        write(primer, epic())
        write(primer, story("ST-001"), body="## What\nsomething specific")
        write(primer, task("TK-001", status="verified"))
        recompute_parents(primer, "TK-001")
        assert "something specific" in (primer / "stories" / "ST-001.md").read_text()
