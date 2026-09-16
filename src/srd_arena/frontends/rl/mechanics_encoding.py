"""Summarize disclosed mechanics while separating initial and later outcomes."""

import re
from collections.abc import Mapping

from srd_arena.engine.api import SpellCapabilityObservation

DAMAGE_TYPES = (
    "acid",
    "bludgeoning",
    "cold",
    "fire",
    "force",
    "lightning",
    "necrotic",
    "piercing",
    "poison",
    "psychic",
    "radiant",
    "slashing",
    "thunder",
    "unknown",
)
CONDITIONS = (
    "blinded",
    "charmed",
    "deafened",
    "exhaustion",
    "frightened",
    "grappled",
    "incapacitated",
    "invisible",
    "paralyzed",
    "petrified",
    "poisoned",
    "prone",
    "restrained",
    "stunned",
    "unconscious",
    "unknown",
)
PHASES = ("automatic", "hit", "miss", "failure", "success", "always", "later")
EFFECT_TYPES = (
    "damage_effect",
    "healing_effect",
    "temporary_hit_points_effect",
    "condition_effect",
    "remove_effect",
    "teleport_effect",
    "forced_movement_effect",
    "attack_hit_damage_effect",
    "attack_hit_retaliation_effect",
    "armor_class_modifier_effect",
    "speed_modifier_effect",
    "speed_multiplier_effect",
    "roll_modifier_effect",
    "damage_resistance_effect",
    "damage_immunity_effect",
    "damage_reduction_effect",
    "condition_immunity_effect",
    "condition_save_advantage_effect",
    "hit_point_maximum_modifier_effect",
    "hit_point_maximum_reduction_effect",
    "prohibit_reactions_effect",
    "turn_economy_restriction_effect",
    "compelled_turn_effect",
    "sense_effect",
    "control_effect",
    "gain_memories_effect",
    "action_prohibition",
    "speed_multiplier",
    "armor_class_adjustment",
    "roll_adjustment",
    "reaction_prohibition",
    "action_economy_restriction",
    "attack_limit",
    "invocation_failure_chance",
)
MECHANIC_FEATURES = (
    "mechanics_known",
    "custom_mechanics",
    "unimplemented_mechanics",
    "duration_rounds",
    "duration_rounds_known",
    "persistent_area",
    "obscures_vision",
    "half_damage_on_save",
    "repeat_save",
    "ends_on_damage",
    "ends_on_assistance",
    "teleport_distance",
    "forced_movement_distance",
    "caster_level",
    "casting_modifier",
    *(f"effect_{kind}" for kind in EFFECT_TYPES),
    *(f"{phase}_condition_{condition}" for phase in PHASES for condition in CONDITIONS),
    *(f"{phase}_damage_{kind}" for phase in PHASES for kind in DAMAGE_TYPES),
    *(f"{phase}_{kind}" for phase in PHASES for kind in ("healing", "temporary_hp")),
)


