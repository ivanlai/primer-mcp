# primer-mcp

A Jira-lite MCP server that enforces planning-first workflows for AI-assisted development. Tickets are markdown files on the user's local disk. The AI agent is the interface.

## Project docs (read these first)

- `docs/planning.md` — goals, constraints, non-goals, success criteria
- `docs/architecture.md` — all key decisions, ticket schema, graph protocol, body templates
- `docs/epic-001.md` — the single epic and all draft stories (ST-001 through ST-011)

## Key conventions

- **Language:** Python, packaged with `uv`, distributed via `uvx`
- **Data store:** Markdown + YAML frontmatter in `primer/` directory (visible, not dot-hidden; gitignored in THIS repo until the backlog migrates post-ST-005)
- **No provider-specific code** — server must be MCP-protocol-only, no Anthropic/OpenAI SDK calls
- **Ticket body templates** are defined in `docs/architecture.md` — follow them exactly when generating ticket files
- **Graph edges** (`blocks`, `blocked_by`) are base fields on ALL ticket types, not just tasks
- **Two-phase completion:** `complete_task` then `verify_task` — do not collapse into one step

## Workflow gates (enforced by the server — never bypass)

1. Cannot create an ADR without a valid parent Epic
2. Cannot create a Story without the parent Epic having at least one ADR
3. Cannot create a Task without a valid parent Story
4. Cannot call `verify_task` before `complete_task` has been called

## Development workflow

- Dogfood wherever possible — plan and track this project's own work with primer-mcp's own tools, and fix what that exposes. If we don't trust our own process, why should anyone else?
- Always enter plan mode before implementing a new story
- Every story from ST-002 onward lands with its unit tests in the same PR — acceptance criteria are proven by tests, not deferred to ST-010
- No filler tests. Every test must verify a real behaviour or acceptance criterion and be able to fail for a real reason — never add tests for coverage's or quantity's sake
- Tasks must be completable in a single session (~3 files max)
- One PR per task
- Completion is two-phase: `complete_task` with notes, then `verify_task` with evidence. Both are required
- **Tickets hold what git cannot; they never restate it.** Intent before the work — `testable_outcome`, acceptance criteria, an ADR's rejected alternatives — has no other home. What happened, and how, is git's job. So keep ticket bodies at overview level: the goal, not the implementation. Notes and evidence stay one line and point at the commit (`"126 passed, mypy clean — c4ac39f"`) rather than retelling it. Duplicating git is what makes Jira miserable, and detail written before the work is what makes tickets lie: TK-007 listed the functions it would add, the real implementation added others, and `verified` is terminal so it says so permanently
- Detail is safe where the content describes a moment rather than a state, which is why ADRs are the exception: a rejected alternative stays true forever, and a reversal is a new ADR superseding the old one, not an edit

## Plagiarism policy

Do NOT read or reference `groundwork-mcp` or any similar existing repo. All design decisions must come from first principles. The architecture is fully documented in `docs/architecture.md`.

## Stack

```
mcp                  # MCP server SDK
pydantic             # schema validation
python-frontmatter   # markdown + YAML frontmatter parsing
pyyaml               # direct YAML dumping (custom no-alias dumper, stable key order)
networkx             # graph traversal and cycle detection
uv                   # packaging and distribution (dev pinned to Python 3.13, requires-python >=3.12)
pytest               # unit tests (use tmp_path fixture, no filesystem mocking)
ruff                 # lint + format (dev)
mypy                 # type checking (dev)
```

## Story status

Done: ST-001 (scaffolding), ST-002 (schema/models), ST-003 (`init_project`), ST-004 (MCP server + `plan_epic`/`record_adr`), ST-005 (execution tools), ST-006 (completion tools `complete_task`, `verify_task`, `complete_spike`).
Next: ST-007 — query and graph tools `get_next_action`, `get_ticket`, `list_tickets`, `update_ticket`.

The live backlog is `primer/`; `docs/epic-001.md` keeps the prose descriptions.
Story IDs match across both — ST-007 means the query and graph tools story
everywhere. ST-001 through ST-006 were back-filled during migration with one
summary task each, carrying their real merge commits as verification evidence.

## primer-mcp

This project uses primer-mcp for planning-first development. Tickets are
markdown files under `primer/` — they are yours to read and edit. Prefer the
tools for creating and updating them: they allocate IDs, follow the templates
and enforce the workflow. Hand-edit where the tools fall short, but not to set
a status the workflow owns — `verified` and `done` are reached through the
tools or not at all.

- Plan before code. The hierarchy is Epic → ADR → Story → Task, and the
  server enforces the order: an Epic needs at least one recorded ADR before
  stories, a Story before tasks.
- Unsure what to do next? Call `get_next_action`.
- Completion is two-phase: `complete_task` with notes, then `verify_task`
  with evidence (test output, command run). Both are required.
