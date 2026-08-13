"""
Generate a self-contained HTML file visualising the project graph.

Nodes are coloured by ticket type (fill) and status (border). Edges show
both hierarchy (solid) and dependency (dashed). vis.js is vendored inline
so the file opens offline with no external requests.
"""

from __future__ import annotations

import importlib.resources
import json
from pathlib import Path

from primer_mcp.graph import dependency_graph, load_tickets
from primer_mcp.models import Adr, Spike, Story, Task, Ticket
from primer_mcp.project import require_store
from primer_mcp.storage import loads_ticket

TYPE_COLOUR = {
    "epic": "#4A90D9",
    "adr": "#9B59B6",
    "story": "#E67E22",
    "task": "#E84393",
    "spike": "#B53471",
}

STATUS_BORDER = {
    "todo": "#95A5A6",
    "in-progress": "#F1C40F",
    "blocked": "#E74C3C",
    "completed": "#82E0AA",
    "done": "#2ECC71",
    "verified": "#1A9A5B",
}


def _safe_json(obj: object) -> str:
    """Serialize *obj* as JSON, escaping sequences that would break inline <script>."""
    return json.dumps(obj).replace("</", "<\\/")


def _parent_id(ticket: Ticket) -> str | None:
    if isinstance(ticket, Adr | Story):
        return ticket.epic_id
    if isinstance(ticket, Task | Spike):
        return ticket.story_id
    return None


def _node(ticket: Ticket) -> dict[str, object]:
    return {
        "id": ticket.id,
        "label": ticket.id,
        "title": f"{ticket.id}: {ticket.title}",
        "color": {
            "background": TYPE_COLOUR[ticket.type],
            "border": STATUS_BORDER.get(ticket.status, "#95A5A6"),
        },
        "borderWidth": 6,
        "shape": "circle",
        "font": {"color": "#FFFFFF", "size": 11},
    }


def _detail(ticket: Ticket, body: str, blocks: list[str]) -> dict[str, object]:
    parent = _parent_id(ticket)
    return {
        "id": ticket.id,
        "title": ticket.title,
        "type": ticket.type,
        "status": ticket.status,
        "parent": parent,
        "blocked_by": ticket.blocked_by,
        "blocks": blocks,
        "body": body,
    }


def _build_graph_data(
    tickets: dict[str, Ticket],
    bodies: dict[str, str],
    blocks_map: dict[str, list[str]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, dict[str, object]]]:
    nodes = []
    edges = []
    details: dict[str, dict[str, object]] = {}

    for ticket in tickets.values():
        nodes.append(_node(ticket))
        details[ticket.id] = _detail(
            ticket, bodies.get(ticket.id, ""), blocks_map.get(ticket.id, [])
        )

        parent = _parent_id(ticket)
        if parent and parent in tickets:
            edges.append(
                {
                    "from": parent,
                    "to": ticket.id,
                    "color": {"color": "#888888"},
                    "arrows": "to",
                    "dashes": False,
                }
            )

        for blocker in ticket.blocked_by:
            if blocker in tickets:
                edges.append(
                    {
                        "from": blocker,
                        "to": ticket.id,
                        "color": {"color": "#E74C3C"},
                        "arrows": "to",
                        "dashes": True,
                    }
                )

        if isinstance(ticket, Story):
            for adr_id in ticket.adr_ids:
                if adr_id in tickets:
                    edges.append(
                        {
                            "from": adr_id,
                            "to": ticket.id,
                            "color": {"color": "#9B59B6"},
                            "arrows": "to",
                            "dashes": [5, 5],
                        }
                    )

    return nodes, edges, details


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>primer-mcp project graph</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       display: flex; height: 100vh; background: #1a1a2e; color: #e0e0e0; }}
#graph {{ flex: 1; }}
#sidebar {{ width: 360px; background: #16213e; border-left: 1px solid #0f3460;
            overflow-y: auto; padding: 20px; display: none; }}
#sidebar.open {{ display: block; }}
#sidebar h2 {{ margin-bottom: 12px; color: #e94560; font-size: 18px; }}
#sidebar .field {{ margin-bottom: 10px; }}
#sidebar .label {{ font-size: 11px; text-transform: uppercase; color: #888;
                   letter-spacing: 0.5px; }}
#sidebar .value {{ font-size: 14px; margin-top: 2px; }}
#sidebar .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px;
                   font-size: 12px; font-weight: 600; }}
