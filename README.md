# primer-mcp
A Jira-lite MCP server that enforces planning-first workflows for AI-assisted development — tickets as markdown files, your AI agent as the interface.

## This repo dogfoods itself

The `primer/` directory is this project's own backlog, created with the tools in
`src/` and committed deliberately — a tool that tells you to commit your ticket
store should commit its own. It doubles as a worked example: browse it to see
what a real store looks like before installing anything.

- `primer/adrs/` — why the design is what it is, including the alternatives that
  were rejected and why
- `primer/stories/` and `primer/tasks/` — what is done, what is next, and the
  evidence each completed task was verified against

**It is project management, not part of the package.** The wheel ships
`src/primer_mcp` only, and `primer/` is excluded from the source distribution.
When you install primer-mcp, `init_project` creates *your* `primer/` — this
one never reaches your machine.
