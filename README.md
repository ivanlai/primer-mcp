# primer-mcp

> **Beta** — the core workflow is stable and tested, but the tool is new. Expect rough edges.

A Jira-lite MCP server that guides planning-first workflows for AI-assisted development — tickets as markdown files, your AI agent as the interface.

## Why

AI coding agents could jump straight to implementation if insufficient guidance is given. Primer-mcp makes them plan first: state why the work matters, record decisions, break it into stories and tasks, then complete and verify each one. The tickets are plain markdown with YAML frontmatter, committed alongside your code — no external service, no database, fully visible in your repo.

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

Tell your AI agent what you want to build — it handles the rest. The server guides the agent through a planning-first workflow: why the work matters, decisions, stories, tasks, completion. Not sure what to do next? Ask your agent — it reads the current state and knows what comes next.

## Tools

Your AI agent calls these tools automatically — you don't need to invoke them directly. You can also ask your agent to call a specific tool if you want more control.

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
| `list_actionable` | List what can be acted on right now, with epic context and recommendations |
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

## Agent instructions

When your project is initialized (automatically on first use, or via `init_project`), this section is appended to your agent config file (CLAUDE.md, AGENTS.md) to guide the agent. If you prefer to add it manually:

```markdown
## primer-mcp

This project uses primer-mcp for planning-first development.
Tickets are markdown files under `primer/` — they are yours to read and edit. 
Prefer the tools for creating and updating them: they allocate IDs, follow the templates
and guide the workflow. Hand-edit where the tools fall short.

- Plan before code. Recommended flow: Epic -> ADR -> Story -> Task,
  suggest rather than enforce — skip steps when it makes sense.
- Unsure what to do next? Call `list_actionable`.
- Completion is two-phase: `complete_task` with notes, then `verify_task`
  with evidence (point at the commit, not the output). Both are
  recommended — the tools will nudge you if you skip a step.
- After tickets creation or changes, offer to regenerate the project graph with `export_graph`.
- Before committing, check that completion notes on finished tickets
  still reflect the actual work — update both the frontmatter
  `completed_notes` and the `## Completion Notes` section if needed.
- Before implementing new work, propose a ticket and parent. Small fixes (1–2
  tasks) go under the standing bug-fix story; larger efforts get their
  own story. The user can decline.
```

## Graduating to Jira

primer-mcp tickets map directly to Jira concepts (Epic, Story, Task, ADR). When a project outgrows local markdown files, use the `export_jira` prompt with any Jira MCP server to push tickets to Jira. The `external_ref` field on each ticket tracks the Jira key, so re-exports update existing issues instead of creating duplicates. `import_jira` goes the other direction.

## This repo dogfoods itself

The `primer/` directory in this repo is the project's own backlog, created with the tools in `src/` and committed deliberately — a tool that tells you to commit your ticket store should commit its own. Browse it on GitHub to see what a real store looks like before installing:

- `primer/adrs/` — design decisions, including rejected alternatives and why
- `primer/stories/` and `primer/tasks/` — what is done, what is next, and verification evidence

**It is project management, not part of the package.** The wheel ships `src/primer_mcp` only, and `primer/` is excluded from the distribution. Your own `primer/` is created automatically when you start planning.

## License

MIT
