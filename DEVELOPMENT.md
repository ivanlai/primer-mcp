# Developer guide

How primer-mcp is put together, for anyone reading or changing the code. For using the tool, see the [README](README.md).

## Getting started

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                        # install dependencies, including dev tools
uv run pytest                  # tests
uv run mypy                    # type checking
uv run ruff check src/ tests/  # lint
uv run ruff format src/ tests/ # format
uv run primer-mcp list-actionable   # what's next in this repo's own backlog
```

CI runs the same checks on Python 3.12, 3.13 and 3.14.

To try unreleased code in an MCP client, point the client at your checkout rather than the PyPI release:

```json
{
  "mcpServers": {
    "primer-mcp": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/primer-mcp", "primer-mcp"]
    }
  }
}
```

This repo plans its own work with primer-mcp. The backlog is in `primer/`, and the design decisions, with the alternatives that were rejected, are in `primer/adrs/`. Read those before reopening a settled question.

## How a tool call reaches the code

The model never talks to primer-mcp directly. The MCP client (e.g. Claude Code) sits in the middle:

```
Model (e.g. Claude, on the provider's servers)
      ▲ │  API calls
      │ ▼
MCP client (e.g. Claude Code, on your machine)
      ▲ │  JSON-RPC over stdio
      │ ▼
primer-mcp (MCP server, child process)
```

1. At start-up, the client launches primer-mcp as a local child process and asks for its tools: names, docstrings and parameter schemas. It passes them to the model.
2. The model replies with a tool call as text. The client sends it to primer-mcp as a JSON-RPC request over the process's standard input.
3. primer-mcp does the work and writes the reply to standard output. The client puts it into the conversation for the model's next turn.

**stdio** (`run("stdio")` in `__main__.py`) means no network and no auth: each client session gets its own local process. That fits the single-user scope. It also means two sessions on the same repo are two processes writing the same `primer/`, with nothing coordinating them.

**The model only ever sees text:** the tool descriptions going in and the results coming back. Both steer the agent, and neither can force it. This is why the server nudges rather than blocks (ADR-008).

**Who writes a ticket.** The model writes the words; primer-mcp writes the file.
- **The model** supplies the content as tool arguments (titles, descriptions, testable outcomes, goals, rejected alternatives, completion notes, evidence) and the judgement (whether to plan, where a task belongs, when work is done).
- **primer-mcp** supplies the structure and bookkeeping: it allocates the ID, fills the template, stamps dates, sets the status, validates against the schema, writes the markdown file, and runs the done-ness cascade.
- **Tickets are plain markdown**, so the model or a person can also edit a file directly without the tools. The workflow allows this where the tools fall short.

## Layers

```
  MCP client (Claude Code, Claude Desktop, ...)
        │  stdio
  server.py          thin MCP layer: tool registration; docstrings are agent-facing copy
        │
  tickets.py         creation + lifecycle (plan_epic ... verify_task)
  backlog_ops.py     reading, what next, amending, tidying
  export.py          self-contained HTML graph
        │
  graph.py           dependency graph (networkx), derived status, cascade
        │
  schema.py          pydantic schema, one model per ticket type
  ticket_format.py   markdown + YAML frontmatter round-trip
  project.py         primer/ layout, init_project, CLAUDE.md snippet
  templates.py       ticket body templates
```

Imports point downward, never up (e.g. `ticket_format.py` imports `schema.py`, never the reverse). The one sideways import is `backlog_ops.py` borrowing `_update_section` from `tickets.py`. `errors.py` holds the one shared exception, `GateError`, so `graph.py` can raise it without an import cycle.

## Modules

1. **`schema.py`: what a ticket is.**
   - One pydantic model per ticket type, with a discriminated union on `type`. ID patterns derive from one `ID_PREFIX` dict.
   - `extra="allow"`: unknown frontmatter keys are kept and written back, never rejected, so adding or removing a field never breaks an existing store (ADR-007).
   - `blocked_by` is the only stored dependency edge. The reverse direction is a graph lookup (ADR-004).
   - `SCHEMA_VERSION` is recorded in `config.yaml` but never enforced, because a version stamp cannot be added retroactively.

2. **`ticket_format.py`: how a ticket is written down.**
   - `dumps_ticket` / `loads_ticket` round-trip a ticket to markdown with YAML frontmatter. No file I/O.
   - A custom YAML dumper with no anchors/aliases and stable key order, so files stay hand-editable and diff cleanly in git.

3. **`project.py`: setup.**
   - `init_project` is idempotent: it creates `primer/`, writes `config.yaml` once, and appends a workflow section to `CLAUDE.md` and `AGENTS.md` only if its heading isn't already there. It never overwrites user files.
   - That section is how the tool steers the agent *outside* tool calls, e.g. to plan before editing code at all.

4. **`tickets.py`: creation and lifecycle.**
   - `next_id` uses max+1, not count+1, so a deleted ticket's ID is never reused.
   - Parent checks are the only hard refusals: no ADR or story without an epic, no task or spike without a story.
   - Lifecycle tools (`start_task`, `complete_task`, `verify_task`) proceed from any status and add a nudge when the transition is unusual (ADR-008).
   - Every function returns a list of lines ending in "Next: <exact call>". The response is written for the agent.

5. **`graph.py`: dependencies and derived status.**
   - `load_tickets` reads and validates every ticket in `primer/` on each call, so hand edits are always picked up. A file that fails to parse or validate produces an error naming the file and the fix.
   - `dependency_graph` builds a networkx DiGraph from `blocked_by` edges only. The hierarchy is deliberately *not* in the graph: a child story blocking its parent epic is a cycle in the combined graph but is semantically fine.
   - `find_cycle` picks the shortest cycle, ties broken by ID, so the error message is stable across runs.
   - `derive_status`: a parent is done when all its children are terminal. A childless story is never vacuously done.
   - `recompute_parents`: the upward cascade (ADR-002). Verifying the last task marks its story done, then its epic. Creating a new task under a done story reverts it to in-progress.

6. **`backlog_ops.py`: the backlog as a whole.**
   - `get_ticket` and `list_tickets` read. `get_ticket` also reports which tickets this one blocks, derived from their `blocked_by`.
   - `list_actionable` is the "what now?" tool: epic context, status drift, urgent items (completed but unverified), then a table of ready work in dependency order. It reports facts; the recommendation is left to the model, steered by the tool description.
   - `update_ticket` validates everything before writing: unknown references and cycles are checked against a probe copy of the store, so a rejected edge leaves the file untouched. It also keeps body sections that mirror a frontmatter field in step with it.
   - `delete_ticket` reports children rather than cascading; `sweep_blocked_by` drops references to deleted tickets.

7. **`server.py`: the MCP layer.**
   - Thin by design; the business logic is tested directly, without MCP.
   - Every tool docstring is shipped to the model as the tool's description, and the type hints become its parameter schema. Treat both as user-facing text: rewording one changes how agents behave.
   - `_call` turns every exception into text, because a tool that throws gives the agent nothing to act on. `GateError` messages say what failed, why, and the exact next call.
   - Also registers three MCP prompts: `plan_story`, and experimental Jira export and import.

8. **`export.py`:** one self-contained HTML file with vis-network inlined, so it opens offline with no external requests.

## One call, end to end

`verify_task(task_id="TK-010", evidence="...", commit="a1b2c3d")`:

1. **From request to business logic:**
   - At start-up, `create_server` registers a small wrapper per tool with `@server.tool(name="verify_task")`. `project_dir` is captured from `create_server`'s argument (a closure), so the model never passes it.
   - At call time, the client sends a JSON-RPC `tools/call` request. The MCP SDK looks the tool up by name, checks the arguments against the schema, and calls the wrapper.
   - The wrapper calls `_call(tickets.verify_task, project_dir, task_id, evidence, commit or None)`. `_call` runs the function, joins the returned lines into one string, and turns any error into readable text.
   - In short: SDK tool table → `@server.tool` wrapper → `_call` → `tickets.verify_task`.
2. `tickets.verify_task` finds the file and parses it through `ticket_format.loads_ticket` into a validated `Task`.
3. It picks a nudge if the task was never completed, sets `verified` and the evidence, and rewrites the body's `## Verification Evidence` section.
4. It writes the file, then calls `graph.recompute_parents`. That re-reads every ticket in `primer/`, checks whether the story (then the epic) is now done, writes those files if so, and adds a nudge to review the acceptance criteria with the user.
5. The agent gets back plain lines: what changed and what to do next.

## Testing

- Tests use real files in pytest's `tmp_path`; the filesystem is never mocked.
- Most tests call the business layers directly, plus a smaller set through the MCP server.
- Every test must be able to fail for a real reason. No tests for coverage's sake.
- Behaviour that depends on the model (do the nudges work?) can't be unit-tested. That is measured separately in [primer-mcp-eval](https://github.com/ivanlai/primer-mcp-eval).

## Workflow in this repo

- Each piece of work is a ticket in `primer/`, and each commit for a ticket is prefixed with its ID (`TK-060: ...`), so `git log --grep TK-060` finds it.
- Completion is two-phase: `complete_task`, commit the code, then `verify_task` with evidence pointing at that commit, and commit the ticket update. Verifying the last task in a story also writes `done` into the story and epic files.
