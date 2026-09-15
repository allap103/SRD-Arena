"""An idle comparison must never accidentally help the scripted ally."""

import pytest

from srd_arena.engine.api import SelectAction
from srd_arena.frontends.rl.actions import Candidate
from srd_arena.training.baselines import idle_action


@pytest.mark.parametrize(
    "kind",
    [
        "wait",
        "keep_initiative",
        "decline_d20_modifier",
        "decline_reaction",
        "decline_weapon_mastery",
        "decline_reckless_attack",
    ],
)
def test_idle_declines_even_when_an_active_choice_is_first(kind: str) -> None:
    choices = (
        Candidate(SelectAction("attack", "decision"), "attack", "warlock"),
        Candidate(SelectAction("pass", "decision"), kind, "warlock"),
    )
    assert idle_action(choices) == 1


def test_idle_refuses_an_unhandled_decision() -> None:
    with pytest.raises(ValueError, match="no wait/decline"):
        idle_action(
            (Candidate(SelectAction("attack", "decision"), "attack", "warlock"),)
        )
