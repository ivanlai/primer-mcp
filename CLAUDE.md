# primer-mcp

A Jira-lite MCP server that enforces planning-first workflows for AI-assisted development. Tickets are markdown files on the user's local disk. The AI agent is the interface.

## Key conventions

- **Language:** Python, packaged with `uv`, distributed via `uvx`
- **Data store:** Markdown + YAML frontmatter in `primer/` (visible, not dot-hidden, and committed — this repo dogfoods its own store)
- **No provider-specific code** — server must be MCP-protocol-only, no Anthropic/OpenAI SDK calls
- **Ticket body templates** are defined in `src/primer_mcp/templates.py` — follow them exactly when generating ticket files
- **Graph edges**: `blocked_by` is a base field on ALL ticket types, not just tasks. It is the only stored edge — "A blocks B" is recorded on B (ADR-004)
- **Two-phase completion:** `complete_task` then `verify_task` — do not collapse into one step

## Workflow gates (enforced by the server — never bypass)

1. Cannot create an ADR without a valid parent Epic
2. Cannot create a Task without a valid parent Story

Two-phase completion (`complete_task` then `verify_task`) is recommended and the tools will nudge you if you skip a step, but it is not enforced — `verify_task` proceeds from any pre-terminal state.

## Development workflow

- Dogfood wherever possible — plan and track this project's own work with primer-mcp's own tools, and fix what that exposes. If we don't trust our own process, why should anyone else?
- Always enter plan mode before implementing a new story
- Every story from ST-002 onward lands with its unit tests in the same PR — acceptance criteria are proven by tests, not deferred to ST-010
- No filler tests. Every test must verify a real behaviour or acceptance criterion and be able to fail for a real reason — never add tests for coverage's or quantity's sake
- Tasks must be completable in a single session (~3 files max)
- One PR per task
- When a commit is for a ticket, prefix the message with the ticket ID (`TK-030: Rename get_next_action...`). This closes the loop: `git log --grep TK-030` finds the commit, and `verified_evidence` on the ticket points back at the hash. Standalone chores (CLAUDE.md tweaks, typo fixes) need no prefix.
- Ask before committing and before pushing — the user reviews the working diff, not the PR page
- Improvements and simplifications wait until after v0 ships. This is a compact project that showcases the workflow, not an enterprise system; a heavier primer-mcp has no reason to exist when Jira already does
- Completion is two-phase: `complete_task` with notes, then `verify_task` with evidence. Both are recommended
- **Tickets hold what git cannot; they never restate it.** Intent before the work — `testable_outcome`, acceptance criteria, an ADR's rejected alternatives — has no other home. What happened, and how, is git's job. So keep ticket bodies at overview level: the goal, not the implementation. Evidence stays one line and points at the commit (`"218 passed, mypy clean — c4ac39f"`). Completion notes have two layers: the frontmatter `completed_notes` field is a terse one-liner for scanning; the `## Completion Notes` body section holds a fuller summary — approach taken, key changes, decisions made — the narrative that would otherwise vanish with the chat session. Duplicating git is what makes Jira miserable, and detail written before the work is what makes tickets lie: TK-007 listed the functions it would add, the real implementation added others, and `verified` is terminal so it says so permanently
- Detail is safe where the content describes a moment rather than a state, which is why ADRs are the exception: a rejected alternative stays true forever, and a reversal is a new ADR superseding the old one, not an edit

## Plagiarism policy

Do NOT read or reference `groundwork-mcp` or any similar existing repo. All design decisions must come from first principles.

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

## Where things stand

**Start by running `uv run primer-mcp list-actionable`**, then:

1. Copy the command's entire output into your response as-is. The output
   is already formatted for the user — do not rewrite, summarise, or
   build your own table from it.
2. Below that output, add your recommendation for what to work on next
   and why.

The live backlog is `primer/`. Decisions live in `primer/adrs/` (ADR-001 to
ADR-007) with the alternatives that were rejected. Read those before reopening
a settled question — several were argued through at length and the reasoning
is not in the code.

## primer-mcp

This project uses primer-mcp for planning-first development. Tickets are
markdown files under `primer/` — they are yours to read and edit. Prefer the
tools for creating and updating them: they allocate IDs, follow the templates
and guide the workflow. Hand-edit where the tools fall short.

- Plan before code. The recommended flow is Epic → ADR → Story → Task,
  but the tools suggest rather than enforce — skip steps when it makes
  sense for the work at hand.
- Unsure what to do next? Run `uv run primer-mcp list-actionable`.
- Completion is two-phase: `complete_task` with notes, then `verify_task`
  with evidence (point at the commit, not the output). Both are
  recommended — the tools will nudge you if you skip a step.
- After creating tickets, completing tasks, or verifying tasks, offer to
  regenerate the project graph with `export_graph` so the user can see
  the updated picture.
- Before committing, check whether any tickets completed or verified in
  this session have completion notes that still reflect the actual work.
  If the implementation evolved after the notes were written, update
  both layers before staging: the frontmatter `completed_notes` (terse
  one-liner) and the `## Completion Notes` body section (fuller summary
  — approach taken, key changes, decisions made).
- When the user reports a bug or small fix, check for a standing bug-fix
  story under the epic before creating a new story. Small fixes (1–2
  tasks) go as tasks under that story; larger efforts (3+ tasks) get
  their own story. If no bug-fix story exists yet, suggest creating one.