def mechanics_features(spell: SpellCapabilityObservation | None) -> tuple[float, ...]:
    """Encode intrinsic quantities, not predicted damage against actual targets.

    Dice averages are per effect application before defense/feature modifiers.
    Control flags and amounts summarize the richer tree; they are not a full
    interpreter of arbitrary requirements, selections, or custom Python rules.
    """
    result = dict.fromkeys(MECHANIC_FEATURES, 0.0)
    if spell is None or not spell.mechanics:
        return tuple(result.values())
    mechanics = spell.mechanics
    result["mechanics_known"] = 1.0
    result["custom_mechanics"] = float(mechanics.get("implementation") == "custom")
    result["unimplemented_mechanics"] = float(
        mechanics.get("implementation") == "unimplemented"
    )
    duration = mechanics.get("duration_rounds")
    if isinstance(duration, (int, float)):
        result["duration_rounds"] = duration / 100
        result["duration_rounds_known"] = 1.0
    result["caster_level"] = _number(mechanics.get("caster_level")) / 20
    modifier = _number(mechanics.get("casting_modifier"))
    result["casting_modifier"] = modifier / 20

    def visit(value: object, phase: str = "automatic") -> None:
        """Accumulate typed effects, keeping repeated effects out of initial damage."""
        if isinstance(value, (tuple, list)):
            for item in value:
                visit(item, phase)
            return
        if not isinstance(value, Mapping):
            return
        kind = value.get("type")
        if kind in EFFECT_TYPES:
            result[f"effect_{kind}"] = 1.0
        if kind == "damage_effect":
            damage_type = value.get("damage_type")
            damage_type = damage_type if damage_type in DAMAGE_TYPES else "unknown"
            result[f"{phase}_damage_{damage_type}"] += (
                _dice_mean(value.get("cast_dice", value.get("dice"))) / 100
            )
        if kind in ("healing_effect", "temporary_hit_points_effect"):
            quantity = _dice_mean(
                value.get("cast_dice", value.get("dice")),
                maximum=kind == "temporary_hit_points_effect"
                and spell.temporary_hit_point_dice == "maximum",
            )
            quantity += _number(value.get("cast_bonus", value.get("bonus")))
            quantity += _number(value.get("cast_value", value.get("value")))
            if value.get("modifier") == "ability_modifier":
                quantity += modifier
            suffix = "healing" if kind == "healing_effect" else "temporary_hp"
            result[f"{phase}_{suffix}"] += quantity / 100
        if kind == "condition_effect":
            condition = value.get("condition")
            condition = condition if condition in CONDITIONS else "unknown"
            result[f"{phase}_condition_{condition}"] = 1.0
        if kind == "area_turn_start_save":
            result["repeat_save"] = 1.0
            for condition in value.get("failure_conditions", ()):
                condition = condition if condition in CONDITIONS else "unknown"
                result[f"later_condition_{condition}"] = 1.0
        if kind in ("repeat_save", "repeat_save_lifecycle"):
            result["repeat_save"] = 1.0
        if kind == "teleport_effect":
            result["teleport_distance"] = max(
                result["teleport_distance"], _number(value.get("distance_feet")) / 120
            )
        if kind == "forced_movement_effect":
            result["forced_movement_distance"] = max(
                result["forced_movement_distance"],
                _number(value.get("distance_feet")) / 120,
            )
        if value.get("success_damage") == "half":
            result["half_damage_on_save"] = 1.0
        if value.get("persistent_area") is True:
            result["persistent_area"] = 1.0
        if value.get("obscures_vision") is True:
            result["obscures_vision"] = 1.0
        if value.get("event") == "target_damaged":
            # A trigger only counts as ending if its outcome actually ends the capability.
            resolution = value.get("resolution")
            if isinstance(resolution, Mapping):
                outcome = resolution.get("outcome")
                if isinstance(outcome, Mapping) and outcome.get("end_capability"):
                    result["ends_on_damage"] = 1.0
        if value.get("event") == "adjacent_creature_wakes_target":
            result["ends_on_assistance"] = 1.0
        for key, nested in value.items():
            if key == "scaling":
                continue  # Cast quantities already include scaling.
            next_phase = phase
            if key in ("triggers", "follow_ups", "repeat_saves", "custom"):
                next_phase = "later"
            elif phase != "later" and key in PHASES:
                next_phase = key
            visit(nested, next_phase)

    visit(mechanics)
    return tuple(result.values())


def _number(value: object) -> float:
    """Return an authored numeric quantity, with absent quantities contributing zero."""
    return float(value) if isinstance(value, (int, float)) else 0.0


def _dice_mean(value: object, *, maximum: bool = False) -> float:
    """Compute an intrinsic dice quantity without sampling or reading engine state."""
    if not isinstance(value, str):
        return 0.0
    match = re.fullmatch(r"(\d+)d(\d+)", value)
    if match is None:
        raise ValueError(f"Unsupported disclosed dice expression: {value}")
    count, sides = map(int, match.groups())
    return float(count * sides) if maximum else count * (sides + 1) / 2
