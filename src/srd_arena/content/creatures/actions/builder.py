import re
from typing import TYPE_CHECKING, Literal, cast

from . import schema
from .multiattack import MultiattackCapabilitySchema
from srd_arena.content.capabilities import (
    AutomaticResolutionSchema,
    CapabilityBuildError,
    build_capability,
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
            definition = build_capability(
                target=capability.target,
                resolution=resolution,
                content=(f"Monster '{stat_block.public_name}' action '{action.name}'"),
            )
            if isinstance(
                resolution,
                schema.SavingThrowActionResolutionSchema,
            ):
                saving_resolution = cast(
                    shared_domain.SavingThrowResolution,
                    definition.resolution,
                )
                difficulty = cast(
                    shared_domain.FixedDifficultyClass,
                    saving_resolution.difficulty,
                )
                grant, resource_pool = _grant(
                    action.name,
                    definition,
                    capability.resource,
                )
                definitions[action.name] = domain.SavingThrowActionDefinition(
                    name=action.name,
                    target=definition.target,
                    ability=saving_resolution.ability,
                    dc=difficulty.value,
                    failure=saving_resolution.failure,
                    success=saving_resolution.success.effects,
                    success_damage=saving_resolution.success_damage,
                    always=saving_resolution.always.effects,
                    grant=grant,
                    resource_pool=resource_pool,
                )
            elif isinstance(resolution, AutomaticResolutionSchema):
                automatic_resolution = cast(
                    shared_domain.AutomaticResolution,
                    definition.resolution,
                )
                grant, resource_pool = _grant(
                    action.name,
                    definition,
                    capability.resource,
                )
                definitions[action.name] = domain.AutomaticActionDefinition(
                    name=action.name,
                    target=definition.target,
                    effects=automatic_resolution.outcome.effects,
                    grant=grant,
                    resource_pool=resource_pool,
                )
            else:
                raise CapabilityBuildError(
                    content=(
                        f"Monster '{stat_block.public_name}' action '{action.name}'"
                    ),
                    location="capability.resolution",
                    mechanic=type(resolution).__name__,
                )
        elif isinstance(capability, schema.SpellcastingCapabilitySchema):
            definitions[action.name] = domain.SpellcastingActionDefinition(
                name=action.name,
                ability=capability.ability,
                spells=tuple(
                    _spell_option(spell, spells) for spell in capability.spells
                ),
                resource_pool=_resource_pool(
                    f"stat_block_action:{action.name}",
                    capability.shared_resource,
                ),
            )
        elif isinstance(capability, MultiattackCapabilitySchema):
            continue
        elif capability is None:
            fallback = _parse_tagged_attack(action)
            if fallback is not None:
                definitions[action.name] = fallback
        else:
            raise CapabilityBuildError(
                content=f"Monster '{stat_block.public_name}' action '{action.name}'",
                location="capability",
                mechanic=type(capability).__name__,
            )
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
                    entry for entry in action.entries if isinstance(entry, str)
                ),
                capability_type=(
                    action.capability.type if action.capability is not None else None
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
    definition = build_capability(
        target=capability.target,
        resolution=capability,
        content=f"Monster action '{action.name}'",
    )
    resolution = cast(shared_domain.AttackResolution, definition.resolution)
    grant, resource_pool = _grant(action.name, definition, capability.resource)
    return domain.AttackActionDefinition(
        name=action.name,
        attack_modes=tuple(capability.attack_modes),
        attack_bonus=capability.attack_bonus,
        target=definition.target,
        reach_feet=capability.reach_feet,
        range_normal_feet=capability.range_normal_feet,
        range_long_feet=capability.range_long_feet,
        hit=resolution.hit.effects,
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

        resolved = build_spell(catalog.find(spell.name, spell.source))
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
