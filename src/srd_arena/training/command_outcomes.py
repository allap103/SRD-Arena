"""Describe command acceptance and spell resolution without conflating them."""

from collections.abc import Iterable, Mapping
from typing import Any


def command_outcome(
    *,
    kind: str,
    selected_id: str | None,
    rejection: str | None,
    events: Iterable[Mapping[str, Any]],
    resolution_events: Iterable[Mapping[str, Any]] | None = None,
) -> str:
    """Link a submitted spell to its own engine action, including later interrupts.

    Legacy traces also carry enough events to distinguish a pre-cast refusal
    from a failed invocation check after resources were spent. No conclusions
    are drawn from whether damage occurred or whose command resolved a spell.
    """
    if rejection is not None:
        return (
            f"rejected before casting: {rejection}"
            if kind == "spell"
            else f"rejected: {rejection}"
        )
    if kind != "spell":
        return "accepted"
    events = tuple(events)
    declared = next(
        (
            e
            for e in events
            if e["type"] == "action_declared"
            and e["data"].get("selected_action_id") == selected_id
        ),
        None,
    )
    if declared is None or declared.get("action_id") is None:
        return "submitted — cast not confirmed"
    related = [
        e
        for e in (resolution_events if resolution_events is not None else events)
        if e.get("action_id") == declared["action_id"]
    ]
    for event in related:
        if event["type"] == "spell_cast":
            return (
                "cast resolved"
                if event["data"].get("success")
                else "cast resolved — no immediate effect"
            )
    failure = next(
        (
            e
            for e in related
            if e["type"] == "action_resolved" and e["data"].get("reason_code")
        ),
        None,
    )
    if failure is not None:
        started = failure["data"].get("cast_started") or any(
            e["type"] == "invocation_start_checked" for e in related
        )
        phase = (
            "cast failed after spending resources"
            if started
            else "rejected before casting"
        )
        return (
            f"{phase}: {failure['data'].get('reason', failure['data']['reason_code'])}"
        )
    return "submitted — awaiting spell resolution"
