"""Domain exceptions for Disputes and Chargebacks Manager (F2).

Pure-Python exception hierarchy raised by the domain services. The domain layer never imports a
cloud SDK or a web framework; these errors let callers (the API, the CLI, the agent tool) react
to domain-level failures without coupling to any vendor SDK error type.
"""

from __future__ import annotations


class DisputeError(Exception):
    """Base class for all domain-level errors this service raises."""


class GuardrailBlockedError(DisputeError):
    """Raised when the guardrail blocks an input or a narrated/classified output (rule R1).

    A blocked call must never yield a partial or substitute result: the domain service raises
    this rather than returning an intake classification or a representment draft built on
    unsafe text, and the caller audits the attempt as ``Decision.BLOCKED`` before the raise
    reaches it.
    """
