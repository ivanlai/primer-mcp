"""
export_graph: self-contained HTML output with correct nodes, edges, and detail.
"""

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from primer_mcp.export import STATUS_BORDER, TYPE_COLOUR, export_graph
from primer_mcp.models import Adr, Epic, Story, Task, Ticket
from primer_mcp.project import SUBDIR_FOR_TYPE, init_project
from primer_mcp.storage import dumps_ticket

TODAY = date(2026, 1, 1)


def write(project: Path, ticket: Ticket, body: str = "## Body\ntext") -> Ticket:
    path = project / "primer" / SUBDIR_FOR_TYPE[ticket.type] / f"{ticket.id}.md"
    path.write_text(dumps_ticket(ticket, body), encoding="utf-8")
    return ticket


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    init_project(tmp_path, "demo")
    write(
        tmp_path,
        Epic(id="EP-001", title="The Epic", created=TODAY, updated=TODAY),
    )
    write(
        tmp_path,
        Adr(
            id="ADR-001",
            title="Use vis.js",
            created=TODAY,
            updated=TODAY,
            epic_id="EP-001",
            context="need a graph",
            decision="vis.js",
            alternatives=["d3"],
            consequences="vendored JS",
        ),
    )
    write(
        tmp_path,
        Story(id="ST-001", title="The Story", created=TODAY, updated=TODAY, epic_id="EP-001"),
    )
    write(
        tmp_path,
        Task(
            id="TK-001",
            title="The Task",
            created=TODAY,
            updated=TODAY,
            story_id="ST-001",
            testable_outcome="it works",
            status="in-progress",
        ),
    )
    return tmp_path


class TestHtmlOutput:
    def test_produces_valid_html(self, project: Path) -> None:
        result = export_graph(project)
        assert result[0].startswith("Exported graph to")
        html = (project / "primer" / "graph.html").read_text()
        assert "<html" in html
        assert "</html>" in html
        assert "vis.Network" in html

    def test_no_external_requests(self, project: Path) -> None:
        export_graph(project)
        html = (project / "primer" / "graph.html").read_text()
        assert not re.findall(r'<script[^>]+src=["\']', html)
        assert not re.findall(r'<link[^>]+href=["\']', html)

    def test_default_output_path(self, project: Path) -> None:
        result = export_graph(project)
        expected = project / "primer" / "graph.html"
        assert str(expected) in result[0]
        assert expected.is_file()

    def test_custom_output_path(self, project: Path, tmp_path: Path) -> None:
        custom = tmp_path / "out" / "my_graph.html"
        result = export_graph(project, output_path=custom)
        assert str(custom) in result[0]
        assert custom.is_file()
        assert "vis.Network" in custom.read_text()


class TestNodeData:
    def _nodes(self, project: Path) -> list[dict[str, Any]]:
        export_graph(project)
        html = (project / "primer" / "graph.html").read_text()
        match = re.search(r"var nodeData = (\[.*?\]);\s*var edgeData", html, re.DOTALL)
        assert match, "nodeData not found in HTML"
        return json.loads(match.group(1))  # type: ignore[no-any-return]

    def test_all_tickets_present(self, project: Path) -> None:
        nodes = self._nodes(project)
        ids = {n["id"] for n in nodes}
        assert ids == {"EP-001", "ADR-001", "ST-001", "TK-001"}

    def test_type_colours(self, project: Path) -> None:
        nodes = self._nodes(project)
        by_id = {n["id"]: n for n in nodes}
        assert by_id["EP-001"]["color"]["background"] == TYPE_COLOUR["epic"]
        assert by_id["ST-001"]["color"]["background"] == TYPE_COLOUR["story"]
        assert by_id["TK-001"]["color"]["background"] == TYPE_COLOUR["task"]
        assert by_id["ADR-001"]["color"]["background"] == TYPE_COLOUR["adr"]

    def test_status_borders(self, project: Path) -> None:
        nodes = self._nodes(project)
        by_id = {n["id"]: n for n in nodes}
        assert by_id["EP-001"]["color"]["border"] == STATUS_BORDER["todo"]
        assert by_id["TK-001"]["color"]["border"] == STATUS_BORDER["in-progress"]
        assert by_id["ADR-001"]["color"]["border"] == STATUS_BORDER["done"]


