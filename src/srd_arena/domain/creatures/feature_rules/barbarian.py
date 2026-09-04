"""Implement Barbarian-specific combat features as Python rule handlers."""

from __future__ import annotations

from collections.abc import Callable

from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.effects.modifiers import RollModifier
from srd_arena.domain.effects.results import ActionResolutionResult, EffectResult
from srd_arena.domain.effects.rule_effects import (
    DamageResistance,
    InvocationProhibition,
    RollAdjustment,
)
from srd_arena.domain.effects.runtime import (
    EffectPolarity,
    ExtendEventRule,
    OngoingEffectLifecycle,
    UntilTurnEnd,
)
from srd_arena.domain.rolls.dice import DieRoller

from ..model import Creature


def resolve_barbarian_feature(
    creature: Creature,
    feature_id: str,
    roll_die: DieRoller,
    heal: Callable[[int], int],
    *,
    actor_ref: str,
    round_number: int = 1,
) -> ActionResolutionResult | None:
    """Execute a supported Barbarian feature for one encounter actor."""

    del roll_die, heal
    if feature_id == "extend_rage":
        return ActionResolutionResult(
            definition_id="extend_rage",
            definition_name="Extend Rage",
            messages=[("system", f"{creature.name} extends Rage.")],
            effects=[
                EffectResult(
                    kind="extend_ongoing_effect",
                    target_ref=actor_ref,
                    data={
                        "definition_id": "rage",
                        "expires_on_round": round_number + 1,
                    },
                )
            ],
        )
    if feature_id != "rage":
        return None
    uses_remaining = creature.spend_feature_use("rage")
    return ActionResolutionResult(
        definition_id="rage",
        definition_name="Rage",
        messages=[("system", f"{creature.name} enters Rage.")],
        effects=[
            EffectResult(
                kind="start_ongoing_effect",
                target_ref=actor_ref,
                data={
                    "source_ref": actor_ref,
                    "source_label": creature.name,
                    "source_kind": "feature",
                    "definition_id": "rage",
                    "effect_kind": "generic",
                    "polarity": EffectPolarity.BENEFICIAL.value,
                    "ends_concentration": True,
                    "dispellable": False,
                },
                effect_label="Rage",
                duration=UntilTurnEnd(actor_ref, round_number + 1),
                lifecycle=OngoingEffectLifecycle(
                    started_round=round_number,
                    end_conditions=(Condition.INCAPACITATED,),
                    extend_events=(
                        ExtendEventRule(
                            "target_makes_attack",
                            "actor_against_opponent",
                        ),
                        ExtendEventRule(
                            "target_forces_saving_throw",
                            "actor_against_opponent",
                        ),
                    ),
                    maximum_end_round=round_number + 100,
                ),
                rule_effects=(
                    DamageResistance(
                        frozenset({"bludgeoning", "piercing", "slashing"})
                    ),
                    RollAdjustment(
                        RollModifier(
                            "ability_check",
                            "advantage",
                            ability="strength",
                        )
                    ),
                    RollAdjustment(
                        RollModifier(
                            "saving_throw",
                            "advantage",
                            ability="strength",
                        )
                    ),
                    RollAdjustment(
                        RollModifier(
                            "damage_roll",
                            "add",
                            value=2,
                            ability="strength",
                        )
                    ),
                    InvocationProhibition(
                        frozenset({"cast_spell"}),
                        "rage_spellcasting",
                        "You cannot cast spells while raging.",
                    ),
                ),
            )
        ],
        resource_updates={"rage": uses_remaining},
    )
