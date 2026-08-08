# primer-mcp — Architecture Document

## Key Decisions

| Decision | Choice | Alternatives considered | Rationale |
|----------|--------|------------------------|-----------|
| Language | Python | TypeScript | User expertise; `uvx` solves distribution equally well |
| Data store | Markdown + YAML frontmatter | SQLite, JSON files | Human-readable, git-native, no vendor lock-in, editable without the tool |
| Distribution | `uvx primer-mcp` | `pip install`, Docker | Zero-install; uv manages the virtual environment automatically |
| Schema validation | Pydantic | dataclasses, marshmallow | Best-in-class validation with clear error messages; widely understood |
| Frontmatter parsing | `python-frontmatter` | PyYAML + manual parsing | Handles markdown body + YAML metadata cleanly in one library |
| Graph library | `networkx` | custom adjacency list, igraph | Standard, well-documented; fits the dependency graph use case naturally |
| Graph visualisation | vis.js embedded in single HTML | D3.js, Cytoscape.js, React | Neo4j-style rendering out of the box; zero server or build step needed |
| CLAUDE.md strategy | Append via `init_project` | Overwrite, manual only | Non-destructive; idempotent; user stays in full control of their file |
| MCP primitives | Tools + Prompts | Tools only | Prompts scaffold planning conversations and work across all MCP clients |
| Plan mode | Cannot trigger programmatically | N/A | Client-side Claude Code feature; addressed via CLAUDE.md rules and tool descriptions |

## Storage Layout

All primer-mcp data lives in a `.primer/` directory within the user's project:

```
{project_dir}/
└── .primer/
    ├── config.yaml          # project id prefix (e.g. "PROJ"), created by init_project
    ├── epics/
    │   └── EP-001.md
    ├── adrs/
    │   └── ADR-001.md
    ├── stories/
    │   └── ST-001.md
    ├── tasks/
    │   └── TK-001.md
    └── spikes/
        └── SP-001.md
```

## Ticket Schema

All ticket types share a common frontmatter base. Type-specific fields are additive.

```yaml
# Common fields (all types) — including graph edges
id: EP-001
type: epic | adr | story | task | spike
title: string
status: todo | in-progress | done | blocked
created: ISO8601 date
updated: ISO8601 date
blocks: []        # list of ticket IDs this ticket blocks (any type)
blocked_by: []    # list of ticket IDs blocking this ticket (any type)

# Epic-specific
goals: []
constraints: []
non_goals: []
success_criteria: []

# ADR-specific
epic_id: EP-001
context: string
decision: string
alternatives: []
consequences: string

# Story-specific
epic_id: EP-001
acceptance_criteria: []
definition_of_done: []

# Task-specific
story_id: ST-001
testable_outcome: string
completed_notes: string
verified_evidence: string   # populated by verify_task

# Spike-specific
story_id: ST-001
question: string
timebox: string             # e.g. "2 hours"
findings: string
```

## Graph Protocol

Graph edges are first-class citizens — every ticket type participates in the graph. There are two distinct edge types:

**Hierarchy edges** (implicit, derived from parent ID fields):
- `epic_id` on ADR → Epic is parent of ADR
- `epic_id` on Story → Epic is parent of Story
- `story_id` on Task/Spike → Story is parent of Task/Spike

**Dependency edges** (explicit, stored in frontmatter):
- `blocks: [TK-002, ST-003]` — this ticket must be done before those tickets
- `blocked_by: [EP-001]` — this ticket cannot start until those tickets are done

Both edge types are loaded into a `networkx.DiGraph` at query time. This graph is the source of truth for:
- `get_next_action` — finds unblocked, ready tickets
- `export_graph` — renders the full project as a neo4j-style interactive HTML graph
- Cycle detection — `networkx` detects circular dependencies on graph load

IDs are globally unique across all ticket types (EP-, ADR-, ST-, TK-, SP- prefixes), so any ticket can reference any other ticket in `blocks`/`blocked_by`.

## Workflow Gates

Enforced by the MCP server — these are hard blocks, not warnings:

1. Cannot call `record_adr` without a valid `epic_id`
2. Cannot call `create_story` unless the parent epic has at least one ADR
3. Cannot call `create_task` without a valid `story_id`
4. Cannot call `verify_task` unless `complete_task` has been called first
5. `get_next_action` surfaces the first unmet gate in the project

## MCP Primitives Used

### Tools
All state-changing operations and queries. See `docs/epic-001.md` for the full list.

### Prompts
`plan_story` — a reusable conversation template that scaffolds the planning phase before a story is created. Works across all MCP clients, including those without a native plan mode.

### Resources
Not used in v1. Future: expose ticket files as readable resources for richer client integrations.

## Provider Agnosticism

The server contains no provider-specific SDK calls. It speaks only the MCP protocol. Claude Code is referenced in documentation and README examples only — any MCP-compatible client works identically.
