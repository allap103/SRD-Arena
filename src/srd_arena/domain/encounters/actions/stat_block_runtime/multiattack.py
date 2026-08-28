"""Multiattack planning and turn-state setup for stat-block actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....creatures import Creature, MultiattackInvocation, MultiattackStep
from ....creatures.stat_block_actions import AttackActionDefinition
from ...attack_economy import begin_attack_action, clear_attack_action
from ...encounter_models.actions import EncounterAction
from ...encounter_models.resolution import EncounterProgress

if TYPE_CHECKING:
    from ...encounter import EncounterState


def executable_multiattack_sequence(
    creature: Creature,
) -> tuple[MultiattackInvocation, ...] | None:
    """Return the sole deterministic sequence, if the first plan has one.

    >>> from types import SimpleNamespace
    >>> from ....capabilities import CapabilityTarget, DamageEffect
    >>> from ....creatures import Multiattack, MultiattackPlan
    >>> bite = MultiattackInvocation("stat_block_action", "Bite")
    >>> attack = AttackActionDefinition(
    ...     "Bite", ("melee",), 5, CapabilityTarget("creature"),
    ...     5, None, None, (DamageEffect("1d8", 3, "piercing"),),
    ... )
    >>> creature = SimpleNamespace(
    ...     multiattack=Multiattack((MultiattackPlan((MultiattackStep((bite,),),)),)),
    ...     stat_block_actions={"Bite": attack},
    ... )
    >>> [entry.name for entry in executable_multiattack_sequence(creature) or ()]
    ['Bite']
    """
    plans = executable_multiattack_slot_plans(creature)
    if not plans or any(len(slot.options) != 1 for slot in plans[0]):
        return None
    return tuple(slot.options[0] for slot in plans[0])


def executable_multiattack_slot_plans(
    creature: Creature,
) -> tuple[tuple[MultiattackStep, ...], ...]:
    """Build executable multiattack plans from the creature's attack actions.

    >>> from types import SimpleNamespace
    >>> executable_multiattack_slot_plans(
    ...     SimpleNamespace(multiattack=None, stat_block_actions={})
    ... )
    ()
    """
    if creature.multiattack is None:
        return ()
    return creature.multiattack.executable_slot_plans(
        {
            action.name
            for action in creature.stat_block_actions.values()
            if isinstance(action, AttackActionDefinition)
        }
    )


def resolve_multiattack_action(
    state: EncounterState,
    creature: Creature,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    """Consume an action and queue the selected multiattack plan's slots.

    >>> from types import SimpleNamespace
    >>> from ....capabilities import CapabilityTarget, DamageEffect
    >>> from ....creatures import Multiattack, MultiattackPlan
    >>> bite = MultiattackInvocation("stat_block_action", "Bite")
    >>> attack = AttackActionDefinition(
    ...     "Bite", ("melee",), 5, CapabilityTarget("creature"),
    ...     5, None, None, (DamageEffect("1d8", 3, "piercing"),),
    ... )
    >>> creature = SimpleNamespace(
    ...     name="Wolf",
    ...     multiattack=Multiattack((MultiattackPlan((MultiattackStep((bite,),),)),)),
    ...     stat_block_actions={"Bite": attack},
    ... )
    >>> creature_state = SimpleNamespace(
    ...     actions_remaining=1, attacks_remaining=0,
    ...     attack_action_base_attacks=0, attack_action_attacks_used=0,
    ...     pending_multiattack=[],
    ... )
    >>> state = SimpleNamespace(
    ...     current_decision=lambda: SimpleNamespace(creature_ref="wolf"),
    ...     creatures={"wolf": creature_state},
    ...     _consume_action=lambda **kwargs: None,
    ...     combat_rules=SimpleNamespace(
    ...         attack_limit=lambda state, ref, base: SimpleNamespace(value=base)
    ...     ),
    ...     _event=lambda *args, **kwargs: kwargs,
    ... )
    >>> progress = EncounterProgress()
    >>> resolve_multiattack_action(
    ...     state, creature, EncounterAction("Multiattack", "multiattack", "0"),
    ...     progress, "action-1",
    ... )
    >>> (creature_state.attacks_remaining, progress.messages)
    (1, [('system', 'Wolf begins Multiattack.')])
    """
    creature_ref = state.current_decision().creature_ref
    creature_state = state.creatures[creature_ref]
    if creature_state.actions_remaining <= 0 or creature_state.attacks_remaining > 0:
        raise RuntimeError("No Action remains to make a Multiattack.")
    plans = executable_multiattack_slot_plans(creature)
    selected_plan = (
        int(action.value)
        if isinstance(action.value, str) and action.value.isdigit()
        else 0
    )
    if selected_plan >= len(plans):
        raise RuntimeError("This creature has no executable Multiattack plan.")
    slots = plans[selected_plan]
    state._consume_action(allow_magic=False)
    clear_attack_action(creature_state)
    creature_state.pending_multiattack = list(slots)
    begin_attack_action(
        state,
        creature_ref,
        base_attacks=len(slots),
    )
    progress.messages.append(("system", f"{creature.name} begins Multiattack."))
    progress.events.append(
        state._event(
            "action_resolved",
            creature_ref=creature_ref,
            action_id=action_id,
            data={
                "kind": "multiattack",
                "slots": [
                    [invocation.name for invocation in slot.options] for slot in slots
                ],
            },
        )
    )
