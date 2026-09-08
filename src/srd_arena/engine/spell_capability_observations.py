"""Describe allied spell invocations without tying the catalog to availability."""

from dataclasses import dataclass

from srd_arena.domain.capabilities import (
    AttackResolution,
    FixedAttackBonus,
    FixedDifficultyClass,
    SavingThrowResolution,
)
from srd_arena.domain.creatures import Creature
from srd_arena.domain.creatures.feature_rules.registry import spell_invocation_grants
from srd_arena.domain.spells import Spell
from srd_arena.domain.spells.invocation_grants import SpellInvocationGrant
from srd_arena.domain.spells.rules import (
    spell_action_economy,
    spell_area_shape,
    spell_max_targets,
)


@dataclass(frozen=True)
class SpellCapabilityObservation:
    """Describe one known spell/cast-level/grant combination, not a legal action.

    Costs are intrinsic invocation costs; current availability stays in action
    options. Resolution metadata describes the initial declarative resolution,
    not every ongoing or custom rule. Damage/healing details are not yet part
    of this draft descriptor. ``maximum_targets=None`` denotes area-wide targeting.
    """

    id: str
    spell_id: str
    grant_id: str | None
    spell_level: int
    cast_level: int
    action_cost: int
    bonus_action_cost: int
    reaction_cost: int
    spell_slot_cost: int
    range_kind: str | None
    range_amount: int | None
    target_kind: str | None
    maximum_targets: int | None
    area_shape: str | None
    area_size_feet: int | None
    concentration: bool
    resolution_kind: str | None
    attack_bonus: int | None
    save_ability: str | None
    save_dc: int | None
    custom_resolver_id: str | None
    temporary_hit_point_dice: str


def observe_spell_capabilities(
    creature: Creature,
) -> tuple[SpellCapabilityObservation, ...]:
    """Return a stable allied catalog, including exhausted slots and feature grants."""

    casting = creature.spellcasting
    if casting is None:
        return ()
    descriptors: list[SpellCapabilityObservation] = []
    for spell in sorted(casting.learned_spells, key=lambda spell: spell.id):
        levels = (
            (0,)
            if spell.level == 0
            else tuple(
                level
                for level, maximum in sorted(casting.spell_slots_max.items())
                if maximum > 0 and level >= spell.level
            )
        )
        for level in levels:
            descriptors.append(_describe(creature, spell, level, None))
    for grant in sorted(spell_invocation_grants(creature), key=lambda grant: grant.id):
        granted_spell = casting.spell_for_grant(grant.spell_id, grant)
        if granted_spell is not None:
            descriptors.append(
                _describe(
                    creature,
                    granted_spell,
                    grant.fixed_cast_level
                    if grant.fixed_cast_level is not None
                    else granted_spell.level,
                    grant,
                )
            )
    return tuple(descriptors)


def _describe(
    creature: Creature, spell: Spell, level: int, grant: SpellInvocationGrant | None
) -> SpellCapabilityObservation:
    casting = creature.spellcasting
    assert casting is not None
    definition = spell.definition
    resolution = definition.resolution if definition is not None else None
    economy = spell_action_economy(spell)
    attack_bonus: int | None = None
    save_dc: int | None = None
    if isinstance(resolution, AttackResolution):
        attack_bonus = (
            resolution.attack_bonus.value
            if isinstance(resolution.attack_bonus, FixedAttackBonus)
            else casting.attack_bonus
        )
    if isinstance(resolution, SavingThrowResolution):
        difficulty = resolution.difficulty
        save_dc = (
            difficulty.value
            if isinstance(difficulty, FixedDifficultyClass)
            else 10 + level
            if difficulty.derivation == "ten_plus_spell_level"
            else casting.save_dc
        )
    target = definition.target if definition is not None else None
    return SpellCapabilityObservation(
        id=f"spell:{spell.id}:level:{level}:grant:{grant.id if grant else 'ordinary'}",
        spell_id=spell.id,
        grant_id=grant.id if grant else None,
        spell_level=spell.level,
        cast_level=level,
        action_cost=economy.action,
        bonus_action_cost=economy.bonus_action,
        reaction_cost=economy.reaction,
        spell_slot_cost=int(
            spell.level > 0 and (grant is None or grant.consumes_spell_slot)
        ),
        range_kind=spell.range.distance.kind if spell.range is not None else None,
        range_amount=spell.range.distance.amount if spell.range is not None else None,
        target_kind=target.kind if target is not None else None,
        maximum_targets=None
        if target is not None and target.kind == "area" and target.occupants != "chosen"
        else spell_max_targets(spell, level, caster_level=creature.attributes.level),
        area_shape=spell_area_shape(spell),
        area_size_feet=spell.area_size_feet,
        concentration=spell.concentration,
        resolution_kind=resolution.kind if resolution is not None else None,
        attack_bonus=attack_bonus,
        save_ability=resolution.ability
        if isinstance(resolution, SavingThrowResolution)
        else None,
        save_dc=save_dc,
        custom_resolver_id=spell.resolver_id,
        temporary_hit_point_dice=grant.temporary_hit_point_dice if grant else "roll",
    )
