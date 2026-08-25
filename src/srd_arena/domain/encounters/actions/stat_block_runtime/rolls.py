"""Dice seams shared by stat-block action resolvers."""

from __future__ import annotations


def roll_die(sides: int) -> int:
    """Roll through the encounter module so existing test seams remain stable."""
    from ... import encounter as encounter_module

    return encounter_module.roll_die(sides)


def roll_dice(count: int, sides: int) -> int:
    """Roll damage through the encounter module's replaceable roller."""
    from ... import encounter as encounter_module

    return encounter_module.roll_dice(count, sides)
