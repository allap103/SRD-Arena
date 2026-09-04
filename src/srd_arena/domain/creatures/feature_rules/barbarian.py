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
    UntilTurnStart,
)
from srd_arena.domain.rolls.dice import DieRoller

from ..model import Creature

RECKLESS_ATTACK_FEATURE_ID = "reckless_attack"


def has_reckless_attack(creature: Creature) -> bool:
    """Return whether the creature owns the Reckless Attack feature."""

    return any(
        feature.id == RECKLESS_ATTACK_FEATURE_ID for feature in creature.class_features
    )


def reckless_attack_result(
    creature: Creature,
    actor_ref: str,
    round_number: int,
) -> ActionResolutionResult:
    """Create the sourced advantage and exposure state for Reckless Attack."""

    return ActionResolutionResult(
        definition_id=RECKLESS_ATTACK_FEATURE_ID,
        definition_name="Reckless Attack",
        messages=[("system", f"{creature.name} attacks recklessly.")],
        effects=[
            EffectResult(
                kind="start_ongoing_effect",
                target_ref=actor_ref,
                data={
                    "source_ref": actor_ref,
                    "source_label": creature.name,
                    "source_kind": "feature",
                    "definition_id": RECKLESS_ATTACK_FEATURE_ID,
                    "effect_kind": "generic",
                    "polarity": EffectPolarity.NEUTRAL.value,
                    "dispellable": False,
                },
                effect_label="Reckless Attack",
                duration=UntilTurnStart(actor_ref, round_number + 1),
                rule_effects=(
                    RollAdjustment(
                        RollModifier(
                            "attack_roll",
                            "advantage",
                            ability="strength",
                        )
                    ),
                    RollAdjustment(
                        RollModifier(
                            "attack_roll",
                            "advantage",
                            subject="attacks_against_target",
                        )
                    ),
                ),
            )
        ],
    )


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
