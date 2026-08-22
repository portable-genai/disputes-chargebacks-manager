"""NarrationPort: the LLM's narrow job (classify into a closed set, narrate over engine facts).

The model NEVER produces a number or a verdict in this service. It has exactly two jobs, both
behind this port: classify an intake into the closed :class:`~..domain.models.IntakeCategory`
set, and narrate a representment draft over facts the engine already decided. The managed adapter
calls Vertex; the local adapter is deterministic (keyword classify, template narrate) so the gate
runs offline; on-prem fails fast. Output that fails validation is discarded by the caller, never
trusted.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class NarrationPort(Protocol):
    def classify(self, text: str, *, categories: tuple[str, ...]) -> str:
        """Return exactly one label from ``categories`` for ``text``, or ``""`` if none fits.

        The caller treats ``""`` and any value outside ``categories`` as a fail-closed to human
        review. The model may not invent a label.
        """
        ...

    def narrate(self, *, instruction: str, facts: tuple[tuple[str, str], ...]) -> str:
        """Narrate a short paragraph from ``facts`` only. It may restate facts, never add them."""
        ...
