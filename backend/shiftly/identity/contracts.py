"""Identity values and context rules without service or HTTP dependencies."""
from dataclasses import dataclass, field


class IdentityError(Exception):
    """Category preserves legacy contracts; reason distinguishes native recovery."""

    def __init__(self, code, message, *, reason=None):
        super().__init__(message)
        self.code = code
        self.reason = reason


@dataclass(frozen=True)
class SessionResult:
    role: str
    token: str = field(repr=False)
    response: dict
    ttl: int


def require_store_context(actor, expected_store_id):
    """A stale-view precondition, never authority to select a different store."""
    if isinstance(expected_store_id, bool) or not isinstance(expected_store_id, int) or expected_store_id <= 0:
        raise IdentityError("invalid", "Expected store ID must be a positive integer.")
    if expected_store_id != actor.store_id:
        raise IdentityError("conflict", "The selected store changed. Refresh and try again.",
                            reason="store_context_changed")
