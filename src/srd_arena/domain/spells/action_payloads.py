"""Build typed spell choices for encounter actions."""

from __future__ import annotations

from dataclasses import dataclass

from .definitions import Spell


@dataclass(frozen=True)
class SpellActionPayload:
    """Selections needed to execute one advertised spell action."""

    spell_id: str
    target_refs: tuple[str, ...] = ()
    aim_point: tuple[float, float] | None = None
    selected_condition: str | None = None
    selected_damage_type: str | None = None
    selected_ability: str | None = None
    slot_level: int | None = None
    healing_allocations: tuple[tuple[str, int], ...] = ()

    @property
    def target_ref(self) -> str | None:
        """Return the target for a single-target invocation.

        >>> SpellActionPayload("fire_bolt", ("goblin",)).target_ref
        'goblin'
        >>> SpellActionPayload("scorching_ray", ("goblin", "ogre")).target_ref is None
        True
        """

        return self.target_refs[0] if len(self.target_refs) == 1 else None


def serialize_spell_action_payload(payload: SpellActionPayload) -> dict[str, object]:
    """Translate a typed choice at the application event boundary.

    >>> serialized = serialize_spell_action_payload(
    ...     SpellActionPayload("fireball", aim_point=(3.5, 4.5), slot_level=5)
    ... )
    >>> (serialized["spell_id"], serialized["aim_point"], serialized["slot_level"])
    ('fireball', (3.5, 4.5), 5)
    """

    return {
        "spell_id": payload.spell_id,
        "target_refs": list(payload.target_refs),
        "aim_point": payload.aim_point,
        "selected_condition": payload.selected_condition,
        "selected_damage_type": payload.selected_damage_type,
        "selected_ability": payload.selected_ability,
        "slot_level": payload.slot_level,
        "healing_allocations": dict(payload.healing_allocations),
    }


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


def spell_action_payload(
    spell_id: str,
    target_ref: str | tuple[str, ...] | None = None,
    aim_point: tuple[float, float] | None = None,
    selected_condition: str | None = None,
    selected_damage_type: str | None = None,
    selected_ability: str | None = None,
    slot_level: int | None = None,
    healing_allocations: dict[str, int] | None = None,
) -> SpellActionPayload:
    """Build the complete typed selection for one spell invocation.

    >>> payload = spell_action_payload(
    ...     "mass_heal", ("cleric", "fighter"), slot_level=9,
    ...     healing_allocations={"cleric": 200, "fighter": 500},
    ... )
    >>> (payload.spell_id, payload.target_refs, payload.slot_level)
    ('mass_heal', ('cleric', 'fighter'), 9)
    >>> dict(payload.healing_allocations)
    {'cleric': 200, 'fighter': 500}
    """

    target_refs = (
        ()
        if target_ref is None
        else target_ref
        if isinstance(target_ref, tuple)
        else (target_ref,)
    )
    allocations = tuple(
        sorted(
            (target, amount)
            for target, amount in (healing_allocations or {}).items()
            if amount > 0
        )
    )
    return SpellActionPayload(
        spell_id=spell_id,
        target_refs=target_refs,
        aim_point=aim_point,
        selected_condition=selected_condition,
        selected_damage_type=selected_damage_type,
        selected_ability=selected_ability,
        slot_level=slot_level,
        healing_allocations=allocations,
    )
