from __future__ import annotations

from dataclasses import dataclass

from ..creatures import Spellcasting
from ..geometry import Grid
from .definitions import Spell


@dataclass(frozen=True)
class SpellActionEconomy:
    action: int = 0
    bonus_action: int = 0
    reaction: int = 0


def spell_action_economy(spell: Spell) -> SpellActionEconomy:
    units = {
        entry.get("unit") for entry in spell.casting_time if isinstance(entry, dict)
    }
    return SpellActionEconomy(
        action=1 if "action" in units else 0,
        bonus_action=1 if "bonus" in units else 0,
        reaction=1 if "reaction" in units else 0,
    )


def spell_cast_block_reason(
    spellcasting: Spellcasting,
    spell: Spell,
    economy: SpellActionEconomy,
    *,
    action_available: bool,
    bonus_action_available: bool,
    reaction_available: bool,
    cast_level: int | None = None,
) -> str | None:
    if economy.action > 0 and not action_available:
        return "You have already used your Action."
    if economy.bonus_action > 0 and not bonus_action_available:
        return "You have already used your Bonus Action."
    if economy.reaction > 0 and not reaction_available:
        return "You have already used your Reaction."
    slot_level = cast_level if cast_level is not None else spell.level
    if spell.level > 0 and spellcasting.spell_slots_remaining.get(slot_level, 0) <= 0:
        return f"You have no level {slot_level} spell slots remaining."
    return None


def spell_targets_self_only(spell: Spell) -> bool:
    return (
        spell.definition is not None and spell.definition.target.kind == "self"
    ) or spell.range_data.get("type") == "self"


def spell_chooses_area_targets(spell: Spell) -> bool:
    if spell.definition is None:
        return False
    target = spell.definition.target
    return target.kind == "area" and target.occupants == "chosen"


def spell_target_disposition(spell: Spell) -> str:
    if spell.definition is not None and spell.definition.target.kind == "creature":
        return spell.definition.target.disposition
    return "enemy"


def spell_area_shape(spell: Spell) -> str | None:
    if spell.definition is not None and spell.definition.target.kind == "area":
        return spell.definition.target.shape
    return None


def spell_repeats_target_allocations(spell: Spell) -> bool:
    if spell.definition is not None and spell.definition.repetition is not None:
        return spell.definition.repetition.allocation in {
            "same_target",
            "same_or_different",
        }
    return False


def spell_requires_full_target_count(spell: Spell) -> bool:
    return bool(
        spell.definition is not None and spell.definition.repetition is not None
    )


def spell_supports_higher_level(spell: Spell) -> bool:
    if spell.definition is not None:
        return any(
            scaling.basis == "resource_level" and scaling.per_level
            for scaling in spell.definition.scaling
        )
    return False


def spell_range_squares(spell: Spell, grid: Grid) -> int | None:
    distance = spell.range_data.get("distance", {})
    if not isinstance(distance, dict):
        return None
    amount = distance.get("amount")
    if distance.get("type") == "touch":
        return 1
    if not isinstance(amount, int):
        return None
    return int(grid.distance_from_feet(amount, minimum=1))


def spell_action_label(
    spell: Spell,
    *,
    actor_ref: str,
    target_ref: str | None = None,
    target_label: str | None = None,
) -> str:
    if target_ref is None or target_ref == actor_ref or target_label is None:
        return f"Cast {spell.name}"
    return f"Cast {spell.name} on {target_label[:1].lower()}{target_label[1:]}"


def spell_action_id(spell: Spell, *, target_ref: str | None = None) -> str:
    if target_ref is None:
        return f"spell-{spell.id}"
    if target_ref.startswith("participant:"):
        return f"spell-{spell.id}-{target_ref.removeprefix('participant:')}"
    return f"spell-{spell.id}-{target_ref.replace(':', '-')}"


def spell_action_value(
    spell_id: str,
    target_ref: str | tuple[str, ...] | None = None,
    aim_point: tuple[float, float] | None = None,
    selected_condition: str | None = None,
    selected_damage_type: str | None = None,
    selected_ability: str | None = None,
    slot_level: int | None = None,
    healing_allocations: dict[str, int] | None = None,
) -> str:
    if aim_point is not None:
        value = f"{spell_id}@{aim_point[0]:.4f},{aim_point[1]:.4f}"
        if isinstance(target_ref, tuple) and target_ref:
            value += f"|{','.join(target_ref)}"
        return _with_spell_selections(
            value,
            selected_condition,
            selected_damage_type,
            selected_ability,
            slot_level,
            healing_allocations,
        )
    if target_ref is None:
        return _with_spell_selections(
            spell_id,
            selected_condition,
            selected_damage_type,
            selected_ability,
            slot_level,
            healing_allocations,
        )
    encoded_target = (
        ",".join(target_ref) if isinstance(target_ref, tuple) else target_ref
    )
    value = f"{spell_id}:{encoded_target}"
    return _with_spell_selections(
        value,
        selected_condition,
        selected_damage_type,
        selected_ability,
        slot_level,
        healing_allocations,
    )


