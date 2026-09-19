"""Define typed recovery boundaries and report restored creature resources."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from srd_arena.domain.capabilities import LimitedUsePool

if TYPE_CHECKING:
    from .model import Creature


class RestType(StrEnum):
    """Name the rest boundaries that can restore creature resources."""

    SHORT = "short_rest"
    LONG = "long_rest"


@dataclass(frozen=True)
class ResourceRecovery:
    """Report one addressed resource counter changed by a completed rest.

    >>> recovery = ResourceRecovery("feature:rage", 0, 1)
    >>> recovery.amount
    1
    """

    resource_id: str
    previous: int
    current: int

    @property
    def amount(self) -> int:
        """Return the number of uses restored by this recovery."""

        return self.current - self.previous


def spend_feature_use(creature: Creature, feature_id: str) -> int:
    """Spend one use of an addressed creature feature."""

    remaining = creature.feature_uses_remaining.get(feature_id, 0)
    if remaining <= 0:
        raise RuntimeError(f"Feature '{feature_id}' has no uses remaining.")
    creature.feature_uses_remaining[feature_id] = remaining - 1
    return creature.feature_uses_remaining[feature_id]


def recover_resources(
    creature: Creature,
    rest: RestType,
) -> tuple[ResourceRecovery, ...]:
    """Restore every creature resource affected by a completed rest."""

    refreshes = {rest.value}
    if rest is RestType.LONG:
        refreshes.add(RestType.SHORT.value)
    recoveries = (
        list(creature.spellcasting.recover_slots(rest))
        if creature.spellcasting is not None
        else []
    )
    recoveries.extend(_recover_feature_uses(creature, frozenset(refreshes)))
    recoveries.extend(_recover_stat_block_uses(creature, frozenset(refreshes)))
    return tuple(recoveries)


def refresh_daily_resources(creature: Creature) -> tuple[ResourceRecovery, ...]:
    """Restore limited uses whose authored refresh boundary is one day."""

    refreshes = frozenset({"day"})
    recoveries = _recover_feature_uses(creature, refreshes)
    recoveries.extend(_recover_stat_block_uses(creature, refreshes))
    return tuple(recoveries)


def _recover_feature_uses(
    creature: Creature,
    refreshes: frozenset[str],
) -> list[ResourceRecovery]:
    recoveries: list[ResourceRecovery] = []
    for feature_id, maximum in sorted(creature.combat_profile.feature_uses_max.items()):
        rules = creature.combat_profile.feature_recharge.get(feature_id, {})
        matching_rules = [rules[key] for key in sorted(refreshes) if key in rules]
        if not matching_rules:
            continue
        previous = creature.feature_uses_remaining.get(feature_id, maximum)
        current = previous
        for rule in matching_rules:
            current = maximum if rule == "all" else min(current + int(rule), maximum)
        if current == previous:
            continue
        creature.feature_uses_remaining[feature_id] = current
        recoveries.append(
            ResourceRecovery(
                resource_id=f"feature:{feature_id}",
                previous=previous,
                current=current,
            )
        )
    return recoveries


def _recover_stat_block_uses(
    creature: Creature,
    refreshes: frozenset[str],
) -> list[ResourceRecovery]:
    recoveries: list[ResourceRecovery] = []
    for action_name, definition in sorted(creature.stat_block_actions.items()):
        pool = getattr(definition, "resource_pool", None)
        if not isinstance(pool, LimitedUsePool):
            continue
        if pool.refresh not in refreshes:
            continue
        previous = creature.stat_block_action_resources.get(
            action_name,
            pool.maximum,
        )
        if previous >= pool.maximum:
            continue
        creature.stat_block_action_resources[action_name] = pool.maximum
        recoveries.append(
            ResourceRecovery(
                resource_id=pool.id,
                previous=previous,
                current=pool.maximum,
            )
        )
    return recoveries
