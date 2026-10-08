"""Assistance request lifecycle.

Owns the state machine the plan prescribes for Phase 2:

    submitted -> triaged -> approved -> fulfilled
                  \\            \
                   +-> declined  +-> declined

A request enters as ``submitted`` on creation, is ``triaged`` by a case
handler, then either declines or is ``approved`` and eventually ``fulfilled``.
``declined`` and ``fulfilled`` are terminal: nothing may leave either state.

The database guarantees only column defaults and uniqueness; this module is
the single place that decides which transitions are legal, so routes cannot
drift into their own interpretations.
"""

from __future__ import annotations

LIFE_CYCLE: dict[str, frozenset[str]] = {
    "submitted": frozenset({"triaged", "declined"}),
    "triaged": frozenset({"approved", "declined"}),
    "approved": frozenset({"fulfilled", "declined"}),
    "fulfilled": frozenset(),
    "declined": frozenset(),
}

VALID_STATUSES = frozenset(LIFE_CYCLE)


class LifecycleError(ValueError):
    """Raised when a transition is not allowed by the state machine."""


def transition_allowed(current: str, target: str) -> bool:
    return target in LIFE_CYCLE.get(current, frozenset())


def assert_transition(current: str, target: str) -> None:
    """Raise ``LifecycleError`` (not ValueError) on illegal transitions so
    route code can map it to a 409 without catching broad exceptions."""
    if current not in VALID_STATUSES:
        raise LifecycleError(f"unknown current status {current!r}")
    if target not in VALID_STATUSES:
        raise LifecycleError(f"unknown target status {target!r}")
    if not transition_allowed(current, target):
        raise LifecycleError(
            f"cannot move an assistance request from {current!r} to {target!r}"
        )