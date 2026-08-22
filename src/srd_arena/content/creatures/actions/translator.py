import re
from typing import TYPE_CHECKING, Literal, cast

from . import schema
from srd_arena.content.capabilities import AutomaticResolutionSchema
from srd_arena.content.capabilities.compiler import (
    compile_duration,
    compile_outcome,
    compile_target,
)
from srd_arena.content.creatures.stat_block_schema import (
    BestiaryActionSchema,
    BestiaryMonsterSchema,
)
from srd_arena.domain.creatures import stat_block_actions as domain
import srd_arena.domain.capabilities as shared_domain

if TYPE_CHECKING:
    from srd_arena.content.spells import SpellCatalog


def build_stat_block_actions(
    stat_block: BestiaryMonsterSchema | None,
    spells: "SpellCatalog | None" = None,
) -> dict[str, domain.StatBlockActionDefinition]:
    if stat_block is None:
        return {}
    definitions: dict[str, domain.StatBlockActionDefinition] = {}
    for action in stat_block.action:
        capability = action.capability
        if isinstance(capability, schema.AttackCapabilitySchema):
            definitions[action.name] = _attack_definition(action, capability)
        elif isinstance(capability, schema.CapabilitySchema):
            resolution = capability.resolution
            if isinstance(
                resolution,
                schema.SavingThrowActionResolutionSchema,
            ):
                failure = tuple(
                    shared_domain.OutcomeStage(
                        effects=compile_outcome(stage.effects).effects,
                        repeat_saves=tuple(
                            _repeat_save(repeat) for repeat in stage.repeat_saves
                        ),
                    )
                    for stage in resolution.failure
                )
                compiled = shared_domain.CapabilityDefinition(
                    target=compile_target(capability.target),
                    resolution=shared_domain.SavingThrowResolution(
                        ability=resolution.ability,
                        difficulty=shared_domain.FixedDifficultyClass(
                            resolution.difficulty.value
                        ),
                        failure=failure,
                        success=compile_outcome(resolution.success.effects),
                        always=compile_outcome(resolution.always.effects),
                        success_damage=resolution.success_damage,
                    ),
                )
                grant, resource_pool = _grant(
                    action.name,
                    compiled,
                    capability.resource,
                )
                definitions[action.name] = domain.SavingThrowActionDefinition(
                    name=action.name,
                    target=compiled.target,
                    ability=resolution.ability,
                    dc=resolution.difficulty.value,
                    failure=failure,
                    success=compile_outcome(resolution.success.effects).effects,
                    success_damage=resolution.success_damage,
                    always=compile_outcome(resolution.always.effects).effects,
                    grant=grant,
                    resource_pool=resource_pool,
                )
            elif isinstance(resolution, AutomaticResolutionSchema):
                compiled = shared_domain.CapabilityDefinition(
                    target=compile_target(capability.target),
                    resolution=shared_domain.AutomaticResolution(
                        compile_outcome(resolution.outcome.effects)
                    ),
                )
                grant, resource_pool = _grant(
                    action.name,
                    compiled,
                    capability.resource,
                )
                definitions[action.name] = domain.AutomaticActionDefinition(
                    name=action.name,
                    target=compiled.target,
                    effects=compile_outcome(resolution.outcome.effects).effects,
                    grant=grant,
                    resource_pool=resource_pool,
                )
        elif isinstance(capability, schema.SpellcastingCapabilitySchema):
            definitions[action.name] = domain.SpellcastingActionDefinition(
                name=action.name,
                ability=capability.ability,
                spells=tuple(
                    _spell_option(spell, spells)
                    for spell in capability.spells
                ),
                resource_pool=_resource_pool(
                    f"stat_block_action:{action.name}",
                    capability.shared_resource,
                ),
            )
        else:
            fallback = _parse_tagged_attack(action)
            if fallback is not None:
                definitions[action.name] = fallback
    return definitions


def build_declared_stat_block_actions(
    stat_block: BestiaryMonsterSchema | None,
) -> tuple[domain.DeclaredStatBlockAction, ...]:
    if stat_block is None:
        return ()
    declarations: list[domain.DeclaredStatBlockAction] = []
    for section, actions in (
        ("action", stat_block.action),
        ("bonus_action", stat_block.bonus),
    ):
        declarations.extend(
            domain.DeclaredStatBlockAction(
                name=action.name,
                display_name=_display_name(action.name),
                description="\n".join(
                    entry
                    for entry in action.entries
                    if isinstance(entry, str)
                ),
                capability_type=(
                    action.capability.type
                    if action.capability is not None
                    else None
                ),
                section=cast(
                    Literal["action", "bonus_action"],
                    section,
                ),
            )
            for action in actions
        )
    return tuple(declarations)


def _display_name(name: str) -> str:
    return re.sub(r"\s*\{@[^}]+\}", "", name).strip()


def _attack_definition(
    action: BestiaryActionSchema,
    capability: schema.AttackCapabilitySchema,
) -> domain.AttackActionDefinition:
    target = compile_target(capability.target)
    hit = compile_outcome(capability.hit)
    compiled = shared_domain.CapabilityDefinition(
        target=target,
        resolution=shared_domain.AttackResolution(
            modes=tuple(capability.attack_modes),
            attack_bonus=shared_domain.FixedAttackBonus(capability.attack_bonus),
            hit=hit,
        ),
    )
    grant, resource_pool = _grant(action.name, compiled, capability.resource)
    return domain.AttackActionDefinition(
        name=action.name,
        attack_modes=tuple(capability.attack_modes),
        attack_bonus=capability.attack_bonus,
        target=target,
        reach_feet=capability.reach_feet,
        range_normal_feet=capability.range_normal_feet,
        range_long_feet=capability.range_long_feet,
        hit=hit.effects,
        grant=grant,
        resource_pool=resource_pool,
    )


