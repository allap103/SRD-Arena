"""Provide execution support for the actions package."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...creatures import Creature, can_grapple
from ...effects.application import condition_from_effect_with_origin
from ...effects.results import EffectResult
from ...rolls.dice import resolve_d20
from ..attack_economy import spend_attack
from ..behaviors import is_adjacent as _is_adjacent
from ..models import EncounterAction, EncounterProgress
from .attack_resolution import has_free_hand

if TYPE_CHECKING:
    from ..encounter import EncounterState


def _roll_die(sides: int) -> int:
    from .. import encounter as encounter_module

    return encounter_module.roll_die(sides)


def resolve_grapple_action(
    self: EncounterState,
    actor: Creature,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    """Resolve grapple action."""

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

    spend_attack(
        self,
        creature_ref,
        base_attacks=actor.combat_profile.attacks_per_attack_action,
    )

    actor_roll_rules = self.combat_rules.roll_modifiers(
        self,
        creature_ref,
        "ability_check",
        ability="strength",
    )
    target_roll_rules = self.combat_rules.roll_modifiers(
        self,
        target_ref,
        "ability_check",
        ability="strength",
    )
    player_roll = resolve_d20(
        modifier=(
            actor.get_modifier(actor.attributes.strength)
            + actor_roll_rules.resolve_modifier(_roll_die)
        ),
        mode=actor_roll_rules.mode,
        roller=_roll_die,
    )
    target_roll = resolve_d20(
        modifier=(
            target.creature.get_modifier(target.creature.attributes.strength)
            + target_roll_rules.resolve_modifier(_roll_die)
        ),
        mode=target_roll_rules.mode,
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