#sidebar .body {{ margin-top: 16px; padding-top: 16px; border-top: 1px solid #0f3460;
                  white-space: pre-wrap; font-size: 13px; line-height: 1.5;
                  color: #ccc; }}
#sidebar .close {{ position: absolute; top: 10px; right: 14px; cursor: pointer;
                   font-size: 20px; color: #888; }}
#sidebar .close:hover {{ color: #e94560; }}
#sidebar .edge-list {{ font-size: 13px; }}
#sidebar .edge-list span {{ cursor: pointer; color: #4A90D9; }}
#sidebar .edge-list span:hover {{ text-decoration: underline; }}
#sidebar .focus-btn {{ display: inline-block; margin-top: 8px; padding: 4px 12px;
                       border-radius: 4px; font-size: 12px; font-weight: 600;
                       cursor: pointer; border: 1px solid #0f3460; background: #0f3460;
                       color: #e0e0e0; }}
#sidebar .focus-btn:hover {{ background: #1a3a6e; }}
#sidebar .focus-btn.active {{ background: #e94560; border-color: #e94560; color: #fff; }}
#search {{ position: absolute; top: 16px; left: 16px; z-index: 11; }}
#search input {{ background: rgba(22,33,62,0.92); border: 1px solid #0f3460; color: #e0e0e0;
                 padding: 8px 12px; border-radius: 6px; font-size: 14px; width: 200px;
                 outline: none; }}
#search input::placeholder {{ color: #666; }}
#search input:focus {{ border-color: #4A90D9; }}
#search .dropdown {{ background: rgba(22,33,62,0.96); border: 1px solid #0f3460;
                     border-top: none; border-radius: 0 0 6px 6px; width: 200px;
                     max-height: 240px; overflow-y: auto; display: none; }}
#search .dropdown.open {{ display: block; }}
#search .dropdown .item {{ padding: 6px 12px; cursor: pointer; font-size: 13px;
                           white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
#search .dropdown .item:hover, #search .dropdown .item.active {{ background: #0f3460; }}
#search .dropdown .item .id {{ color: #4A90D9; margin-right: 6px; }}
#legend {{ position: absolute; top: 60px; left: 16px; background: rgba(22,33,62,0.92);
           padding: 16px 20px; border-radius: 8px; font-size: 14px; z-index: 10;
           width: 200px; box-sizing: border-box; }}
#legend .row {{ display: flex; align-items: center; margin-bottom: 4px;
               cursor: pointer; user-select: none; }}
#legend .row:hover {{ opacity: 0.8; }}
#legend .row.off {{ opacity: 0.35; }}
#legend .row.off .swatch {{ background: #555 !important; }}
#legend .swatch {{ width: 18px; height: 18px; border-radius: 4px; margin-right: 10px;
                   display: inline-block; transition: background 0.15s; }}
#legend .line {{ width: 24px; height: 0; border-top: 2px; margin-right: 8px;
                 display: inline-block; }}
</style>
</head>
<body>
<div id="graph"></div>
<div id="search">
  <input type="text" placeholder="Search ticket ID..." oninput="onSearch(this.value)" onkeydown="onSearchKey(event)">
  <div class="dropdown" id="searchDropdown"></div>
</div>
<div id="sidebar">
  <span class="close" onclick="closeSidebar()">&times;</span>
  <div id="detail"></div>
</div>
<div id="legend">
  <div style="font-weight:600;margin-bottom:6px;">Node fill = type</div>
  {legend_types}
  <div style="font-weight:600;margin:8px 0 6px;">Border = status</div>
  {legend_statuses}
  <div style="font-weight:600;margin:8px 0 6px;">Edges</div>
  <div class="row"><span class="line" style="border-style:solid;border-color:#888;"></span> hierarchy</div>
  <div class="row"><span class="line" style="border-style:dashed;border-color:#E74C3C;"></span> dependency</div>
  <div class="row"><span class="line" style="border-style:dotted;border-color:#9B59B6;"></span> ADR informs</div>
</div>
<script>
{vis_js}
</script>
<script>
var nodeData = {nodes_json};
var edgeData = {edges_json};
var details = {details_json};

