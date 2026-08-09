"""The one exception type shared across layers.

Lives here rather than in tickets.py so graph.py can raise it without an
import cycle — tickets.py imports graph.py, not the other way round.
"""

from __future__ import annotations


class GateError(ValueError):
    """A workflow gate blocked the operation.

    The message is agent-steering: what failed, why, and the exact
    next call to make. Surfaced verbatim as the tool response.
    """
