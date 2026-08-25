from __future__ import annotations

from typing import TYPE_CHECKING

from ....creatures import Creature
from ...models import ActionCost, EncounterAction

if TYPE_CHECKING:
    from ...encounter import EncounterState


def available_feature_actions(
    self: EncounterState,
    creature: Creature,
) -> list[EncounterAction]:
    creature_ref = self.current_decision().creature_ref
    actions: list[EncounterAction] = []
    for feature_id, definition in creature.combat_profile.feature_actions.items():
        if definition.economy == "reaction":
            continue
        action_cost = ActionCost(
            bonus_action=1 if definition.economy == "bonus_action" else 0,
            action=1 if definition.economy == "action" else 0,
            reaction=1 if definition.economy == "reaction" else 0,
        )
        actions.append(
            EncounterAction(
                definition.label,
                "feature",
                feature_id,
                id=f"{creature_ref}-feature-{feature_id.replace('_', '-')}",
                creature_ref=creature_ref,
                cost=action_cost,
            )
        )
    return actions


def feature_action_available(self: EncounterState, actor: Creature, definition) -> bool:
    if definition.economy == "bonus_action" and not self.active_bonus_action_available:
        return False
    if definition.economy == "action" and self.active_actions_remaining <= 0:
        return False
    if definition.economy == "reaction" and not self.combat_rules.reaction_eligibility(
        self,
        self.current_decision().creature_ref,
        "feature",
    ).allowed:
        return False
    return actor.feature_uses_remaining.get(definition.feature_id, 0) > 0
