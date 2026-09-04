"""Discover, activate, and execute persistent-effect retargeting."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from ..encounter_models.actions import (
    ActionCost,
    EffectRetargetSelection,
    EncounterAction,
)
from ..encounter_models.resolution import EncounterProgress
from ..participants import creatures_are_opponents
from ..rule_queries.obstructions import cover_between
from ..spatial import creature_distance
from ..state_runtime import create_event

if TYPE_CHECKING:
    from ..encounter import EncounterState


def mark_retargetable_effects_for_defeat(
    state: EncounterState,
    target_ref: str,
) -> None:
    """Arm active effects whose current target was just defeated."""

    for index, effect in enumerate(state.ongoing_effects):
        retargeting = effect.lifecycle.retarget_on_defeat
        if retargeting is None or target_ref not in effect.target_refs:
            continue
        state.ongoing_effects[index] = replace(
            effect,
            lifecycle=replace(
                effect.lifecycle,
                retarget_on_defeat=replace(
                    retargeting,
                    defeated_target_ref=target_ref,
                    defeated_round=state.round.number,
                    defeated_turn_index=state.turn.index,
                ),
            ),
        )


def effect_retarget_actions(
    state: EncounterState,
    actor_ref: str,
) -> list[EncounterAction]:
    """Return legal replacement targets for effects owned by this actor."""

    actions: list[EncounterAction] = []
    for effect in state.ongoing_effects:
        source = effect.identity.source
        retargeting = effect.lifecycle.retarget_on_defeat
        if source.applied_by_ref != actor_ref or retargeting is None:
            continue
        if retargeting.defeated_target_ref is None or not _is_later_turn(
            state,
            retargeting.defeated_round,
            retargeting.defeated_turn_index,
        ):
            continue
        for target_ref, target in state.creatures.items():
            if not target.is_alive or not _target_is_legal(
                state,
                actor_ref,
                target_ref,
                range_feet=retargeting.range_feet,
                line_of_sight=retargeting.line_of_sight,
                disposition=retargeting.disposition,
            ):
                continue
            actions.append(
                EncounterAction(
                    f"Move {effect.label or 'effect'} to {target.creature.name}",
                    "retarget_effect",
                    EffectRetargetSelection(effect.identity.id, target_ref),
                    id=(
                        f"{actor_ref}-retarget-{effect.identity.id.replace(':', '-')}-"
                        f"{target_ref.replace(':', '-')}"
                    ),
                    creature_ref=actor_ref,
                    cost=ActionCost(bonus_action=1),
                )
            )
    return actions


def execute_effect_retarget(
    state: EncounterState,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> bool:
    """Move one armed effect after revalidating its selected target."""

    if action.kind != "retarget_effect":
        return False
    selection = action.value
    if not isinstance(selection, EffectRetargetSelection):
        raise ValueError("Effect retargeting requires a typed selection.")
    effect = next(
        (
            candidate
            for candidate in state.ongoing_effects
            if candidate.identity.id == selection.effect_id
        ),
        None,
    )
    actor_ref = state.current_decision().creature_ref
    if effect is None or effect.identity.source.applied_by_ref != actor_ref:
        raise ValueError("The selected ongoing effect is no longer available.")
    retargeting = effect.lifecycle.retarget_on_defeat
    if (
        retargeting is None
        or retargeting.defeated_target_ref is None
        or not _is_later_turn(
            state,
            retargeting.defeated_round,
            retargeting.defeated_turn_index,
        )
        or not _target_is_legal(
            state,
            actor_ref,
            selection.target_ref,
            range_feet=retargeting.range_feet,
            line_of_sight=retargeting.line_of_sight,
            disposition=retargeting.disposition,
        )
    ):
        raise ValueError("The selected replacement target is no longer legal.")
    state.active_bonus_action_available = False
    updated = replace(
        effect,
        target_refs=(selection.target_ref,),
        lifecycle=replace(
            effect.lifecycle,
            retarget_on_defeat=replace(
                retargeting,
                defeated_target_ref=None,
                defeated_round=None,
                defeated_turn_index=None,
            ),
        ),
    )
    state.ongoing_effects = [
        updated if candidate.identity.id == effect.identity.id else candidate
        for candidate in state.ongoing_effects
    ]
    target = state.creatures[selection.target_ref].creature
    label = effect.label or "Effect"
    progress.messages.append(
        (
            "system",
            f"{state.creatures[actor_ref].creature.name} moves {label} to {target.name}.",
        )
    )
    progress.events.append(
        create_event(
            state,
            "effect_retargeted",
            creature_ref=actor_ref,
            action_id=action_id,
            data={
                "effect_id": effect.identity.id,
                "previous_target_ref": retargeting.defeated_target_ref,
                "target_ref": selection.target_ref,
            },
        )
    )
    return True


def _is_later_turn(
    state: EncounterState,
    defeated_round: int | None,
    defeated_turn_index: int | None,
) -> bool:
    return (state.round.number, state.turn.index) != (
        defeated_round,
        defeated_turn_index,
    )


def _target_is_legal(
    state: EncounterState,
    source_ref: str,
    target_ref: str,
    *,
    range_feet: int | None,
    line_of_sight: bool,
    disposition: str,
) -> bool:
    target = state.creatures.get(target_ref)
    if target is None or not target.is_alive or target_ref == source_ref:
        return False
    is_opponent = creatures_are_opponents(state, source_ref, target_ref)
    if disposition == "enemy" and not is_opponent:
        return False
    if disposition == "ally" and is_opponent:
        return False
    if range_feet is not None:
        maximum = int(state.definition.grid.distance_from_feet(range_feet, minimum=1))
        if creature_distance(state, source_ref, target_ref) > maximum:
            return False
    return (
        not line_of_sight
        or cover_between(
            state,
            source_ref,
            target_ref,
        ).has_line_of_effect
    )
