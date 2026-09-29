"""
Serialise tickets to and from markdown with YAML frontmatter.

Directory layout and file I/O belong to init_project; this module
only defines the text format so it round-trips cleanly:
loads_ticket(dumps_ticket(ticket, body)) == (ticket, body) for stripped bodies.
"""

from __future__ import annotations

import frontmatter
import yaml
from pydantic import TypeAdapter

from primer_mcp.models import Ticket

_TICKET_ADAPTER: TypeAdapter[Ticket] = TypeAdapter(Ticket)


class _NoAliasDumper(yaml.SafeDumper):
    """
    Never emit YAML anchors/aliases (&id001/*id001) for repeated values —
    frontmatter must stay human-readable and hand-editable.
    """

    def ignore_aliases(self, data: object) -> bool:
        return True


def dumps_ticket(ticket: Ticket, body: str) -> str:
    """
    Render a ticket as markdown with YAML frontmatter.

    Keys keep field-definition order (sort_keys=False) so files diff
    cleanly in git; dates are written as plain ISO dates.
    """
    metadata = ticket.model_dump(mode="python")
    front = yaml.dump(metadata, Dumper=_NoAliasDumper, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{front}\n---\n\n{body.strip()}\n"


def loads_ticket(text: str) -> tuple[Ticket, str]:
    """
    Parse markdown with YAML frontmatter into a validated ticket and body.

    The `type` frontmatter field discriminates which model applies.
    Raises pydantic.ValidationError on schema violations.
    """
    post = frontmatter.loads(text)
    ticket = _TICKET_ADAPTER.validate_python(post.metadata)
    body: str = post.content
    return ticket, body.strip()
