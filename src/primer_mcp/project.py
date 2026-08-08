"""Project initialisation: the primer/ data store and CLAUDE.md setup.

Everything here is idempotent — running init_project twice produces
byte-identical state to running it once, and user-owned files
(config.yaml, CLAUDE.md) are never overwritten or rewritten.
"""

from __future__ import annotations

from pathlib import Path

import yaml

PRIMER_DIR = "primer"
SUBDIRS = ("epics", "adrs", "stories", "tasks", "spikes")

# Idempotency marker: if this heading exists in CLAUDE.md, we never touch the file.
SNIPPET_HEADING = "## primer-mcp"

CLAUDE_MD_SNIPPET = f"""{SNIPPET_HEADING}

This project uses primer-mcp for planning-first development. Tickets are
markdown files under `primer/` — browse them freely, but create and update
them through the primer-mcp tools, not by hand-editing frontmatter.

- Plan before code. The hierarchy is Epic → ADR → Story → Task, and the
  server enforces the order: an Epic needs at least one recorded ADR before
  stories, a Story before tasks.
- Unsure what to do next? Call `get_next_action`.
- Completion is two-phase: `complete_task` with notes, then `verify_task`
  with evidence (test output, command run). Both are required.
"""


def init_project(
    project_dir: Path,
    project_name: str,
    jira_project_key: str | None = None,
) -> list[str]:
    """Initialise a project directory for primer-mcp.

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
        config: dict[str, object] = {"project_name": project_name}
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