def _with_spell_selections(
    value: str,
    selected_condition: str | None,
    selected_damage_type: str | None,
    selected_ability: str | None,
    slot_level: int | None,
    healing_allocations: dict[str, int] | None = None,
) -> str:
    if (
        selected_condition is not None
        and selected_damage_type is None
        and selected_ability is None
        and slot_level is None
        and not healing_allocations
    ):
        return f"{value}#{selected_condition}"
    selections = []
    if selected_condition is not None:
        selections.append(f"condition={selected_condition}")
    if selected_damage_type is not None:
        selections.append(f"damage_type={selected_damage_type}")
    if selected_ability is not None:
        selections.append(f"ability={selected_ability}")
    if slot_level is not None:
        selections.append(f"slot={slot_level}")
    if healing_allocations:
        encoded = ",".join(
            f"{target_ref}~{amount}"
            for target_ref, amount in sorted(healing_allocations.items())
            if amount > 0
        )
        selections.append(f"healing={encoded}")
    return value if not selections else f"{value}#{'&'.join(selections)}"


def parse_spell_action_value(
    value: str,
) -> tuple[str, str | None, tuple[float, float] | None]:
    value, _, _selection = value.partition("#")
    if "@" in value:
        spell_id, _, aim = value.partition("@")
        aim, _, _targets = aim.partition("|")
        x_text, _, y_text = aim.partition(",")
        if not spell_id or not x_text or not y_text:
            raise ValueError(f"Unsupported spell action payload: {value!r}.")
        return spell_id, None, (float(x_text), float(y_text))
    spell_id, _, target_ref = value.partition(":")
    if not spell_id:
        raise ValueError(f"Unsupported spell action payload: {value!r}.")
    if not target_ref:
        return spell_id, None, None
    return spell_id, target_ref, None


def parse_spell_action_targets(value: str) -> tuple[str, ...]:
    base, _, _selection = value.partition("#")
    if "|" in base:
        _aim_payload, _, targets = base.partition("|")
        return tuple(ref for ref in targets.split(",") if ref)
    _spell_id, target_ref, _aim = parse_spell_action_value(value)
    if target_ref is None:
        return ()
    return tuple(ref for ref in target_ref.split(",") if ref)


def spell_max_targets(
    spell: Spell,
    cast_level: int | None,
    *,
    caster_level: int | None = None,
) -> int:
    if spell.definition is not None:
        definition = spell.definition
        target_maximum = definition.target.count.maximum
        base_target_count = target_maximum if isinstance(target_maximum, int) else 1
        if definition.repetition is not None and isinstance(
            definition.repetition.count, int
        ):
            base_target_count = definition.repetition.count
        if caster_level is not None:
            actor_thresholds = sorted(
                (
                    threshold
                    for scaling in definition.scaling
                    if scaling.basis == "actor_level"
                    for threshold in scaling.thresholds
                    if threshold.minimum_level <= caster_level
                    and any(
                        increment.kind in {"target_count", "projectile_count"}
                        and isinstance(increment.amount, int)
                        for increment in threshold.increments
                    )
                ),
                key=lambda threshold: threshold.minimum_level,
            )
            if actor_thresholds:
                base_target_count = next(
                    increment.amount
                    for increment in actor_thresholds[-1].increments
                    if increment.kind in {"target_count", "projectile_count"}
                    and isinstance(increment.amount, int)
                )
        resolved_level = cast_level if cast_level is not None else spell.level
        levels_above = max(0, resolved_level - spell.level)
        per_level_increment = sum(
            increment.amount
            for scaling in definition.scaling
            if scaling.basis == "resource_level"
            for increment in scaling.per_level
            if increment.kind in {"target_count", "projectile_count"}
            and isinstance(increment.amount, int)
        )
        return base_target_count + levels_above * per_level_increment
    return 1


def parse_spell_action_condition(value: str) -> str | None:
    _base, separator, selections = value.partition("#")
    if not separator:
        return None
    for selection in selections.split("&"):
        key, equals, selected = selection.partition("=")
        if equals and key == "condition" and selected:
            return selected
    return selections if "=" not in selections and selections else None


def parse_spell_action_damage_type(value: str) -> str | None:
    _base, separator, selections = value.partition("#")
    if not separator:
        return None
    for selection in selections.split("&"):
        key, equals, selected = selection.partition("=")
        if equals and key == "damage_type" and selected:
            return selected
    return None


def parse_spell_action_ability(value: str) -> str | None:
    _base, separator, selections = value.partition("#")
    if not separator:
        return None
    for selection in selections.split("&"):
        key, equals, selected = selection.partition("=")
        if equals and key == "ability" and selected:
            return selected
    return None


def parse_spell_action_slot(value: str) -> int | None:
    _base, separator, selections = value.partition("#")
    if not separator:
        return None
    for selection in selections.split("&"):
        key, equals, selected = selection.partition("=")
        if equals and key == "slot" and selected.isdigit():
            return int(selected)
    return None


def parse_spell_healing_allocations(value: str) -> dict[str, int]:
    _base, separator, selections = value.partition("#")
    if not separator:
        return {}
    for selection in selections.split("&"):
        key, equals, encoded = selection.partition("=")
        if not equals or key != "healing":
            continue
        allocations: dict[str, int] = {}
        for entry in encoded.split(","):
            target_ref, separator, amount = entry.rpartition("~")
            if separator and target_ref and amount.isdigit():
                allocations[target_ref] = int(amount)
        return allocations
    return {}
