# EP-001 — Build and publish primer-mcp

## Goals
Build a working, published MCP server that enforces planning-first workflows for AI-assisted development. See `docs/planning.md` for full goals, constraints, and success criteria.

## Status of this document

**Historical record only, from ST-007 onward.** The live backlog now lives in
`primer/`, migrated with primer-mcp's own tools. This file remains the record
for ST-001 through ST-006, which were completed before the ticket store existed
and cannot be imported — `done` is derived from child tasks, and there is no
tool to assert a story was already finished.

The store renumbered from `ST-001` on migration, so story numbers in this file
do **not** match the store. The numbers overlap rather than simply offset:

| This document | In `primer/` | Story |
|---|---|---|
| ST-001 – ST-006 | — | completed pre-migration; not in the store |
| ST-007 | `ST-001` | Query and graph tools |
| ST-008 | `ST-002` | `export_graph` — vis.js HTML output |
| ST-009 | `ST-003` | MCP Prompts |
| ST-010 | `ST-004` | Test sweep |
| ST-011 | `ST-005` | README, registry submission |
| ST-012 | `ST-006` | CI pipeline |
| ST-013 | `ST-007` | Portfolio framing |
| ST-014 | `ST-008` | `reopen_task` (added during ST-007 planning) |

Quote store IDs when working; quote this document only for history.

## Stories

### ST-001: Project scaffolding, uv environment, and packaging
Set up the uv-managed Python environment, project structure, `pyproject.toml`, and `uvx` entry point so the server is installable and runnable.
- `uv init` project layout; `.python-version` pinned to 3.13; `requires-python = ">=3.12"` in `pyproject.toml`
- Runtime dependencies: `mcp`, `pydantic`, `python-frontmatter`, `networkx`
- Dev dependency group: `pytest`, `ruff`, `mypy`
- Entry point: `primer_mcp/__main__.py`
- `uv` lockfile committed; MIT `LICENSE` file added
- `uvx primer-mcp --help` runs without errors

### ST-002: Schema and Pydantic models
Define and validate all ticket types as Pydantic models.
- Models for: Epic, ADR, Story, Task, Spike
- Shared base model with common fields, including `blocks`/`blocked_by` and optional `external_ref`
- Per-type status validation matching the Ticket Lifecycle in `docs/architecture.md` (tasks: `todo | in-progress | blocked | completed | verified`; epics/stories/spikes: `todo | in-progress | blocked | done`)
- Frontmatter serialisation/deserialisation round-trips cleanly
- Acceptance: all models validate valid inputs and reject invalid ones, including statuses not allowed for the type

### ST-003: `init_project` tool
Initialise a project directory and configure CLAUDE.md.
- Creates `primer/` subdirectories
- Creates `primer/config.yaml` with project name and optional Jira project key
- Appends `## primer-mcp` section to CLAUDE.md if not already present
- Idempotent — safe to run multiple times
- Acceptance: running twice produces identical state to running once

### ST-004: Planning tools — `plan_epic`, `record_adr`
Implement the two top-level planning tools.
- `plan_epic`: creates an Epic ticket, validates required fields
- `record_adr`: creates an ADR linked to an Epic, rejects invalid `epic_id`
- Acceptance: gating enforced — `record_adr` fails cleanly with helpful message if epic not found

### ST-005: Execution tools — `create_story`, `create_task`, `create_spike`, `start_task`
Implement story and task creation with workflow gating.
- `create_story`: blocked if parent epic has no ADR
- `create_task`: requires valid `story_id`
- `create_spike`: requires valid `story_id`, records question and timebox
- `start_task`: transitions status to `in-progress`
- Acceptance: all gates enforced with clear error messages
- Follow-up once this story lands: migrate the remaining backlog from `docs/epic-001.md` into `primer/` using the tools themselves (dogfooding), then remove `primer/` from this repo's .gitignore

### ST-006: Completion tools — `complete_task`, `verify_task`, `complete_spike`
Implement two-phase task completion and spike closure.
- `complete_task`: sets task status to `completed`, records completion notes
- `verify_task`: requires status `completed`; records verification evidence; sets status to `verified` (terminal)
- `complete_spike`: records findings, sets spike status to `done`
- Acceptance: `verify_task` fails with an actionable error if the task is not `completed`; state transitions match the Ticket Lifecycle

### ST-007: Query and graph tools — `get_next_action`, `get_ticket`, `list_tickets`, `update_ticket`
Implement project navigation and read/update tools using networkx.
- `get_next_action`: returns the first unmet workflow gate, else the next unblocked ticket in deterministic order (topological order of the dependency graph, oldest ID first)
- `get_ticket`: returns one ticket (frontmatter + body) by ID
- `list_tickets`: lists tickets, filterable by type and status
- `update_ticket`: post-creation edits — status (e.g. `blocked`), `blocks`/`blocked_by` edges, body sections
- Derived done-ness: story done when all child tasks `verified` and spikes `done`; epic done when all stories done
- Internal graph built from hierarchy + `blocks`/`blocked_by` fields; cycle detection on dependency edges only
- Acceptance: correctly identifies blockers; rejects edge updates that would create a dependency cycle

