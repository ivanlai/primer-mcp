# EP-001 — Build and publish primer-mcp

## Goals
Build a working, published MCP server that enforces planning-first workflows for AI-assisted development. See `docs/planning.md` for full goals, constraints, and success criteria.

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

### ST-009: MCP Prompts — `plan_story`, `export_jira`
Implement the MCP Prompt primitives.
- `plan_story`: scaffolds a planning conversation before a story is created; prompts for title, acceptance criteria, definition of done, dependencies
- `export_jira`: scaffolds exporting tickets to Jira via the client's Jira MCP server, following the field mapping in `docs/architecture.md`; instructs the agent to record created issue keys in `external_ref` so re-export updates instead of duplicating
- Works in any MCP client
- Acceptance: both prompts are registered and returned correctly by the server

### ST-010: Tests — unit and MCP integration
Test all business logic independently of the MCP protocol layer, plus one thin integration pass over the protocol layer itself.
- Schema validation (valid and invalid inputs for each model, per-type status rules)
- Workflow gating rules (each gate blocks correctly, error messages contain the corrective action)
- Graph traversal (blockers, blocked-by, cycle detection on dependency edges only, derived story/epic done-ness)
- State transitions (complete → verify sequence; spike completion)
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
