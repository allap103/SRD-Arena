"""Project exact combat resources for clients authorized to know them."""

from srd_arena.domain.capabilities import LimitedUsePool, RechargePool
from srd_arena.domain.creatures import Creature

from .observation_models import ResourcePoolObservation, SpellSlotObservation


def observe_spell_slots(creature: Creature) -> tuple[SpellSlotObservation, ...]:
    """Snapshot available slot levels; an empty tuple means no spell slots."""

    spellcasting = creature.spellcasting
    if spellcasting is None:
        return ()
    return tuple(
        SpellSlotObservation(
            level=level,
            remaining=spellcasting.spell_slots_remaining.get(level, maximum),
            maximum=maximum,
        )
        for level, maximum in sorted(spellcasting.spell_slots_max.items())
        if maximum > 0
    )


def observe_resource_pools(
    creature: Creature,
) -> tuple[ResourcePoolObservation, ...]:
    """Project tracked feature and stat-block counters by stable pool identity."""

    resources = [
        ResourcePoolObservation(
            id=f"feature:{feature_id}",
            source_id=feature_id,
            kind="feature_uses",
            remaining=remaining,
            maximum=creature.combat_profile.feature_uses_max[feature_id],
            refresh=tuple(
                sorted(creature.combat_profile.feature_recharge.get(feature_id, {}))
            ),
        )
        for feature_id, remaining in sorted(creature.feature_uses_remaining.items())
    ]
    for action_name, remaining in sorted(creature.stat_block_action_resources.items()):
        definition = creature.stat_block_actions.get(action_name)
        pool = getattr(definition, "resource_pool", None)
        refresh: tuple[str, ...]
        recharge_die_sides: int | None
        recharge_minimum: int | None
        if isinstance(pool, LimitedUsePool):
            maximum = pool.maximum
            refresh = (pool.refresh,)
            recharge_die_sides = None
            recharge_minimum = None
        elif isinstance(pool, RechargePool):
            maximum = 1
            refresh = ("turn_start_recharge",)
            recharge_die_sides = pool.die_sides
            recharge_minimum = pool.minimum
        else:
            raise RuntimeError(
                f"Tracked stat-block resource '{action_name}' has no pool definition."
            )
        resources.append(
            ResourcePoolObservation(
                id=pool.id,
                source_id=action_name,
                kind=pool.kind,
                remaining=remaining,
                maximum=maximum,
                refresh=refresh,
                recharge_die_sides=recharge_die_sides,
                recharge_minimum=recharge_minimum,
            )
        )
    return tuple(resources)
