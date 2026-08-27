from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

from ..geometry import Position
from .behaviors import build_behavior
from .models import (
    BehaviorContext,
    CreatureRef,
    EncounterAction,
    EncounterCreatureState,
)

if TYPE_CHECKING:
    from .encounter import EncounterState


class ActionSelector(Protocol):
    def select_action(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
        actions: Sequence[EncounterAction],
    ) -> EncounterAction | None: ...


class ExternalActionSelector:
    def select_action(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
        actions: Sequence[EncounterAction],
    ) -> None:
        return None


class ScriptedActionSelector:
    def __init__(self, participant: EncounterCreatureState) -> None:
        self._behavior = build_behavior(participant)
        next(self._behavior)

    def select_action(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
        actions: Sequence[EncounterAction],
    ) -> EncounterAction:
        wait = next(action for action in actions if action.kind == "wait")
        target_ref = self._nearest_opponent(state, creature_ref)
        if target_ref is None:
            return wait
        actor = state.creatures[creature_ref]
        target = state.creatures[target_ref]
        preferred_attack_type = "ranged" if actor.behavior.type == "archer" else "melee"
        matching_attacks = [
            action
            for action in actions
            if action.kind == "attack"
            and action.value == target_ref
            and action.preferred_attack_type == preferred_attack_type
        ]
        command = self._behavior.send(
            BehaviorContext(
                target_position=Position(target.position.x, target.position.y),
                actor_position=Position(actor.position.x, actor.position.y),
                can_attack=bool(matching_attacks),
            )
        )
        if command is None:
            return wait
        if command.kind == "attack":
            multiattack = next(
                (action for action in actions if action.kind == "multiattack"),
                None,
            )
            if multiattack is not None and matching_attacks:
                return multiattack
            return matching_attacks[0] if matching_attacks else wait
        return next(
            (
                action
                for action in actions
                if action.kind == command.kind and action.value == command.value
            ),
            wait,
        )

    def _nearest_opponent(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
    ) -> CreatureRef | None:
        actor_position = state._creature_position(creature_ref)
        opponents = [
            target_ref
            for target_ref in state._living_creature_refs()
            if state._creatures_are_opponents(creature_ref, target_ref)
        ]
        if not opponents:
            return None
        return min(
            opponents,
            key=lambda target_ref: (
                abs(state._creature_position(target_ref).x - actor_position.x)
                + abs(state._creature_position(target_ref).y - actor_position.y)
            ),
        )


def build_action_selector(
    controller: str,
    participant: EncounterCreatureState,
) -> ActionSelector:
    if controller == "external":
        return ExternalActionSelector()
    return ScriptedActionSelector(participant)
