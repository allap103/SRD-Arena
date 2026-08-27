"""Provide refs support for the encounters package."""

from __future__ import annotations


def reroll_die_action_id(action_id: str, die_index: int) -> str:
    """Handle reroll die action id."""

    return f"{action_id}-reroll-damage-{die_index}"