var nodes = new vis.DataSet(nodeData);
var edges = new vis.DataSet(edgeData);
var container = document.getElementById("graph");
var network = new vis.Network(container, {{nodes: nodes, edges: edges}}, {{
  physics: {{
    solver: "forceAtlas2Based",
    forceAtlas2Based: {{ gravitationalConstant: -60, springLength: 120, damping: 0.4 }},
    stabilization: {{ iterations: 200 }}
  }},
  interaction: {{ hover: true, tooltipDelay: 200 }},
  edges: {{ smooth: {{ type: "continuous" }} }}
}});

function esc(s) {{
  var d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}}

function renderDetail(id) {{
  var d = details[id];
  if (!d) return;
  var h = '<h2>' + esc(d.id) + '</h2>';
  h += '<div class="field"><div class="label">Title</div><div class="value">' + esc(d.title) + '</div></div>';
  h += '<div class="field"><div class="label">Type</div><div class="value"><span class="badge" style="background:' + typeColour(d.type) + '">' + esc(d.type) + '</span></div></div>';
  h += '<div class="field"><div class="label">Status</div><div class="value"><span class="badge" style="background:' + statusColour(d.status) + '">' + esc(d.status) + '</span></div></div>';
  if (d.parent) h += '<div class="field"><div class="label">Parent</div><div class="value edge-list"><span onclick="go(\\''+d.parent+'\\')">'+esc(d.parent)+'</span></div></div>';
  if (d.blocked_by.length) {{
    h += '<div class="field"><div class="label">Blocked by</div><div class="value edge-list">'
      + d.blocked_by.map(function(b){{ return '<span onclick="go(\\''+b+'\\')">'+esc(b)+'</span>'; }}).join(", ") + '</div></div>';
  }}
  if (d.blocks.length) {{
    h += '<div class="field"><div class="label">Blocks</div><div class="value edge-list">'
      + d.blocks.map(function(b){{ return '<span onclick="go(\\''+b+'\\')">'+esc(b)+'</span>'; }}).join(", ") + '</div></div>';
  }}
  h += '<div><span class="focus-btn' + (focusedNode === id ? ' active' : '') + '" onclick="toggleFocus(\\''+id+'\\')">Focus</span> <span style="font-size:11px;color:#888;">Show only connected nodes</span></div>';
  if (d.body) h += '<div class="body">' + esc(d.body) + '</div>';
  document.getElementById("detail").innerHTML = h;
  document.getElementById("sidebar").classList.add("open");
}}

function closeSidebar() {{
  document.getElementById("sidebar").classList.remove("open");
  if (focusedNode) {{ focusedNode = null; applyFilters(); }}
}}

function go(id) {{
  network.selectNodes([id]);
  network.focus(id, {{scale: 1, animation: true}});
  renderDetail(id);
}}

var TYPE_COLOURS = {type_colours_json};
var STATUS_COLOURS = {status_colours_json};
function typeColour(t) {{ return TYPE_COLOURS[t] || "#666"; }}
function statusColour(s) {{ return STATUS_COLOURS[s] || "#666"; }}

var dragged = false;
network.on("dragStart", function() {{ dragged = true; }});
network.on("dragEnd", function() {{
  network.unselectAll();
  setTimeout(function() {{ dragged = false; }}, 50);
}});
network.on("click", function(params) {{
  if (dragged) return;
  if (params.nodes.length === 1) renderDetail(params.nodes[0]);
  else closeSidebar();
}});

var hiddenTypes = {{}};
var hiddenStatuses = {{}};
var focusedNode = null;

function toggleFilter(el) {{
  var kind = el.getAttribute("data-filter");
  var val = el.getAttribute("data-value");
  var store = kind === "type" ? hiddenTypes : hiddenStatuses;
  if (store[val]) {{ delete store[val]; el.classList.remove("off"); }}
  else {{ store[val] = true; el.classList.add("off"); }}
  applyFilters();
}}

