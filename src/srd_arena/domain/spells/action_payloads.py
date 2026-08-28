"""Encode spell choices into stable action IDs, labels, and command payloads."""

from __future__ import annotations

from .definitions import Spell


def spell_action_label(
    spell: Spell,
    *,
    actor_ref: str,
    target_ref: str | None = None,
    target_label: str | None = None,
) -> str:
    """Build a readable cast label, including a direct target when useful.

    >>> spell = Spell("magic_missile", "Magic Missile", "XPHB", 1)
    >>> spell_action_label(
    ...     spell, actor_ref="wizard", target_ref="goblin", target_label="Goblin"
    ... )
    'Cast Magic Missile on goblin'
    """

    if target_ref is None or target_ref == actor_ref or target_label is None:
        return f"Cast {spell.name}"
    return f"Cast {spell.name} on {target_label[:1].lower()}{target_label[1:]}"


def spell_action_id(spell: Spell, *, target_ref: str | None = None) -> str:
    """Build a stable selectable-action ID for a spell and optional target.

    >>> spell = Spell("fire_bolt", "Fire Bolt", "XPHB", 0)
    >>> spell_action_id(spell, target_ref="participant:goblin")
    'spell-fire_bolt-goblin'
    """

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
    """Encode runtime targeting, upcasting, and allocation choices for execution.

    >>> spell_action_value(
    ...     "mass_heal", ("cleric", "fighter"), slot_level=9,
    ...     healing_allocations={"cleric": 200, "fighter": 500},
    ... )
    'mass_heal:cleric,fighter#slot=9&healing=cleric~200,fighter~500'
    """

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
    """Extract the spell, direct target, or aim point from an action payload.

    >>> parse_spell_action_value("fireball@3.5000,4.0000|goblin#slot=4")
    ('fireball', None, (3.5, 4.0))
    >>> parse_spell_action_value("hold_person:goblin")
    ('hold_person', 'goblin', None)
    """

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
    """Extract the ordered creature references selected for a spell action.

    >>> parse_spell_action_targets("scorching_ray:goblin,ogre")
    ('goblin', 'ogre')
    >>> parse_spell_action_targets("fireball@2.0000,3.0000|goblin,ogre")
    ('goblin', 'ogre')
    """

    base, _, _selection = value.partition("#")
    if "|" in base:
        _aim_payload, _, targets = base.partition("|")
        return tuple(ref for ref in targets.split(",") if ref)
    _spell_id, target_ref, _aim = parse_spell_action_value(value)
    if target_ref is None:
        return ()
    return tuple(ref for ref in target_ref.split(",") if ref)


def parse_spell_action_condition(value: str) -> str | None:
    """Extract the condition chosen for a flexible spell.

    >>> parse_spell_action_condition("lesser_restoration:hero#condition=blinded")
    'blinded'
    >>> parse_spell_action_condition("lesser_restoration:hero#poisoned")
    'poisoned'
    """

    _base, separator, selections = value.partition("#")
    if not separator:
        return None
    for selection in selections.split("&"):
        key, equals, selected = selection.partition("=")
        if equals and key == "condition" and selected:
            return selected
    return selections if "=" not in selections and selections else None


def parse_spell_action_damage_type(value: str) -> str | None:
    """Extract the damage-type selection encoded in a spell action payload.

    >>> parse_spell_action_damage_type("resist_energy:hero#damage_type=fire")
    'fire'
    """

    _base, separator, selections = value.partition("#")
    if not separator:
        return None
    for selection in selections.split("&"):
        key, equals, selected = selection.partition("=")
        if equals and key == "damage_type" and selected:
            return selected
    return None


def parse_spell_action_ability(value: str) -> str | None:
    """Extract the ability chosen for a flexible spell.

    >>> parse_spell_action_ability("enhance_ability:hero#ability=strength")
    'strength'
    """

    _base, separator, selections = value.partition("#")
    if not separator:
        return None
    for selection in selections.split("&"):
        key, equals, selected = selection.partition("=")
        if equals and key == "ability" and selected:
            return selected
    return None


def parse_spell_action_slot(value: str) -> int | None:
    """Extract the spell-slot level selected for this casting invocation.

    >>> parse_spell_action_slot("fireball@2.0000,3.0000#slot=5")
    5
    """

    _base, separator, selections = value.partition("#")
    if not separator:
        return None
    for selection in selections.split("&"):
        key, equals, selected = selection.partition("=")
        if equals and key == "slot" and selected.isdigit():
            return int(selected)
    return None


def parse_spell_healing_allocations(value: str) -> dict[str, int]:
    """Extract per-target healing amounts from a resource-allocation payload.

    >>> parse_spell_healing_allocations(
    ...     "mass_heal:cleric,fighter#healing=cleric~200,fighter~500"
    ... )
    {'cleric': 200, 'fighter': 500}
    """

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
