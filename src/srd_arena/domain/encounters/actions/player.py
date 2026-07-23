from __future__ import annotations

from typing import TYPE_CHECKING

from ...creatures import Creature
from ...creatures import can_grapple
from ...rolls.dice import resolve_d20
from ...effects.results import EffectResult
from .features import resolve_feature_action as _resolve_feature_action_impl
from .items import resolve_utilize_action as _resolve_utilize_action_impl
from .spellcasting import resolve_spell_action as _resolve_spell_action_impl
from .attack_resolution import has_free_hand
from ..behaviors import is_adjacent as _is_adjacent
from ..models import EncounterAction, EncounterProgress
from ..creature_control import (
    apply_creature_action as _apply_creature_action_impl,
    available_creature_actions as _available_creature_actions_impl,
)

if TYPE_CHECKING:
    from ..encounter import EncounterState


def _roll_die(sides: int) -> int:
    from .. import encounter as encounter_module

    return encounter_module.roll_die(sides)


def apply_action(
    self: EncounterState,
    player: Creature,
    action: EncounterAction,
) -> EncounterProgress:
    decision = self.current_decision()
    if self._creature_controller(decision.creature_ref) != "user":
        raise RuntimeError("User action requested for an AI-controlled creature.")
    if decision.kind == "reroll_dice":
        return self._apply_damage_reroll_action(player, action, decision)
    if decision.kind == "reaction":
        return self._apply_reaction_action(player, action, decision)
    creature = self.creatures[decision.creature_ref].creature
    return self._apply_creature_action(creature, action, decision)

def resolve_grapple_action(
    self: EncounterState,
    player: Creature,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    creature_ref = self.current_decision().creature_ref
    creature_state = self.creatures[creature_ref]
    if self.active_actions_remaining <= 0:
        progress.messages.append(("system", "You have already used your Action."))
        progress.events.append(
            self._event(
                "action_resolved",
                creature_ref=creature_ref,
                action_id=action_id,
                data={"kind": "grapple", "success": False},
            )
        )
        return
    if not isinstance(action.value, str):
        raise ValueError(
            f"Encounter grapple action requires a creature reference, got {action.value!r}."
        )

    target_ref = action.value
    target = self.creatures[target_ref]
    if not target.is_alive:
        progress.messages.append(("system", "The target is no longer available."))
        return
    if not _is_adjacent(creature_state.position, target.position):
        progress.messages.append(("system", "The target is out of reach."))
        return
    if not has_free_hand(player):
        progress.messages.append(("system", "You need a free hand to grapple."))
        progress.events.append(
            self._event(
                "action_resolved",
                creature_ref=creature_ref,
                action_id=action_id,
                data={"kind": "grapple", "success": False},
            )
        )
        return
    if not can_grapple(target.creature.size, player.size):
        progress.messages.append(("system", "The target is too large to grapple."))
        return

    self._consume_action(allow_magic=False)

    player_roll = resolve_d20(modifier=player.get_modifier(player.attributes.strength), roller=_roll_die)
    target_roll = resolve_d20(modifier=target.creature.get_modifier(target.creature.attributes.strength), roller=_roll_die)
    success = player_roll.total >= target_roll.total
    target_label = self._creature_label(target_ref)

    progress.events.append(
        self._event(
            "grapple_resolved",
            creature_ref=creature_ref,
            action_id=action_id,
            data={
                "target_ref": target_ref,
                "target_label": target_label,
                "player_roll": player_roll.total,
                "target_roll": target_roll.total,
                "player_die": player_roll.selected,
                "target_die": target_roll.selected,
                "success": success,
            },
        )
    )

    if not success:
        progress.messages.append(("system", f"{player.name} fails to grapple {target_label}."))
        progress.events.append(
            self._event(
                "action_resolved",
                creature_ref=creature_ref,
                action_id=action_id,
                data={"kind": "grapple", "success": False},
            )
        )
        return

    progress.messages.append(("system", f"{player.name} grapples {target_label}."))
    progress.messages.append(("system", f"{target_label} is grappled."))
    self._apply_effects(
        [
            EffectResult(
                kind="apply_status",
                target_ref=target_ref,
                data={
                    "condition": "grappled",
                    "source_ref": creature_ref,
                    "source_label": player.name,
                },
            ),
            EffectResult(
                kind="apply_status",
                target_ref=creature_ref,
                data={
                    "condition": "grappling",
                    "source_ref": target_ref,
                    "source_label": target.creature.name,
                },
            ),
        ]
    )
    progress.events.append(
        self._event(
            "action_resolved",
            creature_ref=creature_ref,
            action_id=action_id,
            data={"kind": "grapple", "success": True, "target_ref": target_ref},
        )
    )


available_creature_actions = _available_creature_actions_impl
apply_creature_action = _apply_creature_action_impl
resolve_utilize_action = _resolve_utilize_action_impl
resolve_feature_action = _resolve_feature_action_impl
resolve_spell_action = _resolve_spell_action_impl
