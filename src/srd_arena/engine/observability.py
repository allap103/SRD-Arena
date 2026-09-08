"""Define which conditions and effects are visually identifiable to opponents."""

from enum import StrEnum
from types import MappingProxyType

from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.effects.runtime import OngoingEffect


class Observability(StrEnum):
    """Classify when a rules state may enter opponent knowledge."""

    OBVIOUS = "obvious"
    AFTER_TRIGGER = "observable_after_trigger"
    HIDDEN = "hidden"


CONDITION_OBSERVABILITY = MappingProxyType(
    {
        Condition.BLINDED: Observability.OBVIOUS,
        Condition.CHARMED: Observability.HIDDEN,
        Condition.DEAFENED: Observability.AFTER_TRIGGER,
        Condition.EXHAUSTION: Observability.AFTER_TRIGGER,
        Condition.FRIGHTENED: Observability.AFTER_TRIGGER,
        Condition.GRAPPLED: Observability.OBVIOUS,
        Condition.INCAPACITATED: Observability.OBVIOUS,
        Condition.INVISIBLE: Observability.OBVIOUS,
        Condition.PARALYZED: Observability.OBVIOUS,
        Condition.PETRIFIED: Observability.OBVIOUS,
        Condition.POISONED: Observability.AFTER_TRIGGER,
        Condition.PRONE: Observability.OBVIOUS,
        Condition.RESTRAINED: Observability.OBVIOUS,
        Condition.STUNNED: Observability.OBVIOUS,
        Condition.UNCONSCIOUS: Observability.OBVIOUS,
    }
)

EFFECT_OBSERVABILITY = MappingProxyType(
    {
        "armor_of_agathys": Observability.OBVIOUS,
        "rage": Observability.OBVIOUS,
        "slow": Observability.OBVIOUS,
        "stinking_cloud": Observability.OBVIOUS,
    }
)


def condition_observability(condition: Condition) -> Observability:
    """Return the explicit opponent-observability policy for a condition."""

    return CONDITION_OBSERVABILITY[condition]


def effect_observability(effect: OngoingEffect) -> Observability:
    """Return the explicit opponent-observability policy for an ongoing effect."""

    if effect.obscures_vision:
        return Observability.OBVIOUS
    return EFFECT_OBSERVABILITY.get(
        effect.identity.source.definition_id.casefold().replace("-", "_"),
        Observability.HIDDEN,
    )
