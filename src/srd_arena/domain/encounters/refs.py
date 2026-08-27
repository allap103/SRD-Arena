"""Construct stable identifiers for generated encounter actions."""

from __future__ import annotations


def reroll_die_action_id(action_id: str, die_index: int) -> str:
    """Build the action identifier for rerolling one die in a pending roll."""

    return f"{action_id}-reroll-damage-{die_index}"
