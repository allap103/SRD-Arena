"""Assemble loaded spells from authored content.

The translator has three jobs: resolve the authored spell, compile intrinsic
spell metadata and the shared executable capability definition, and separately
produce the legacy ``SpellCapability`` projection still consumed by the
encounter runtime.
Provider-specific grants and resource costs do not belong here.

Keep ``build_spell`` as the readable orchestration entrypoint. New translation
rules belong in the concern-based ``translation`` package; the remaining legacy
projection should shrink as runtime consumers move to shared capabilities.

# TODO: Move remaining encounter-runtime consumers from SpellCapability to
# shared capability definitions, then remove the legacy projection.
"""

from .catalog import SpellCatalog
from .schema import SpellSchema
from .resolution import (
    AutomaticResolutionSchema,
    RepeatResolutionSchema,
    SavingThrowResolutionSchema,
    SequenceResolutionSchema,
    SpellAttackResolutionSchema,
)
from srd_arena.content.common.sources import slug
from srd_arena.domain.spells import (
    SpellCapability,
    Spell,
)
from .translation import (
    automatic_success_condition_immunities,
    automatic_success_traits,
    compile_activation,
    compile_spell_definition,
    creature_types_from_requirements,
    damage_repeat_save_advantage,
    end_events,
    find_spell,
    normalize_save_ability,
    repeat_failure_conditions,
    repeat_failure_damage,
    repeat_save_trigger,
    save_advantage_against_opponents,
    target_requirements,
)


from .translation.metadata import (
    remove_effect_selection,
    spell_area_size_feet,
    spell_damage_dice,
    spell_geometry_mode,
    spell_removable_conditions,
    spell_removable_effect_kinds,
)
from .translation.follow_ups import follow_up_resolution


def build_spell(
    name: str,
    source: str | None,
    catalog: SpellCatalog | None,
) -> Spell:
    raw = find_spell(name, source, catalog)
    capability = _translate_capability(raw)
    return Spell(
        id=slug(raw.public_name),
        name=raw.public_name,
        source=raw.source,
        level=raw.level,
        school=raw.school,
        casting_time=tuple(raw.time),
        range_data=dict(raw.range),
        duration_data=tuple(raw.duration),
        components=dict(raw.components),
        saving_throw_abilities=tuple(
            normalize_save_ability(value) for value in raw.saving_throw
        ),
        condition_inflict=tuple(raw.condition_inflict),
        removable_conditions=spell_removable_conditions(raw),
        removable_effect_kinds=spell_removable_effect_kinds(raw),
        remove_effect_selection=remove_effect_selection(raw),
        damage_dice=spell_damage_dice(raw),
        damage_inflict=tuple(raw.damage_inflict),
        area_tags=tuple(raw.area_tags),
        geometry_mode=spell_geometry_mode(raw),
        area_size_feet=spell_area_size_feet(raw),
        concentration=any(
            bool(duration.get("concentration"))
            for duration in raw.duration
            if isinstance(duration, dict)
        ),
        recast_ends_previous=(
            raw.capability.recast_ends_previous if raw.capability is not None else False
        ),
        self_removal_blocked_conditions=(
            tuple(raw.capability.self_removal_blocked_conditions)
            if raw.capability is not None
            else ()
        ),
        target_requirements=target_requirements(raw),
        definition=compile_spell_definition(raw),
        capability=capability,
        activation=compile_activation(raw),
    )


def _translate_capability(raw: SpellSchema) -> SpellCapability | None:
    if raw.capability is None:
        return None
    outer_resolution = raw.capability.resolution.root
    sequence = (
        outer_resolution
        if isinstance(outer_resolution, SequenceResolutionSchema)
        else None
    )
    if sequence is not None:
        outer_resolution = sequence.steps[0].resolution.root
    repeated = (
        outer_resolution
        if isinstance(outer_resolution, RepeatResolutionSchema)
        else None
    )
    resolution = repeated.resolution.root if repeated is not None else outer_resolution
    if not isinstance(
        resolution,
        (
            AutomaticResolutionSchema,
            SavingThrowResolutionSchema,
            SpellAttackResolutionSchema,
        ),
    ):
        return None
    return SpellCapability(
        automatic_failure_creature_types=(
            creature_types_from_requirements(resolution.automatic_failure)
            if isinstance(resolution, SavingThrowResolutionSchema)
            else ()
        ),
        disadvantage_creature_types=(
            tuple(
                creature_type
                for modifier in resolution.save_modifiers
                if modifier.mode == "disadvantage"
                for creature_type in creature_types_from_requirements(
                    modifier.requirements
                )
            )
            if isinstance(resolution, SavingThrowResolutionSchema)
            else ()
        ),
        repeat_save_trigger=repeat_save_trigger(resolution),
        repeat_failure_conditions=repeat_failure_conditions(resolution),
        repeat_failure_damage=repeat_failure_damage(resolution),
        end_events=end_events(raw),
        damage_repeat_save_advantage=damage_repeat_save_advantage(raw),
        save_advantage_against_opponents=(save_advantage_against_opponents(resolution)),
        automatic_success_condition_immunities=(
            automatic_success_condition_immunities(resolution)
        ),
        automatic_success_traits=automatic_success_traits(resolution),
        follow_up_resolutions=(
            tuple(follow_up_resolution(raw, step) for step in sequence.steps[1:])
            if sequence is not None
            else ()
        ),
    )
