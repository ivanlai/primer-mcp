# EP-001 — Build and publish primer-mcp

## Goals
Build a working, published MCP server that enforces planning-first workflows for AI-assisted development. See `docs/planning.md` for full goals, constraints, and success criteria.

## Stories

### ST-001: Project scaffolding and packaging
Set up the Python project structure, `pyproject.toml`, and `uvx` entry point so the server is installable and runnable.
- `pyproject.toml` with dependencies: `mcp`, `pydantic`, `python-frontmatter`, `networkx`
- Entry point: `primer_mcp/__main__.py`
- `uv` lockfile committed
- `uvx primer-mcp --help` runs without errors

### ST-002: Schema and Pydantic models
Define and validate all ticket types as Pydantic models.
- Models for: Epic, ADR, Story, Task, Spike
- Shared base model with common fields
- Frontmatter serialisation/deserialisation round-trips cleanly
- Acceptance: all models validate valid inputs and reject invalid ones

### ST-003: `init_project` tool
Initialise a project directory and configure CLAUDE.md.
- Creates `.primer/` subdirectories
- Creates `.primer/config.yaml` with project prefix
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

### ST-006: Completion tools — `complete_task`, `verify_task`
Implement two-phase task completion.
- `complete_task`: marks task as `done`, records completion notes
- `verify_task`: requires `complete_task` called first; records verification evidence; closes the task
- Acceptance: `verify_task` fails if task not yet completed; state transitions are correct

### ST-007: Query and graph tools — `get_next_action`, graph traversal
Implement project navigation tools using networkx.
- `get_next_action`: returns the first unmet workflow gate or highest-priority next action
- Internal graph built from ticket `blocks`/`blocked_by` fields
- Acceptance: correctly identifies blockers; handles circular dependencies gracefully

### ST-008: `export_graph` — vis.js HTML output
Generate a self-contained, browser-openable HTML file with an interactive graph.
- Nodes coloured by type (epic, adr, story, task, spike) and status (todo, in-progress, done, blocked)
- Edges show hierarchy and dependency relationships
- Click a node to see ticket details
- Acceptance: file opens in browser with no external requests; graph renders correctly for a sample project

### ST-009: MCP Prompts — `plan_story`
Implement the `plan_story` MCP Prompt primitive.
- Scaffolds a planning conversation before a story is created
- Prompts for: title, acceptance criteria, definition of done, dependencies
- Works in any MCP client
- Acceptance: prompt is registered and returned correctly by the server

### ST-010: Unit tests
Test all business logic independently of the MCP protocol layer.
- Schema validation (valid and invalid inputs for each model)
- Workflow gating rules (each gate blocks correctly)
- Graph traversal (blockers, blocked-by, circular dependency handling)
- State transitions (complete → verify sequence)
- `export_graph` output (valid HTML, correct node/edge data)
- Acceptance: all tests pass; no mocking of filesystem (use `tmp_path` fixture)

### ST-011: README, CLAUDE.md snippet, MCP registry submission
Finalise documentation and publish.
- README: elevator pitch, install instructions, usage examples, tool reference
- CLAUDE.md snippet shown in README for manual adopters
- PyPI publish via `uv publish`
- MCP registry submission PR
- Acceptance: `uvx primer-mcp --help` works from a fresh environment; registry PR open