def _parse_tagged_attack(
    action: BestiaryActionSchema,
) -> domain.AttackActionDefinition | None:
    if not action.entries or not isinstance(action.entries[0], str):
        return None
    entry = action.entries[0]
    attack_tag = re.search(r"\{@atk(?:r)?\s+([^}]+)\}", entry)
    hit = re.search(r"\{@hit\s+([+-]?\d+)\}", entry)
    damage = re.search(
        r"\{@damage\s+(\d+d\d+)(?:\s*\+\s*(\d+))?\}",
        entry,
    )
    damage_type = re.search(
        r"\{@damage[^}]+\}\)?\s*([A-Za-z]+)\s+damage",
        entry,
    )
    if attack_tag is None or hit is None or damage is None or damage_type is None:
        return None
    attack_modes = _parse_attack_modes(attack_tag.group(1))
    if not attack_modes:
        return None
    reach = re.search(r"reach\s+(\d+)\s*ft", entry)
    attack_range = re.search(r"range\s+(\d+)\/(\d+)\s*ft", entry)
    return domain.AttackActionDefinition(
        name=action.name,
        attack_modes=attack_modes,
        attack_bonus=int(hit.group(1)),
        target=shared_domain.CapabilityTarget(kind="creature"),
        reach_feet=int(reach.group(1)) if reach is not None else None,
        range_normal_feet=(
            int(attack_range.group(1)) if attack_range is not None else None
        ),
        range_long_feet=(
            int(attack_range.group(2)) if attack_range is not None else None
        ),
        hit=(
            shared_domain.DamageEffect(
                dice=damage.group(1),
                bonus=int(damage.group(2) or 0),
                damage_type=damage_type.group(1).lower(),
            ),
        ),
    )


def _parse_attack_modes(value: str) -> tuple[str, ...]:
    modes: list[str] = []
    for token in value.split(","):
        token = token.strip()
        if "m" in token and "melee" not in modes:
            modes.append("melee")
        if "r" in token and "ranged" not in modes:
            modes.append("ranged")
    return tuple(modes)


def _repeat_save(value: schema.RepeatSaveSchema) -> shared_domain.RepeatSave:
    return shared_domain.RepeatSave(
        trigger=value.trigger,
        interval_amount=value.interval_amount,
        interval_unit=value.interval_unit,
        distance_from_source_feet=value.distance_from_source_feet,
        effects_end_on_success=value.effects_end_on_success,
        automatic_success_after=compile_duration(value.automatic_success_after),
    )


def _resource_pool(
    pool_id: str,
    value: schema.ActionResourceSchema | None,
) -> shared_domain.ResourcePoolDefinition | None:
    if value is None:
        return None
    if isinstance(value, schema.UsesResourceSchema):
        return shared_domain.LimitedUsePool(
            id=pool_id,
            maximum=value.maximum,
            refresh=value.reset,
        )
    return shared_domain.RechargePool(
        id=pool_id,
        die_sides=int(value.die.removeprefix("d")),
        minimum=value.minimum,
    )


def _spell_option(
    spell: schema.SpellOptionSchema,
    catalog: "SpellCatalog | None",
) -> domain.SpellOption:
    resolved = None
    if catalog is not None:
        from srd_arena.content.spells import build_spell

        resolved = build_spell(spell.name, spell.source, catalog)
    pool = None
    cost = None
    if isinstance(spell.uses, int):
        pool_id = f"stat_block_spell:{spell.name}"
        pool = shared_domain.LimitedUsePool(
            id=pool_id,
            maximum=spell.uses,
            refresh="day",
        )
        cost = shared_domain.PoolUseCost(pool_id)
    grant = None
    if (
        resolved is not None
        and resolved.definition is not None
        and resolved.activation is not None
    ):
        grant = shared_domain.CapabilityGrant(
            id=f"stat_block_spell:{spell.name}",
            definition=resolved.definition,
            activation=resolved.activation,
            cost=cost,
        )
    return domain.SpellOption(
        name=spell.name,
        source=spell.source,
        cast_level=spell.cast_level,
        uses=spell.uses,
        resource_pool=pool,
        spell=resolved,
        grant=grant,
    )


def _grant(
    action_name: str,
    definition: shared_domain.CapabilityDefinition,
    resource: schema.ActionResourceSchema | None,
) -> tuple[
    shared_domain.CapabilityGrant,
    shared_domain.ResourcePoolDefinition | None,
]:
    if resource is None:
        return (
            shared_domain.CapabilityGrant(
                id=action_name,
                definition=definition,
                activation="action",
            ),
            None,
        )
    pool_id = f"stat_block_action:{action_name}"
    pool = _resource_pool(pool_id, resource)
    assert pool is not None
    return (
        shared_domain.CapabilityGrant(
            id=action_name,
            definition=definition,
            activation="action",
            cost=shared_domain.PoolUseCost(pool_id),
        ),
        pool,
    )
