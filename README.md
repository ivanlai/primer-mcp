# primer-mcp

> **Beta** — the core workflow is stable and tested, but the tool is new. Expect rough edges.

A Jira-lite MCP server that guides planning-first workflows for AI-assisted development — tickets as markdown files, your AI agent as the interface.

## Why

AI coding agents jump straight to implementation. primer-mcp makes them plan first: state why the work matters, record decisions, break it into stories and tasks, then complete and verify each one. The tickets are plain markdown with YAML frontmatter, committed alongside your code — no external service, no database, fully visible in your repo.

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
# Run directly (recommended for MCP)
uvx primer-mcp

# Or install permanently
uv tool install primer-mcp

# Update to latest
uv tool upgrade primer-mcp

# Uninstall
uv tool uninstall primer-mcp
```

## Quick start

Add to your MCP client config (e.g. Claude Code `settings.json`, Claude Desktop `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "primer-mcp": {
      "command": "uvx",
      "args": ["primer-mcp"]
    }
  }
}
```

Then ask your AI agent to plan some work. The recommended flow is:

```
init_project  →  plan_epic  →  record_adr  →  create_story  →  create_task
```

The tools suggest this order but don't block you from skipping steps — if the work is straightforward, go straight from epic to stories. You'll get a helpful nudge if the tools think you might want to record a decision first.

Once tasks exist, the execution cycle is:

```
start_task  →  complete_task (with notes)  →  verify_task (with evidence)
```

Not sure what to do next? `get_next_action` reads the current state and returns exactly one instruction.

## Tools

### Setup

| Tool | What it does |
|------|-------------|
| `init_project` | Create the `primer/` ticket store and add the workflow section to CLAUDE.md |

### Planning

| Tool | What it does |
|------|-------------|
| `plan_epic` | Create an epic — the top-level container for a body of work |
| `record_adr` | Record an architecture decision: context, decision, rejected alternatives, consequences |
| `create_story` | Create a story under an epic — a deliverable with acceptance criteria |
| `create_task` | Create a task under a story — a concrete unit of work with a testable outcome |
| `create_spike` | Create a spike — a timeboxed investigation to answer a question |

### Execution

| Tool | What it does |
|------|-------------|
| `start_task` | Move a task to in-progress |
| `complete_task` | Mark a task completed with notes on what was done |
| `verify_task` | Verify a completed task with evidence (point at the commit) |
| `complete_spike` | Close a spike with findings |

### Query

| Tool | What it does |
|------|-------------|
| `get_next_action` | Ask what to do next — returns exactly one instruction |
| `get_ticket` | Read a ticket by ID with its full body |
| `list_tickets` | List tickets, filterable by type or status |
| `update_ticket` | Amend a ticket's status, dependencies, body sections, or external refs |

### Export

| Tool | What it does |
|------|-------------|
| `export_graph` | Generate a self-contained HTML file visualising the project as an interactive graph |

## Prompts

| Prompt | What it does |
|--------|-------------|
| `plan_story` | Walk through a planning conversation before creating a story |
| `export_jira` | Export primer-mcp tickets to Jira via a Jira MCP server |
| `import_jira` | Import a Jira epic and its hierarchy into primer-mcp |

## CLAUDE.md snippet

`init_project` appends this to your project's CLAUDE.md automatically. If you prefer to add it manually:

```markdown
## primer-mcp

This project uses primer-mcp for planning-first development. Tickets are
markdown files under `primer/` — they are yours to read and edit. Prefer the
tools for creating and updating them: they allocate IDs, follow the templates
and guide the workflow. Hand-edit where the tools fall short.

- Plan before code. The recommended flow is Epic -> ADR -> Story -> Task,
  but the tools suggest rather than enforce — skip steps when it makes
  sense for the work at hand.
- Unsure what to do next? Call `get_next_action`.
- Completion is two-phase: `complete_task` with notes, then `verify_task`
  with evidence (point at the commit, not the output). Both are
  recommended — the tools will nudge you if you skip a step.
- After creating tickets, completing tasks, or verifying tasks, offer to
  regenerate the project graph with `export_graph` so the user can see
  the updated picture.
- When the user reports a bug or small fix, check for a standing bug-fix
  story under the epic before creating a new story. Small fixes (1-2
  tasks) go as tasks under that story; larger efforts (3+ tasks) get
  their own story. If no bug-fix story exists yet, suggest creating one.
```

## Graduating to Jira

primer-mcp tickets map directly to Jira concepts (Epic, Story, Task, ADR). When a project outgrows local markdown files, use the `export_jira` prompt with any Jira MCP server to push tickets to Jira. The `external_ref` field on each ticket tracks the Jira key, so re-exports update existing issues instead of creating duplicates. `import_jira` goes the other direction.

## This repo dogfoods itself

The `primer/` directory is this project's own backlog, created with the tools in `src/` and committed deliberately — a tool that tells you to commit your ticket store should commit its own. It doubles as a worked example: browse it to see what a real store looks like before installing anything.

- `primer/adrs/` — why the design is what it is, including the alternatives that were rejected and why
- `primer/stories/` and `primer/tasks/` — what is done, what is next, and the evidence each completed task was verified against

**It is project management, not part of the package.** The wheel ships `src/primer_mcp` only, and `primer/` is excluded from the source distribution. When you install primer-mcp, `init_project` creates *your* `primer/` — this one never reaches your machine.

## License

MIT