var searchIdx = -1;
function onSearch(q) {{
  var dd = document.getElementById("searchDropdown");
  q = q.trim().toUpperCase();
  searchIdx = -1;
  if (!q) {{ dd.classList.remove("open"); dd.innerHTML = ""; network.unselectAll(); return; }}
  var matches = nodeData.filter(function(n) {{
    var d = details[n.id];
    return n.id.toUpperCase().indexOf(q) !== -1 || d.title.toUpperCase().indexOf(q) !== -1;
  }});
  if (!matches.length) {{ dd.classList.remove("open"); dd.innerHTML = ""; network.unselectAll(); return; }}
  dd.innerHTML = matches.map(function(n, i) {{
    var d = details[n.id];
    return '<div class="item" data-id="'+n.id+'" onclick="pickSearch(\\''+n.id+'\\')"><span class="id">'+esc(n.id)+'</span>'+esc(d.title)+'</div>';
  }}).join("");
  var ids = matches.map(function(n) {{ return n.id; }});
  network.selectNodes(ids);
  if (matches.length === 1) {{ pickSearch(ids[0]); return; }}
  dd.classList.add("open");
}}
function onSearchKey(e) {{
  var dd = document.getElementById("searchDropdown");
  var items = dd.querySelectorAll(".item");
  if (!items.length) return;
  if (e.key === "ArrowDown") {{ e.preventDefault(); searchIdx = Math.min(searchIdx + 1, items.length - 1); }}
  else if (e.key === "ArrowUp") {{ e.preventDefault(); searchIdx = Math.max(searchIdx - 1, 0); }}
  else if (e.key === "Enter" && searchIdx >= 0) {{ e.preventDefault(); pickSearch(items[searchIdx].getAttribute("data-id")); return; }}
  else return;
  items.forEach(function(el, i) {{ el.classList.toggle("active", i === searchIdx); }});
  items[searchIdx].scrollIntoView({{block: "nearest"}});
}}
function pickSearch(id) {{
  var dd = document.getElementById("searchDropdown");
  var input = document.querySelector("#search input");
  dd.classList.remove("open");
  input.value = id;
  go(id);
}}

function toggleFocus(id) {{
  if (focusedNode === id) {{
    focusedNode = null;
  }} else {{
    focusedNode = id;
  }}
  renderDetail(id);
  applyFilters();
}}

function applyFilters() {{
  var neighbors = null;
  if (focusedNode) {{
    neighbors = {{}};
    neighbors[focusedNode] = true;
    network.getConnectedNodes(focusedNode).forEach(function(n) {{ neighbors[n] = true; }});
  }}
  var updates = [];
  nodeData.forEach(function(n) {{
    var d = details[n.id];
    var hide = !!hiddenTypes[d.type] || !!hiddenStatuses[d.status];
    if (!hide && neighbors) hide = !neighbors[n.id];
    updates.push({{id: n.id, hidden: hide}});
  }});
  nodes.update(updates);
}}
</script>
</body>
</html>
"""


def _legend_html(mapping: dict[str, str], kind: str) -> str:
    rows = []
    for label, colour in mapping.items():
        rows.append(
            f'<div class="row" data-filter="{kind}" data-value="{label}" '
            f'onclick="toggleFilter(this)">'
            f'<span class="swatch" style="background:{colour};"></span> {label}</div>'
        )
    return "\n  ".join(rows)


def export_graph(project_dir: Path, output_path: Path | None = None) -> list[str]:
    """
    Write a self-contained HTML file visualising the project graph.
    """
    primer = require_store(project_dir)
    tickets = load_tickets(project_dir)

    if not tickets:
        return ["Nothing to export — the store has no tickets."]

    bodies: dict[str, str] = {}
    from primer_mcp.graph import find_path

    for ticket_id in tickets:
        path = find_path(project_dir, ticket_id)
        _, body = loads_ticket(path.read_text(encoding="utf-8"))
        bodies[ticket_id] = body.strip()

    dep_graph = dependency_graph(tickets)
    blocks_map: dict[str, list[str]] = {}
    for ticket_id in tickets:
        if ticket_id in dep_graph:
            successors = sorted(dep_graph.successors(ticket_id))
            if successors:
                blocks_map[ticket_id] = successors

    nodes, edges, details = _build_graph_data(tickets, bodies, blocks_map)

    vis_js = importlib.resources.read_text("primer_mcp.static", "vis-network.min.js")

    html = _HTML_TEMPLATE.format(
        vis_js=vis_js,
        nodes_json=_safe_json(nodes),
        edges_json=_safe_json(edges),
        details_json=_safe_json(details),
        type_colours_json=_safe_json(TYPE_COLOUR),
        status_colours_json=_safe_json(STATUS_BORDER),
        legend_types=_legend_html(TYPE_COLOUR, "type"),
        legend_statuses=_legend_html(STATUS_BORDER, "status"),
    )

    if output_path is None:
        output_path = primer / "graph.html"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return [f"Exported graph to {output_path}"]
