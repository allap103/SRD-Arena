from srd_arena.content.capabilities import DamageEffectSchema
from srd_arena.content.spells.resolution import SavingThrowResolutionSchema
from srd_arena.content.spells.schema import SpellSchema
from srd_arena.domain.spells import FollowUpSpellResolution, SpellDamage

from .scaling import slot_damage_increment
from .targeting import normalize_save_ability


def follow_up_resolution(
    raw: SpellSchema,
    step: object,
) -> FollowUpSpellResolution:
    target = getattr(step, "target", None)
    resolution_wrapper = getattr(step, "resolution", None)
    resolution = getattr(resolution_wrapper, "root", None)
    if target is None or target.type != "area" or target.origin != "target":
        raise ValueError("Follow-up spell resolutions require a target-origin area.")
    if not isinstance(resolution, SavingThrowResolutionSchema):
        raise ValueError("Only saving-throw follow-up resolutions are executable.")
    damage = tuple(
        SpellDamage(effect.root.dice, effect.root.damage_type)
        for effect in resolution.failure.effects
        if isinstance(effect.root, DamageEffectSchema)
    )
    return FollowUpSpellResolution(
        resolution=resolution.type,
        target=target.type,
        damage=damage,
        save_ability=(
            normalize_save_ability(resolution.ability)
            if resolution.ability is not None
            else None
        ),
        half_damage_on_save=resolution.success_damage == "half",
        area_radius_feet=target.geometry.radius_feet,
        slot_damage_increment=slot_damage_increment(
            raw,
            damage_types={entry.damage_type for entry in damage},
        ),
    )
