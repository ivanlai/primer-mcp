"""
Command-line entry point for the primer-mcp server.
"""

import argparse
from pathlib import Path

from primer_mcp import __version__
from primer_mcp.server import create_server


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="primer-mcp",
        description=(
            "A Jira-lite MCP server that enforces planning-first workflows "
            "for AI-assisted development. Tickets are markdown files in a "
            "primer/ directory; the AI agent is the interface."
        ),
    )
    parser.add_argument(
        "--project-dir",
        default=".",
        help="Project directory containing (or to contain) the primer/ data store (default: %(default)s)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("list-actionable", help="Print actionable items and exit")
    sub.add_parser("serve", help="Start the MCP server (default)")

    args = parser.parse_args()

    if args.command == "list-actionable":
        from primer_mcp import query

        print("\n".join(query.list_actionable(Path(args.project_dir))))
    else:
        create_server(Path(args.project_dir)).run("stdio")


if __name__ == "__main__":
    main()
