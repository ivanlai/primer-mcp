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
| Python version | Dev pinned to 3.13 (`.python-version`); `requires-python = ">=3.12"`; CI tests 3.12–3.14 | 3.14 floor, 3.11 floor | 3.13 is the mature stable with full ecosystem wheel coverage; `uvx` downloads a suitable interpreter for users, so the floor barely restricts reach; 3.14 in CI proves forward-compat |
| Jira interop | Field-mapping doc + `export_jira` prompt + optional `external_ref` field | Jira REST client in the server | Zero new dependencies; any Jira MCP client does the writing; preserves the no-provider-SDK constraint |
| vis.js delivery | Vendored copy (MIT, ~700KB) bundled in the package | CDN `<script>` tag | "Fully offline" and "no external requests" require it; MIT licence permits redistribution |
| Gate error style | Actionable, agent-steering messages | Plain refusals | The consumer of every error is an AI agent mid-task; the error text is the steering surface |
| Frontmatter strictness | Unknown keys tolerated and round-tripped (`extra="allow"`) | `extra="forbid"`, `extra="ignore"` | Strictness made every field removal a breaking change needing a migration, and let one stale key block a whole store; `ignore` silently deletes what it does not understand. Data gets tolerance, workflow gets gates (ADR-007) |
| Hand-editing | Allowed for anything except a status the workflow owns | Tools-only authoring | The store is markdown in the user's own git repo, and "editable without the tool" is why that format was chosen. Claiming exclusive write access is the lock-in this project avoids (ADR-007) |
| Priority | No priority field; deterministic ordering | `priority` frontmatter field | Single-user, small projects; topological order + oldest-ID-first is predictable and needs no upkeep |

## Storage Layout

All primer-mcp data lives in a `primer/` directory within the user's project — deliberately visible (not dot-hidden) so tickets are browsable on GitHub and in editors. Adopters should commit it (git-native history is a core selling point):

```
{project_dir}/
└── primer/
    ├── config.yaml          # project name, schema version, optional Jira project key
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

All ticket types share a common frontmatter base. Type-specific fields are additive. Unrecognised keys are preserved rather than rejected, so a store stays readable across versions and a field can be removed without breaking every ticket (ADR-007).

```yaml
# Common fields (all types) — including graph edges
id: EP-001
type: epic | adr | story | task | spike
title: string
status: todo | in-progress | blocked | completed | verified | done
                  # allowed values vary by type — see Ticket Lifecycle below
created: ISO8601 date
updated: ISO8601 date
blocked_by: []    # list of ticket IDs blocking this ticket (any type)
                  # the only stored edge — "A blocks B" is recorded on B (ADR-004)
external_ref: {}  # optional, e.g. {jira: PROJ-123} — set after export, makes re-export idempotent

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

## Ticket Lifecycle

Any type may be `blocked` at any pre-terminal point. Terminal states per type:

- **Epic / Story:** `todo → in-progress → done`. `done` is derived, never set directly: a story is done when all child tasks are `verified` and all child spikes are `done`; an epic is done when all child stories are done. Derived status is *written to the file* by the tools that change a child, in both directions — finishing the last child settles its parents, adding a new one reopens them (ADR-002). Read tools therefore report stored status and derive nothing. Done requires at least one child, so a childless story is never vacuously done.
- **ADR:** created as `done` — an ADR records a decision already made. It has no active lifecycle.
- **Task:** `todo → in-progress → completed → verified`. `complete_task` sets `completed`; `verify_task` requires status `completed` and sets `verified` (terminal). The intermediate `completed` state is what makes the two-phase gate checkable from state alone.
- **Spike:** `todo → done`. `complete_spike` records findings and sets `done`. There is no `start_spike`, so `in-progress` is unreachable for spikes, and an open spike does not gate the tasks beside it — use `blocked_by` where one genuinely must come first (ADR-006).

`status: blocked` and `blocked_by` are separate mechanisms and `blocked` is never derived (ADR-003). A ticket waiting on another ticket keeps `status: todo` and is simply not offered; readiness is computed from the graph on every call. `blocked` is reserved for blockers with no ticket — waiting on credentials, on a review — which the graph cannot express.

There is no `priority` field. `get_next_action` walks a fixed order and returns on the first match, so the answer is one instruction rather than a list: unmet gates first, scoped to the oldest epic that is not done; task-state gates (`completed` awaiting verification, then `in-progress`) before creation gates; ready work before planning more work; then the blockers, named. The last two orderings were decisions rather than accidents — see ADR-001.

## Ticket Body Templates

Frontmatter carries machine-readable data for the graph and gating logic. The markdown body carries human-readable context so each file is self-contained and readable in isolation.

### Epic body
```markdown
## Why
[Problem being solved and motivation]

## Goals
[Restate goals narratively]

## Constraints
[Key constraints and boundaries]

## Non-Goals
[What this explicitly does not cover]

## Success Criteria
[How we know this is done]

## Child ADRs
- [[ADR-001]] — [title]

## Child Stories
- [[ST-001]] — [title]
```

### ADR body
```markdown
## Parent Epic
[[EP-001]] — [epic title]

## Context
[Why this decision is needed — the situation, problem, or constraint forcing a choice]

## Decision
[What was decided, stated clearly]

## Alternatives Considered
- **[Option A]** — [why rejected]
- **[Option B]** — [why rejected]

## Consequences
[Trade-offs accepted, risks introduced, follow-up actions needed]
```

