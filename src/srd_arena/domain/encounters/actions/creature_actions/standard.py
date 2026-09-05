"""Execute small encounter-native actions that do not invoke capabilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.effects.rule_effects import OpportunityAttackPrevention
from srd_arena.domain.effects.runtime import (
    EffectPolarity,
    EffectSource,
    EffectSourceKind,
    OngoingEffect,
    RuntimeStateIdentity,
    UntilTurnEnd,
)

from ...attack_economy import clear_attack_action, consume_action
from ...effect_lifecycle.lifecycle_events import resolve_effect_lifecycle_event
from ...encounter_models.actions import EncounterAction
from ...encounter_models.decisions import DecisionFrame
from ...encounter_models.resolution import EncounterProgress
from ...spatial import creatures_are_adjacent
from ...state_runtime import create_event, next_runtime_origin_id
from ..effect_retargeting import execute_effect_retarget
from ..rejections import reject_action

if TYPE_CHECKING:
    from ...encounter import EncounterState


def execute_standard_action(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
    progress: EncounterProgress,
    action_id: str,
) -> bool:
    """Execute encounter-native actions and report whether one was recognized.

    >>> from types import SimpleNamespace
    >>> actor = SimpleNamespace(creature=SimpleNamespace(name="Hero"))
    >>> state = SimpleNamespace(
    ...     creatures={"hero": actor}, event_sequence=1,
    ... )
    >>> progress = EncounterProgress()
    >>> execute_standard_action(
    ...     state, EncounterAction("Wait", "wait"),
    ...     DecisionFrame("turn", "hero", "turn", "active"),
    ...     progress, "wait-1"
    ... )
    True
    >>> (progress.messages[-1], progress.events[-1].data["kind"])
    (('system', 'Hero waits.'), 'wait')
    """

    actor = state.creatures[decision.creature_ref]
    if execute_effect_retarget(state, action, progress, action_id):
        return True
    if action.kind == "disengage":
        if action.cost.bonus_action:
            state.active_bonus_action_available = False
        else:
            consume_action(state, allow_magic=False)
            clear_attack_action(state.active_creature_state)
        effect_id = next_runtime_origin_id(state)
        state.ongoing_effects.append(
            OngoingEffect(
                identity=RuntimeStateIdentity(
                    id=effect_id,
                    source=EffectSource(
                        EffectSourceKind.ACTION,
                        "disengage",
                        applied_by_ref=decision.creature_ref,
                        label="Disengage",
                        origin_id=action_id,
                    ),
                ),
                target_refs=(decision.creature_ref,),
                duration=UntilTurnEnd(
                    decision.creature_ref,
                    state.round.number,
                ),
                polarity=EffectPolarity.BENEFICIAL,
                label="Disengage",
                rule_effects=(OpportunityAttackPrevention(),),
            )
        )
        progress.messages.append(
            (
                "system",
                f"{actor.creature.name} disengages and no longer provokes "
                "Opportunity Attacks this turn.",
            )
        )
        progress.events.append(
            create_event(
                state,
                "action_resolved",
                creature_ref=decision.creature_ref,
                action_id=action_id,
                data={"kind": "disengage", "effect_id": effect_id},
            )
        )
    elif action.kind == "rouse_spell_target":
        if not isinstance(action.value, str):
            reject_action(
                state,
                progress,
                actor_ref=decision.creature_ref,
                action_id=action_id,
                action_kind=action.kind,
                message="Rouse action requires a creature reference.",
                reason_code="target_required",
            )
            return True
        target = state.creatures.get(action.value)
        if target is None or not target.is_alive:
            reject_action(
                state,
                progress,
                actor_ref=decision.creature_ref,
                action_id=action_id,
                action_kind=action.kind,
                message="The target is no longer available.",
                reason_code="target_unavailable",
                details={"target_ref": action.value},
            )
            return True
        if not creatures_are_adjacent(
            state,
            decision.creature_ref,
            action.value,
        ):
            reject_action(
                state,
                progress,
                actor_ref=decision.creature_ref,
                action_id=action_id,
                action_kind=action.kind,
                message="The target is no longer within reach.",
                reason_code="target_out_of_range",
                details={"target_ref": action.value},
            )
            return True
        if not _can_rouse_spell_target(state, action.value):
            reject_action(
                state,
                progress,
                actor_ref=decision.creature_ref,
                action_id=action_id,
                action_kind=action.kind,
                message="That magical stupor is no longer active.",
                reason_code="rouse_unavailable",
                details={"target_ref": action.value},
            )
            return True
        consume_action(state, allow_magic=False)
        resolve_effect_lifecycle_event(
            state,
            "adjacent_creature_wakes_target",
            actor_ref=decision.creature_ref,
            target_ref=action.value,
            progress=progress,
        )
        progress.messages.append(
            (
                "system",
                f"{actor.creature.name} rouses {target.creature.name}.",
            )
        )
        progress.events.append(
            create_event(
                state,
                "action_resolved",
                creature_ref=decision.creature_ref,
                action_id=action_id,
                data={"kind": "rouse_spell_target", "target_ref": action.value},
            )
        )
    elif action.kind == "wait":
        progress.messages.append(("system", f"{actor.creature.name} waits."))
        progress.events.append(
            create_event(
                state,
                "action_resolved",
                creature_ref=decision.creature_ref,
                action_id=action_id,
                data={"kind": "wait"},
            )
        )
    else:
        return False
    return True


def _can_rouse_spell_target(state: EncounterState, target_ref: str) -> bool:
    """Return whether an active effect lets an adjacent creature rouse a target."""

    return any(
        target_ref in effect.target_refs
        and any(
            configured.event == "adjacent_creature_wakes_target"
            for configured in effect.lifecycle.end_events
        )
        for effect in state.ongoing_effects
    )
