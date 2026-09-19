"""Calculate intrinsic Initiative modifiers for creatures."""

from .feature_rules.feats import creature_has_feat
from .model import Creature


def initiative_modifier(creature: Creature) -> int:
    """Return the creature's complete intrinsic Initiative modifier.

    A 2024 stat block may add one or more proficiency bonuses directly. Alert
    separately grants player characters proficiency in Initiative.
    """

    modifier = creature.get_modifier(creature.attributes.dexterity) + (
        creature.statistics.initiative_proficiency_multiplier
        * creature.attributes.proficiency_bonus
    )
    if creature_has_feat(creature, "Alert"):
        modifier += creature.attributes.proficiency_bonus
    return modifier