### Story body
```markdown
## Parent Epic
[[EP-001]] — [epic title]

## What
[User story or description of the deliverable]

## Acceptance Criteria
- [ ] [criterion]

## Definition of Done
- [ ] [criterion]

## Dependencies
- Blocked by: [[TK-001]] — [title] — [why it blocks]
- Blocks: [[ST-003]] — [title] — [why]
```

### Task body
```markdown
## Parent Story
[[ST-001]] — [story title]

## What to do
[Specific implementation description]

## Testable Outcome
[Exact condition that proves this task is complete]

## Dependencies
- Blocked by: [[TK-002]] — [title] — [why]
- Blocks: [[TK-004]] — [title] — [why]

## Completion Notes
[Populated by complete_task]

## Verification Evidence
[Populated by verify_task — test output, command run, screenshot reference]
```

### Spike body
```markdown
## Parent Story
[[ST-001]] — [story title]

## Question
[The specific unknown this spike is investigating]

## Timebox
[e.g. 2 hours]

## Findings
[Populated when spike is complete — answer to the question, recommendation]
```

## Graph Protocol

Graph edges are first-class citizens — every ticket type participates in the graph. There are two distinct edge types:

**Hierarchy edges** (implicit, derived from parent ID fields):
- `epic_id` on ADR → Epic is parent of ADR
- `epic_id` on Story → Epic is parent of Story
- `story_id` on Task/Spike → Story is parent of Task/Spike

**Dependency edges** (explicit, stored in frontmatter):
- `blocked_by: [EP-001]` — this ticket cannot start until those tickets are done

`blocked_by` is the only stored edge. "A blocks B" and "B is blocked by A" are one directed edge stated from two ends, so storing both invites a disagreement nothing can resolve; the reverse direction is a graph lookup at read time, which `get_ticket` reports (ADR-004).

Both edge types are loaded into a `networkx.DiGraph` at query time (edge type stored as an edge attribute). This graph is the source of truth for:
- `get_next_action` — finds unblocked, ready tickets
- `export_graph` — renders the full project as a neo4j-style interactive HTML graph
- Cycle detection — `networkx` detects circular dependencies on graph load

Cycle detection runs on **dependency edges only**. A child story blocking its parent epic forms a cycle in the combined graph but is semantically fine — hierarchy edges are excluded from the check.

IDs are globally unique across all ticket types (EP-, ADR-, ST-, TK-, SP- prefixes), so any ticket can reference any other ticket in `blocked_by`.

## Workflow Gates

Enforced by the MCP server — these are hard blocks, not warnings:

1. Cannot call `record_adr` without a valid `epic_id`
2. Cannot call `create_story` unless the parent epic has at least one ADR
3. Cannot call `create_task` without a valid `story_id`
4. Cannot call `verify_task` unless `complete_task` has been called first (task status must be `completed`)
5. `get_next_action` surfaces the first unmet gate in the project

## Gate Errors Are Agent Steering

The consumer of every error message is an AI agent mid-task, so a gate failure must contain the corrective action, not just the refusal. Every gate error follows the pattern: **what failed → why → the exact next call**. Example:

> `Cannot create story: epic EP-001 has no ADRs. Record at least one architectural decision first: record_adr(epic_id="EP-001", ...)`

Tool descriptions follow the same principle — they are the primary steering surface for agents choosing which tool to call, and are written and reviewed deliberately (see ST-011).

## Graduating to Jira

primer-mcp is for people who dislike Jira — but sometimes the team still needs real Jira tickets. The escape hatch is protocol composition, not a Jira dependency: tickets are self-contained markdown, so any agent that also has a Jira MCP server (e.g. Atlassian's) can read primer-mcp tickets and file the corresponding issues. primer-mcp contributes three things:

1. The field mapping below, so the export is mechanical
2. An `export_jira` MCP Prompt that scaffolds the export conversation
3. The optional `external_ref` frontmatter field — the agent records the created issue key there, so re-running the export updates instead of duplicating

| primer-mcp | Jira |
|------------|------|
| Epic | Epic |
| Story | Story |
| Task | Task (or Sub-task of the story) |
| Spike | Spike (or Task labelled `spike`) |
| ADR | No native equivalent — Confluence page or issue labelled `adr`, linked to the Epic |
| `title` | Summary |
| markdown body | Description |
| `acceptance_criteria` | Description checklist (or AC custom field if configured) |
| `blocked_by` | Native issue links "blocks" / "is blocked by" — one stored edge emits both directions |
| `status` | `todo` → To Do, `in-progress` → In Progress, `completed`/`verified`/`done` → Done, `blocked` → flagged |

Jira workflows vary per instance; the `export_jira` prompt instructs the agent to map each status to the nearest available column rather than assuming these exact names.

## MCP Primitives Used

### Tools
All state-changing operations and queries, including read access (`get_ticket`, `list_tickets`) and post-creation edits (`update_ticket`) — agents on clients without filesystem access must be able to work entirely through the server. See `docs/epic-001.md` for the full list.

### Prompts
- `plan_story` — a reusable conversation template that scaffolds the planning phase before a story is created. Works across all MCP clients, including those without a native plan mode.
- `export_jira` — scaffolds the export of primer-mcp tickets to Jira via whatever Jira MCP server the client has available (see "Graduating to Jira").
- `import_jira` — scaffolds importing a Jira epic and its children into primer-mcp via the client's Jira MCP server, creating tickets in gate order and recording Jira keys in `external_ref`.

### Resources
Not used in v1. Future: expose ticket files as readable resources for richer client integrations.

## Provider Agnosticism

The server contains no provider-specific SDK calls. It speaks only the MCP protocol. Claude Code is referenced in documentation and README examples only — any MCP-compatible client works identically.
