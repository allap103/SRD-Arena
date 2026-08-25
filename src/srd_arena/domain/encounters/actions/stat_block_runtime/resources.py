"""Runtime resource handling for authored stat-block actions."""

from __future__ import annotations

from ....capabilities import RechargePool
from ....creatures import Creature
from .rolls import roll_die


def stat_block_action_resource_available(
    creature: Creature,
    action_name: str,
) -> bool:
    """Return whether an authored action's resource permits another use."""
    definition = creature.stat_block_actions.get(action_name)
    resource_pool = getattr(definition, "resource_pool", None)
    if resource_pool is None:
        return True
    return creature.stat_block_action_resources.get(action_name, 0) > 0


def consume_stat_block_action_resource(
    creature: Creature,
    action_name: str,
) -> None:
    """Consume one use of an authored action when it has a resource pool."""
    if not stat_block_action_resource_available(creature, action_name):
        raise RuntimeError(f"'{action_name}' has no uses remaining.")
    if action_name in creature.stat_block_action_resources:
        creature.stat_block_action_resources[action_name] -= 1


def recharge_stat_block_actions(creature: Creature) -> None:
    """Roll recharge pools that are empty at the start of a turn."""
    for name, definition in creature.stat_block_actions.items():
        resource_pool = getattr(definition, "resource_pool", None)
        if not isinstance(resource_pool, RechargePool):
            continue
        if creature.stat_block_action_resources.get(name, 1) > 0:
            continue
        if roll_die(resource_pool.die_sides) >= resource_pool.minimum:
            creature.stat_block_action_resources[name] = 1
