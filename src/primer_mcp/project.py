"""
Project initialisation: the primer/ data store and CLAUDE.md setup.

Everything here is idempotent — running init_project twice produces
byte-identical state to running it once, and user-owned files
(config.yaml, CLAUDE.md) are never overwritten or rewritten.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from primer_mcp.errors import GateError
from primer_mcp.models import SCHEMA_VERSION

PRIMER_DIR = "primer"

# Where each ticket type lives under primer/. Single source of truth for the
# store layout: SUBDIRS below and every path lookup derive from it.
SUBDIR_FOR_TYPE = {
    "epic": "epics",
    "adr": "adrs",
    "story": "stories",
    "task": "tasks",
    "spike": "spikes",
}
SUBDIRS = tuple(SUBDIR_FOR_TYPE.values())


def require_store(project_dir: Path) -> Path:
    """
    Resolve a project directory to its ticket store, or raise.

    Every entry point in the package takes the *project* directory and
    converts here, so there is one convention rather than two. Passing the
    store itself is caught by the same check: primer/primer does not exist.

    Named for what it does rather than what it returns, matching
    `_require_ticket` in tickets.py — and to stay clear of PRIMER_DIR above,
    which is the directory's name, not a resolved path.
    """
    primer = project_dir / PRIMER_DIR
    if not primer.is_dir():
        raise GateError(
            f"Project not initialised: {primer} does not exist. Run init_project first, then retry."
        )
    return primer


# Idempotency marker: if this heading exists in CLAUDE.md, we never touch the file.
SNIPPET_HEADING = "## primer-mcp"

CLAUDE_MD_SNIPPET = f"""{SNIPPET_HEADING}

This project uses primer-mcp for planning-first development. Tickets are
markdown files under `primer/` — they are yours to read and edit. Prefer the
tools for creating and updating them: they allocate IDs, follow the templates
and guide the workflow. Hand-edit where the tools fall short.

- Plan before code. The recommended flow is Epic → ADR → Story → Task,
  but the tools suggest rather than enforce — skip steps when it makes
  sense for the work at hand.
- Unsure what to do next? Call `list_actionable`.
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
"""


def init_project(
    project_dir: Path,
    project_name: str,
    jira_project_key: str | None = None,
) -> list[str]:
    """
    Initialise a project directory for primer-mcp.

    Returns human-readable lines describing what was done — surfaced
    directly as the MCP tool response, so each line tells the agent
    what exists and the last line points at the next step.
    """
    lines: list[str] = []

    primer = project_dir / PRIMER_DIR
    already_there = primer.is_dir()
    for subdir in SUBDIRS:
        (primer / subdir).mkdir(parents=True, exist_ok=True)
    lines.append(
        f"{'Found existing' if already_there else 'Created'} {PRIMER_DIR}/ "
        f"with subdirectories: {', '.join(SUBDIRS)}"
    )

    config_path = primer / "config.yaml"
    if config_path.exists():
        lines.append(f"Kept existing {PRIMER_DIR}/config.yaml (never overwritten)")
    else:
        config: dict[str, object] = {
            "project_name": project_name,
            "schema_version": SCHEMA_VERSION,
        }
        if jira_project_key is not None:
            config["jira"] = {"project_key": jira_project_key}
        config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        lines.append(f"Created {PRIMER_DIR}/config.yaml (project_name: {project_name})")

    claude_md = project_dir / "CLAUDE.md"
    if not claude_md.exists():
        claude_md.write_text(CLAUDE_MD_SNIPPET, encoding="utf-8")
        lines.append("Created CLAUDE.md with the primer-mcp workflow section")
    elif SNIPPET_HEADING in claude_md.read_text(encoding="utf-8"):
        lines.append("CLAUDE.md already has the primer-mcp section — left untouched")
    else:
        existing = claude_md.read_text(encoding="utf-8")
        separator = "" if existing.endswith("\n\n") else "\n" if existing.endswith("\n") else "\n\n"
        claude_md.write_text(existing + separator + CLAUDE_MD_SNIPPET, encoding="utf-8")
        lines.append("Appended the primer-mcp workflow section to existing CLAUDE.md")

    lines.append("Project initialised. Next step: create an epic with plan_epic.")
    return lines
