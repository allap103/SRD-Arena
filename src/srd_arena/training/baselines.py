"""Explicit non-participating baseline for measuring the learner's contribution."""

from collections.abc import Sequence

from srd_arena.frontends.rl.actions import Candidate


def idle_action(choices: Sequence[Candidate]) -> int:
    """Wait or decline an interrupt; never fall back to an arbitrary action."""
    for index, choice in enumerate(choices):
        if choice.kind in {
            "wait",
            "keep_initiative",
            "decline_d20_modifier",
            "decline_reaction",
            "decline_weapon_mastery",
            "decline_reckless_attack",
        }:
            return index
    raise ValueError("Idle baseline has no wait/decline command at this decision")
