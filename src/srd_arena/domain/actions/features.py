from __future__ import annotations

from typing import TYPE_CHECKING

from ..creatures.feature_rules.actions import (
    resolve_feature_action as _resolve_feature_action_impl,
)
from ..creatures import Creature
from ..encounters.models import EncounterProgress

if TYPE_CHECKING:
    from ..encounters.encounter import EncounterState


def _roll_dice(count: int, sides: int) -> int:
    from ..encounters import encounter as encounter_module

    return encounter_module.roll_dice(count, sides)


def resolve_feature_action(
    self: EncounterState,
    player: Creature,
    feature_id: str,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    feature_action = player.combat_profile.feature_actions.get(feature_id)
    if feature_action is None:
        progress.messages.append(("system", f"{feature_id} is not implemented yet."))
        progress.events.append(
            self._event(
                "action_resolved",
                actor_ref="player",
                action_id=action_id,
                data={"kind": "feature", "feature_id": feature_id, "success": False},
            )
        )
        return
    if feature_action.economy == "bonus_action" and not self.player_bonus_action_available:
        progress.messages.append(("system", "You have already used your Bonus Action."))
        progress.events.append(
            self._event(
                "action_resolved",
                actor_ref="player",
                action_id=action_id,
                data={"kind": "feature", "feature_id": feature_id, "success": False},
            )
        )
        return
    if feature_action.economy == "action" and self.player_actions_remaining <= 0:
        progress.messages.append(("system", "You have already used your Action."))
        progress.events.append(
            self._event(
                "action_resolved",
                actor_ref="player",
                action_id=action_id,
                data={"kind": "feature", "feature_id": feature_id, "success": False},
            )
        )
        return
    if feature_action.economy == "reaction" and not self.player_reaction_available:
        progress.messages.append(("system", "You have already used your Reaction."))
        progress.events.append(
            self._event(
                "action_resolved",
                actor_ref="player",
                action_id=action_id,
                data={"kind": "feature", "feature_id": feature_id, "success": False},
            )
        )
        return

    uses_remaining = player.feature_uses_remaining.get(feature_id, 0)
    if uses_remaining <= 0:
        progress.messages.append(("system", f"You have no uses of {feature_action.label} remaining."))
        progress.events.append(
            self._event(
                "action_resolved",
                actor_ref="player",
                action_id=action_id,
                data={"kind": "feature", "feature_id": feature_id, "success": False},
            )
        )
        return

    result = _resolve_feature_action_impl(player, feature_id, _roll_dice)
    if result is None:
        progress.messages.append(("system", f"{feature_action.label} is not implemented yet."))
        progress.events.append(
            self._event(
                "action_resolved",
                actor_ref="player",
                action_id=action_id,
                data={"kind": "feature", "feature_id": feature_id, "success": False},
            )
        )
        return

    if feature_action.economy == "bonus_action":
        self.player_bonus_action_available = False
    elif feature_action.economy == "action":
        self._consume_action(allow_magic=False)
        self.player_attacks_remaining = 0
    elif feature_action.economy == "reaction":
        self.player_reaction_available = False

    progress.messages.extend(result.messages)
    granted_actions = result.details.get("grant_actions", 0)
    if isinstance(granted_actions, int) and granted_actions > 0:
        self.player_actions_remaining += granted_actions
    healing_effect = next((effect for effect in result.effects if effect.kind == "healing"), None)
    healing_data = healing_effect.data if healing_effect is not None else {}
    healing_roll_detail = healing_data.get("roll", {})
    target_ref = healing_effect.target_ref if healing_effect is not None else "player"
    target_label = healing_data.get("target_label", player.name)
    healing = healing_data.get("amount", 0)
    progress.events.append(
        self._event(
            "feature_used",
            actor_ref="player",
            action_id=action_id,
            data={
                "kind": "feature",
                "feature_id": result.capability_id,
                "feature_name": result.capability_name,
                "target_ref": target_ref,
                "target_label": target_label,
                "success": True,
                "healing": healing,
                "healing_roll_detail": healing_roll_detail,
                "uses_remaining": result.resource_updates.get(feature_id),
                "granted_actions": granted_actions if isinstance(granted_actions, int) else 0,
                "effects": [
                    {
                        "kind": effect.kind,
                        "target_ref": effect.target_ref,
                        "success": effect.success,
                        "data": effect.data,
                    }
                    for effect in result.effects
                ],
            },
        )
    )