### ST-008: `export_graph` — vis.js HTML output
Generate a self-contained, browser-openable HTML file with an interactive graph.
- Nodes coloured by type (epic, adr, story, task, spike) and status (todo, in-progress, done, blocked)
- Edges show hierarchy and dependency relationships
- Click a node to see ticket details
- Acceptance: file opens in browser with no external requests; graph renders correctly for a sample project
- Open question: should the graph auto-regenerate on every ticket change? Current design is on-demand. Auto options: server-side (each tool triggers rebuild, adds coupling/latency) or client-side hook (Claude Code specific). Decide during implementation.

### ST-009: MCP Prompts — `plan_story`, `export_jira`, `import_jira`
Implement the MCP Prompt primitives.
- `plan_story`: scaffolds a planning conversation before a story is created; prompts for title, acceptance criteria, definition of done, dependencies
- `export_jira`: scaffolds exporting tickets to Jira via the client's Jira MCP server, following the field mapping in `docs/architecture.md`; instructs the agent to record created issue keys in `external_ref` so re-export updates instead of duplicating
- `import_jira`: scaffolds importing a Jira epic and its children into primer via the client's Jira MCP server; instructs the agent to traverse the Jira hierarchy, map issue types to primer types (Epic/Story/Task), create them locally in workflow-gate order (epic → ADR placeholder → stories → tasks), and record Jira issue keys in `external_ref` so future exports update rather than duplicate
- Works in any MCP client
- Acceptance: all three prompts are registered and returned correctly by the server

### ST-010: Test sweep — coverage gaps and MCP integration
Stories ST-002 onward land with their own unit tests in their PRs (see CLAUDE.md); this story audits the accumulated suite and completes it.
- Fill coverage gaps across schema validation, gating rules, graph traversal, and state transitions
- Cross-cutting cases individual stories may have missed: gate interactions, cycle detection on dependency edges only, derived story/epic done-ness, gate error messages containing the corrective action
- `export_graph` output (valid HTML, correct node/edge data)
- MCP integration: tools and prompts registered and callable via the `mcp` SDK's in-memory client
- Acceptance: all tests pass; no mocking of filesystem (use `tmp_path` fixture)

### ST-011: README, CLAUDE.md snippet, MCP registry submission
Finalise documentation and publish.
- README: elevator pitch, install instructions, usage examples, tool reference, CI badges, demo screenshot/GIF of `export_graph` output, "Graduating to Jira" section
- Review pass over all tool descriptions and gate error messages as agent-steering surfaces (see `docs/architecture.md`)
- CLAUDE.md snippet shown in README for manual adopters
- PyPI publish via `uv publish`
- MCP registry submission PR
- Acceptance: `uvx primer-mcp --help` works from a fresh environment; registry PR open
- Blocked by: ST-012 (CI must be green before publishing)

### ST-012: CI pipeline
GitHub Actions workflow covering quality gates and release.
- On push/PR: `ruff check`, `ruff format --check`, `mypy`, `pytest` on a matrix of Python 3.12, 3.13, 3.14
- On tag: build and publish to PyPI (trusted publishing)
- Acceptance: workflow green on main; a test tag publishes to TestPyPI

### ST-013: Portfolio framing — AI-orchestrated development showcase
Add a README section that frames the repo as a demonstration of AI-orchestrated development for portfolio use.
- Explain which decisions were the author's (architecture, workflow design, gates) vs AI-generated code
- Describe the human–AI workflow: planning-first, two-phase completion, how the agent was directed
- Note what was learned and what the co-author tags represent (transparency, not delegation)
- Tone: thesis statement, not apology — "here's how I ship with AI" not "AI helped me"
- Acceptance: README contains a clearly authored section that a hiring manager at an AI company would read as evidence of orchestration skill

### ST-014: `reopen_task` — reversing a verified task
Add an explicit tool for when a verified task's fix did not hold. Deliberately not a generic `update_ticket` status edit — ST-007 rejects status changes on terminal tickets so that reopening is always an intentional, recorded act.
- `reopen_task(task_id, reason)`: gates on status `verified`; returns the task to `todo` and records the reason
- Prior `verified_evidence` is preserved in the body — it was true when written, so it is superseded rather than deleted
- Cascades upward: parent story and epic revert from `done` to `in-progress` via ST-007's `recompute_parents`
- No cascade to dependents: `blocked_by` readiness is computed per call, so tickets depending on the reopened task stop being offered automatically, with no writes
- Open question: should spikes be reopenable too? `complete_spike` is likewise terminal
- Acceptance: reopening the last verified task of a done story reverts both story and epic; a ticket `blocked_by` the reopened task is no longer offered by `get_next_action`; reopening a non-verified task fails with an actionable error naming the current status
- Blocked by: ST-007 (needs `recompute_parents` and the graph layer)
