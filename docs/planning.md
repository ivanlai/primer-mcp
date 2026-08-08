# primer-mcp — Planning Document

## Goals

- Provide an MCP server that enforces a planning-first workflow: Epic → ADR → Story → Task
- Work with any MCP-compatible client (Claude Code, Cursor, Windsurf, etc.) — provider-agnostic
- Store all project data as human-readable markdown files on the user's local disk
- Be installable with zero setup via `uvx primer-mcp`
- Guide AI agents toward best practices: plan before code, small atomic tasks, explicit verification
- Publish to PyPI and the MCP registry as a reusable open-source tool

## Constraints

- Python only — no TypeScript
- No external database — the filesystem is the data store
- No persistent web server — one exception: `export_graph` generates a self-contained HTML file
- Must work fully offline
- Single-user per project directory — no real-time collaboration
- No provider-specific dependencies in server code (no Anthropic SDK, no OpenAI SDK, etc.)

## Non-Goals

- Multi-user real-time collaboration
- Time tracking, SLA management, or reporting dashboards
- A hosted web service or SaaS offering
- Provider-specific features tied to any one AI vendor
- Replacing full Jira for large enterprise teams

## Success Criteria

- `uvx primer-mcp --project-dir ./` starts the server without errors
- All workflow gates enforced: cannot create a Story without a parent Epic that has an ADR
- `init_project` appends to CLAUDE.md non-destructively and is idempotent
- `export_graph` produces a valid, browser-openable single HTML file with an interactive graph
- Unit tests pass for: schema validation, gating rules, graph traversal, state transitions
- Package published to PyPI as `primer-mcp`
- Server listed in the MCP registry