class TestEdgeData:
    def _edges(self, project: Path) -> list[dict[str, Any]]:
        export_graph(project)
        html = (project / "primer" / "graph.html").read_text()
        match = re.search(r"var edgeData = (\[.*?\]);\s*var details", html, re.DOTALL)
        assert match, "edgeData not found in HTML"
        return json.loads(match.group(1))  # type: ignore[no-any-return]

    def test_hierarchy_edges(self, project: Path) -> None:
        edges = self._edges(project)
        hierarchy = [e for e in edges if not e["dashes"]]
        pairs = {(e["from"], e["to"]) for e in hierarchy}
        assert ("EP-001", "ADR-001") in pairs
        assert ("EP-001", "ST-001") in pairs
        assert ("ST-001", "TK-001") in pairs

    def test_hierarchy_edges_are_solid_grey(self, project: Path) -> None:
        edges = self._edges(project)
        hierarchy = [e for e in edges if not e["dashes"]]
        assert all(e["color"]["color"] == "#888888" for e in hierarchy)

    def test_dependency_edges(self, project: Path) -> None:
        write(
            project,
            Task(
                id="TK-002",
                title="Blocked task",
                created=TODAY,
                updated=TODAY,
                story_id="ST-001",
                testable_outcome="it works",
                blocked_by=["TK-001"],
            ),
        )
        edges = self._edges(project)
        dep = [e for e in edges if e["dashes"]]
        assert len(dep) == 1
        assert dep[0]["from"] == "TK-001"
        assert dep[0]["to"] == "TK-002"

    def test_dependency_edges_are_dashed_red(self, project: Path) -> None:
        write(
            project,
            Task(
                id="TK-002",
                title="Blocked task",
                created=TODAY,
                updated=TODAY,
                story_id="ST-001",
                testable_outcome="it works",
                blocked_by=["TK-001"],
            ),
        )
        edges = self._edges(project)
        dep = [e for e in edges if e["dashes"]]
        assert dep[0]["color"]["color"] == "#E74C3C"


class TestDetailData:
    def _details(self, project: Path) -> dict[str, dict[str, Any]]:
        export_graph(project)
        html = (project / "primer" / "graph.html").read_text()
        match = re.search(r"var details = (\{.*?\});\s*\nvar nodes", html, re.DOTALL)
        assert match, "details not found in HTML"
        return json.loads(match.group(1))  # type: ignore[no-any-return]

    def test_detail_fields(self, project: Path) -> None:
        details = self._details(project)
        d = details["TK-001"]
        assert d["title"] == "The Task"
        assert d["type"] == "task"
        assert d["status"] == "in-progress"
        assert d["parent"] == "ST-001"

    def test_blocks_derived(self, project: Path) -> None:
        write(
            project,
            Task(
                id="TK-002",
                title="Blocked",
                created=TODAY,
                updated=TODAY,
                story_id="ST-001",
                testable_outcome="it works",
                blocked_by=["TK-001"],
            ),
        )
        details = self._details(project)
        assert "TK-002" in details["TK-001"]["blocks"]
        assert details["TK-002"]["blocked_by"] == ["TK-001"]

    def test_body_included(self, project: Path) -> None:
        details = self._details(project)
        assert "Body" in details["EP-001"]["body"]


class TestScriptEscaping:
    def test_script_closing_tag_in_body_is_escaped(self, tmp_path: Path) -> None:
        """A ticket body containing </script> must not break the HTML."""
        init_project(tmp_path, "demo")
        write(
            tmp_path,
            Epic(id="EP-001", title="Epic", created=TODAY, updated=TODAY),
        )
        write(
            tmp_path,
            Story(id="ST-001", title="Story", created=TODAY, updated=TODAY, epic_id="EP-001"),
        )
        write(
            tmp_path,
            Task(
                id="TK-001",
                title="Task with script tag",
                created=TODAY,
                updated=TODAY,
                story_id="ST-001",
                testable_outcome="it works",
            ),
            body="## Body\nsome html </script><h1>injected</h1>",
        )
        export_graph(tmp_path)
        html = (tmp_path / "primer" / "graph.html").read_text()

        # The only raw </script> tags should be the template's own closing tags.
        # Count them: the template has exactly 2 (vis.js script + app script).
        raw_count = html.count("</script>")
        assert raw_count == 2, f"Expected 2 template </script> tags, found {raw_count}"

        # The escaped form must appear in the embedded JSON.
        assert r"<\/script>" in html


class TestEmptyStore:
    def test_no_tickets(self, tmp_path: Path) -> None:
        init_project(tmp_path, "empty")
        result = export_graph(tmp_path)
        assert "Nothing to export" in result[0]
        assert not (tmp_path / "primer" / "graph.html").exists()
