"""Verify that spell invocation facts stay detached and read-only."""

from types import SimpleNamespace
from typing import cast

import pytest

from srd_arena.domain.creatures import Creature
from srd_arena.domain.rolls.dice import D20RollMode
from srd_arena.domain.spells import Spell
from srd_arena.domain.spells.resolution import (
    SpellActionContext,
    SpellResolutionEnvironment,
    SpellTargetContext,
)


def test_spell_target_context_copies_automatic_save_facts() -> None:
    """A target snapshot does not retain the caller's mutable mapping."""

    failures: dict[str, tuple[str, ...]] = {"dexterity": ("stunned",)}
    target = SpellTargetContext(
        cast(Creature, SimpleNamespace()),
        "target",
        "Target",
        automatic_save_failures=failures,
    )

    failures["dexterity"] = ()

    assert target.automatic_failure_reasons("dexterity") == ("stunned",)
    exposed_failures = cast(
        dict[str, tuple[str, ...]],
        target.automatic_save_failures,
    )
    with pytest.raises(TypeError):
        exposed_failures["strength"] = ("restrained",)


def test_spell_action_context_copies_mapping_facts() -> None:
    """An invocation snapshot cannot be changed through source dictionaries."""

    attack_modes: dict[str, D20RollMode] = {"target": "advantage"}
    context = SpellActionContext(
        creature=cast(Creature, SimpleNamespace()),
        spell=Spell("spark", "Spark", "TEST", 0),
        target=SpellTargetContext(
            cast(Creature, SimpleNamespace()),
            "target",
            "Target",
        ),
        current_round=1,
        source_ref="caster",
        environment=cast(SpellResolutionEnvironment, SimpleNamespace()),
        attack_roll_modes=attack_modes,
    )

    attack_modes["target"] = "disadvantage"

    assert context.attack_roll_modes["target"] == "advantage"
    exposed_modes = cast(dict[str, D20RollMode], context.attack_roll_modes)
    with pytest.raises(TypeError):
        exposed_modes["target"] = "normal"
