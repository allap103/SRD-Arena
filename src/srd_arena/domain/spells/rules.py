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
        entry.get("unit")
        for entry in spell.casting_time
        if isinstance(entry, dict)
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
) -> str | None:
    if economy.action > 0 and not action_available:
        return "You have already used your Action."
    if economy.bonus_action > 0 and not bonus_action_available:
        return "You have already used your Bonus Action."
    if economy.reaction > 0 and not reaction_available:
        return "You have already used your Reaction."
    if spell.level > 0 and spellcasting.spell_slots_remaining.get(spell.level, 0) <= 0:
        return f"You have no level {spell.level} spell slots remaining."
    return None


def spell_targets_self_only(spell: Spell) -> bool:
    return spell.range_data.get("type") == "self"


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
    target_ref: str | None = None,
    aim_point: tuple[float, float] | None = None,
    selected_condition: str | None = None,
) -> str:
    if aim_point is not None:
        return f"{spell_id}@{aim_point[0]:.4f},{aim_point[1]:.4f}"
    if target_ref is None:
        return spell_id
    value = f"{spell_id}:{target_ref}"
    if selected_condition is not None:
        value += f"#{selected_condition}"
    return value


def parse_spell_action_value(value: str) -> tuple[str, str | None, tuple[float, float] | None]:
    value, _, _selection = value.partition("#")
    if "@" in value:
        spell_id, _, aim = value.partition("@")
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


def parse_spell_action_condition(value: str) -> str | None:
    _base, separator, condition = value.partition("#")
    return condition if separator and condition else None
