from __future__ import annotations

from typing import TYPE_CHECKING

from ...creatures import Creature
from ...creatures import can_grapple
from ...rolls.dice import resolve_d20
from ...effects.results import EffectResult
from ...effects.application import condition_from_effect_with_origin
from .attack_resolution import has_free_hand
from ..behaviors import is_adjacent as _is_adjacent
from ..models import EncounterAction, EncounterProgress

if TYPE_CHECKING:
    from ..encounter import EncounterState


def _roll_die(sides: int) -> int:
    from .. import encounter as encounter_module

    return encounter_module.roll_die(sides)


def apply_action(
    self: EncounterState,
    action: EncounterAction,
) -> EncounterProgress:
    decision = self.current_decision()
    actor = self.creatures[decision.creature_ref].creature
    if action.creature_ref != decision.creature_ref:
        raise ValueError(
            f"Action '{action.id}' belongs to '{action.creature_ref}', "
            f"not current decision actor '{decision.creature_ref}'."
        )
    if self._creature_controller(decision.creature_ref) != "external":
        raise RuntimeError(
            "External action requested for a scripted-controlled creature."
        )
    if decision.kind == "reroll_dice":
        progress = self._apply_damage_reroll_action(actor, action, decision)
        return self.turn_engine.continue_after_interrupt(self, progress)
    if decision.kind == "reaction":
        progress = self._apply_reaction_action(actor, action, decision)
        return self.turn_engine.continue_after_interrupt(self, progress)
    return self.turn_engine.apply_selected_action(
        self,
        action,
        decision,
    )


def resolve_grapple_action(
    self: EncounterState,
    actor: Creature,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    creature_ref = self.current_decision().creature_ref
    creature_state = self.creatures[creature_ref]
    if creature_state.actions_remaining <= 0 and creature_state.attacks_remaining <= 0:
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
    if not has_free_hand(actor):
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
    if not can_grapple(target.creature.size, actor.size):
        progress.messages.append(("system", "The target is too large to grapple."))
        return

    if creature_state.attacks_remaining == 0:
        self._consume_action(allow_magic=False)
        creature_state.attacks_remaining = max(
            0,
            actor.combat_profile.attacks_per_attack_action - 1,
        )
    else:
        creature_state.attacks_remaining -= 1

    player_roll = resolve_d20(
        modifier=actor.get_modifier(actor.attributes.strength), roller=_roll_die
    )
    target_roll = resolve_d20(
        modifier=target.creature.get_modifier(target.creature.attributes.strength),
        roller=_roll_die,
    )
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
        progress.messages.append(
            ("system", f"{actor.name} fails to grapple {target_label}.")
        )
        progress.events.append(
            self._event(
                "action_resolved",
                creature_ref=creature_ref,
                action_id=action_id,
                data={"kind": "grapple", "success": False},
            )
        )
        return

    progress.messages.append(("system", f"{actor.name} grapples {target_label}."))
    progress.messages.append(("system", f"{target_label} is grappled."))
    self._apply_grapple(
        condition_from_effect_with_origin(
            EffectResult(
                kind="apply_condition",
                target_ref=target_ref,
                data={
                    "condition": "grappled",
                    "source_ref": creature_ref,
                    "source_label": actor.name,
                    "source_kind": "action",
                    "definition_id": "grapple",
                },
            ),
            origin_id=action_id,
        )
    )
    progress.events.append(
        self._event(
            "action_resolved",
            creature_ref=creature_ref,
            action_id=action_id,
            data={"kind": "grapple", "success": True, "target_ref": target_ref},
        )
    )
