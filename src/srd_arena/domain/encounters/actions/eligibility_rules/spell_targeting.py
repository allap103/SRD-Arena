"""Connect spell mechanics to source-aware encounter targeting rules."""

from srd_arena.domain.spells.definitions import Spell
from srd_arena.domain.spells.rules import (
    spell_can_damage_targets,
    spell_uses_attack_roll,
)

from ...encounter_models.actions import CreatureRef
from ...rule_queries.context import ConditionRuleQueryContext
from ...rule_queries.permissions import TargetingKind, target_eligibility
from .models import ActionEligibility


def spell_target_eligibility(
    state: ConditionRuleQueryContext,
    actor_ref: CreatureRef,
    target_ref: CreatureRef,
    spell: Spell,
) -> ActionEligibility:
    """Return Charmed-style restrictions relevant to one spell target.

    A spell attack remains an attack even when it deals no damage. Other spells
    are prohibited by Charmed only when they can damage the charmer; beneficial
    and non-damaging magic remains legal under the SRD 5.2 wording.
    """

    if spell_uses_attack_roll(spell):
        kind = TargetingKind.ATTACK
    elif spell_can_damage_targets(spell):
        kind = TargetingKind.DAMAGING_MAGICAL_EFFECT
    else:
        return ActionEligibility()
    return target_eligibility(state, actor_ref, target_ref, kind)
