"""Command-line entry point for the primer-mcp server."""

import argparse

from primer_mcp import __version__


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="primer-mcp",
        description=(
            "A Jira-lite MCP server that enforces planning-first workflows "
            "for AI-assisted development. Tickets are markdown files in a "
            ".primer/ directory; the AI agent is the interface."
        ),
    )
    parser.add_argument(
        "--project-dir",
        default=".",
        help="Project directory containing (or to contain) the .primer/ data store (default: %(default)s)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    args = parser.parse_args()

    # Server startup lands with the MCP tool implementations (ST-004 onwards).
    parser.exit(
        message=(
            f"primer-mcp {__version__}: server not yet implemented "
            f"(project dir: {args.project_dir})\n"
        )
    )


if __name__ == "__main__":
    main()
