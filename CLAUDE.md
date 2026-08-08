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

- Always enter plan mode before implementing a new story
- Every story from ST-002 onward lands with its unit tests in the same PR — acceptance criteria are proven by tests, not deferred to ST-010
- Tasks must be completable in a single session (~3 files max)
- Run `verify_task` before marking any task done
- One PR per task

## Plagiarism policy

Do NOT read or reference `groundwork-mcp` or any similar existing repo. All design decisions must come from first principles. The architecture is fully documented in `docs/architecture.md`.

## Stack

```
mcp                  # MCP server SDK
pydantic             # schema validation
python-frontmatter   # markdown + YAML frontmatter parsing
networkx             # graph traversal and cycle detection
uv                   # packaging and distribution (dev pinned to Python 3.13, requires-python >=3.12)
pytest               # unit tests (use tmp_path fixture, no filesystem mocking)
ruff                 # lint + format (dev)
mypy                 # type checking (dev)
```

## Story status

See `docs/epic-001.md` for the full story list.
Done: ST-001 — Project scaffolding, uv environment, and packaging.
Next: ST-002 — Schema and Pydantic models.
