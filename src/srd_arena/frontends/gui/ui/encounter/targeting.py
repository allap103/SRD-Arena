"""Derive frontend targeting modes from application observations."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

from srd_arena.application.api import (
    ActionObservation,
    GameObservation,
)

from .config import TargetSelectionMode


def actions_for_mode(
    actions: Sequence[ActionObservation],
    mode: TargetSelectionMode,
) -> list[ActionObservation]:
    """Return all advertised actions represented by one targeting mode.

    >>> action = ActionObservation(
    ...     "bite-goblin", "Bite", "attack", "wolf",
    ...     preferred_attack_name="Bite", target_ref="goblin",
    ... )
    >>> mode = mode_for_action(action)
    >>> actions_for_mode((action,), mode) == [action]
    True
    """

    return [action for action in actions if mode_for_action(action) == mode]


def selection_modes(
    actions: Sequence[ActionObservation],
) -> dict[TargetSelectionMode, dict[str, ActionObservation]]:
    """Index targetable actions by mode and stable creature reference.

    >>> action = ActionObservation(
    ...     "bite-goblin", "Bite", "attack", "wolf",
    ...     preferred_attack_name="Bite", target_ref="goblin",
    ... )
    >>> modes = selection_modes((action,))
    >>> next(iter(modes.values()))["goblin"] is action
    True
    """

    modes: dict[TargetSelectionMode, dict[str, ActionObservation]] = {}
    for action in actions:
        mode = mode_for_action(action)
        creature_ref = target_creature_ref(action)
        if mode is None or creature_ref is None:
            continue
        modes.setdefault(mode, {})[creature_ref] = action
    return modes


def mode_for_action(action: ActionObservation) -> TargetSelectionMode | None:
    """Describe how the battlefield selects a target for an action.

    >>> action = ActionObservation(
    ...     "bite-goblin", "Bite", "attack", "wolf",
    ...     preferred_attack_name="Bite", target_ref="goblin",
    ... )
    >>> mode_for_action(action)
    TargetSelectionMode(kind='attack', source_trigger_id='Bite', variant_id=None)
    >>> mode_for_action(ActionObservation("wait", "Wait", "wait", "wolf")) is None
    True
    """

    if action.kind == "toggle_spell_target":
        return TargetSelectionMode(
            kind=action.kind,
            source_trigger_id=action.source_trigger_id,
        )
    if action.kind == "spell" and action.source_id is not None:
        return TargetSelectionMode(
            kind=action.kind,
            source_trigger_id=action.source_id,
            variant_id=_spell_slot_variant(action),
        )
    if action.kind == "stat_block" and is_area_stat_block_action(action):
        return TargetSelectionMode(
            kind=action.kind,
            source_trigger_id=action.preferred_attack_name,
        )
    if target_creature_ref(action) is None:
        return None
    return TargetSelectionMode(
        kind=action.kind,
        source_trigger_id=_target_mode_source(action),
    )


def mode_label(
    mode: TargetSelectionMode,
    actions: Sequence[ActionObservation] = (),
) -> str:
    """Return the compact action label for a battlefield targeting mode.

    >>> mode_label(TargetSelectionMode("opportunity_attack"))
    'Opportunity attack'
    >>> mode_label(TargetSelectionMode("attack", "Bite"))
    'Bite'
    """

    if mode.kind == "toggle_spell_target":
        spell_name = _source_label(mode.source_trigger_id, actions)
        return (
            f"Choose {spell_name} targets"
            if spell_name is not None
            else "Choose targets"
        )
    if mode.kind == "spell" and mode.source_trigger_id is not None:
        spell_name = _source_label(mode.source_trigger_id, actions)
        if spell_name is not None:
            if mode.variant_id is not None:
                return f"{spell_name} ({mode.variant_id})"
            return spell_name
    if mode.kind == "opportunity_attack":
        return "Opportunity attack"
    if mode.kind == "grapple":
        return "Grapple"
    if mode.kind == "stat_block" and mode.source_trigger_id is not None:
        return mode.source_trigger_id
    if mode.kind == "attack" and mode.source_trigger_id not in {None, "attack"}:
        assert mode.source_trigger_id is not None
        return mode.source_trigger_id
    return "Attack"


def target_creature_ref(action: ActionObservation | None) -> str | None:
    """Return the directly selectable creature target, if any.

    >>> target_creature_ref(
    ...     ActionObservation("bite", "Bite", "attack", "wolf", target_ref="hero")
    ... )
    'hero'
    >>> target_creature_ref(ActionObservation("wait", "Wait", "wait", "wolf")) is None
    True
    """

    if action is None or action.kind not in {
        "spell",
        "toggle_spell_target",
        "attack",
        "grapple",
        "opportunity_attack",
        "stat_block",
    }:
        return None
    return action.target_ref


def action_for_target_click(
    actions: Sequence[ActionObservation],
    mode: TargetSelectionMode,
    creature_ref: str,
    *,
    remove_allocation: bool = False,
) -> ActionObservation | None:
    """Choose the action represented by a click on a target creature.

    >>> add = ActionObservation(
    ...     "spell-target-goblin-add", "Add Goblin", "toggle_spell_target",
    ...     "mage", source_trigger_id="scorching-ray", target_ref="goblin",
    ... )
    >>> remove = ActionObservation(
    ...     "spell-target-goblin-remove", "Remove Goblin", "toggle_spell_target",
    ...     "mage", source_trigger_id="scorching-ray", target_ref="goblin",
    ... )
    >>> mode = mode_for_action(add)
    >>> action_for_target_click((add, remove), mode, "goblin") is add
    True
    >>> action_for_target_click(
    ...     (add, remove), mode, "goblin", remove_allocation=True
    ... ) is remove
    True
    """

    matching_actions = [
        action
        for action in actions
        if mode_for_action(action) == mode
        and target_creature_ref(action) == creature_ref
    ]
    allocation_suffix = "-remove" if remove_allocation else "-add"
    return next(
        (
            action
            for action in matching_actions
            if action.id.endswith(allocation_suffix)
        ),
        matching_actions[0] if matching_actions and not remove_allocation else None,
    )


def cancel_targeting_action(
    actions: Sequence[ActionObservation],
) -> ActionObservation | None:
    """Return the advertised cancellation action for active targeting.

    >>> cancel = ActionObservation(
    ...     "cancel", "Cancel Fireball", "cancel_spell_targets", "mage"
    ... )
    >>> cancel_targeting_action((cancel,)) is cancel
    True
    >>> cancel_targeting_action(()) is None
    True
    """

    return next(
        (action for action in actions if action.kind == "cancel_spell_targets"),
        None,
    )


def pending_area_action(
    actions: Sequence[ActionObservation],
    mode: TargetSelectionMode | None,
) -> ActionObservation | None:
    """Return the area action represented by the active targeting mode.

    >>> action = ActionObservation(
    ...     "fireball", "Fireball", "spell", "mage", source_id="fireball",
    ...     area_preview={"shape": "radius"},
    ... )
    >>> pending_area_action((action,), TargetSelectionMode("spell", "fireball")) is action
    True
    """

    return pending_area_spell_action(
        actions,
        mode,
    ) or pending_area_stat_block_action(actions, mode)


def pending_area_spell_action(
    actions: Sequence[ActionObservation],
    mode: TargetSelectionMode | None,
) -> ActionObservation | None:
    """Return the advertised spell action currently waiting for an aim point.

    >>> action = ActionObservation(
    ...     "fireball-5", "Fireball (Level 5)", "spell", "mage",
    ...     source_id="fireball", resource_level=5,
    ...     area_preview={"shape": "radius"},
    ... )
    >>> mode = TargetSelectionMode("spell", "fireball", "Level 5")
    >>> pending_area_spell_action((action,), mode) is action
    True
    """

    if mode is None or mode.kind != "spell":
        return None
    return next(
        (
            action
            for action in actions
            if action.kind == "spell"
            and action.source_id == mode.source_trigger_id
            and _spell_slot_variant(action) == mode.variant_id
            and is_area_spell_action(action)
        ),
        None,
    )


def pending_area_stat_block_action(
    actions: Sequence[ActionObservation],
    mode: TargetSelectionMode | None,
) -> ActionObservation | None:
    """Return the stat-block action currently waiting for an aim point.

    >>> action = ActionObservation(
    ...     "breath", "Fire Breath", "stat_block", "dragon",
    ...     preferred_attack_name="Fire Breath", area_preview={"shape": "cone"},
    ... )
    >>> mode = TargetSelectionMode("stat_block", "Fire Breath")
    >>> pending_area_stat_block_action((action,), mode) is action
    True
    """

    if mode is None or mode.kind != "stat_block":
        return None
    return next(
        (
            action
            for action in actions
            if action.kind == "stat_block"
            and action.preferred_attack_name == mode.source_trigger_id
            and is_area_stat_block_action(action)
        ),
        None,
    )


def pending_area_overlay(
    actions: Sequence[ActionObservation],
    mode: TargetSelectionMode | None,
) -> Mapping[str, object] | None:
    """Build the area preview for the action currently being aimed.

    >>> action = ActionObservation(
    ...     "fireball", "Fireball", "spell", "mage", source_id="fireball",
    ...     area_preview={"shape": "radius"},
    ... )
    >>> dict(pending_area_overlay(
    ...     (action,), TargetSelectionMode("spell", "fireball")
    ... ))
    {'shape': 'radius'}
    """

    action = pending_area_action(actions, mode)
    return action.area_preview if action is not None else None


def mode_is_available(
    actions: Sequence[ActionObservation],
    modes: Mapping[TargetSelectionMode, Mapping[str, ActionObservation]],
    pending_mode: TargetSelectionMode | None,
) -> bool:
    """Return whether a selected targeting mode remains advertised.

    >>> mode = TargetSelectionMode("attack", "Bite")
    >>> mode_is_available((), {mode: {}}, mode)
    True
    >>> mode_is_available((), {}, mode)
    False
    """

    if pending_mode is None:
        return False
    if pending_mode in modes:
        return True
    return pending_area_action(actions, pending_mode) is not None


def completed_allocation_action(
    observation: GameObservation,
) -> ActionObservation | None:
    """Return confirmation once a fixed-size target allocation is complete.

    >>> from types import SimpleNamespace
    >>> confirm = ActionObservation(
    ...     "confirm", "Cast Scorching Ray", "confirm_spell_targets", "mage"
    ... )
    >>> targeting = SimpleNamespace(
    ...     require_full_target_count=True,
    ...     selected_target_refs=("a", "b"), maximum_targets=2,
    ... )
    >>> observation = SimpleNamespace(
    ...     encounter=SimpleNamespace(targeting=targeting),
    ...     scene=SimpleNamespace(action_details=(confirm,)),
    ... )
    >>> completed_allocation_action(observation) is confirm
    True
    """

    encounter = observation.encounter
    pending = encounter.targeting if encounter is not None else None
    if (
        pending is None
        or not pending.require_full_target_count
        or len(pending.selected_target_refs) != pending.maximum_targets
    ):
        return None
    return next(
        (
            action
            for action in observation.scene.action_details
            if action.kind == "confirm_spell_targets"
        ),
        None,
    )


def allocation_counts(observation: GameObservation) -> dict[str, int]:
    """Count repeated target allocations for battlefield badges.

    >>> from types import SimpleNamespace
    >>> pending = SimpleNamespace(selected_target_refs=("goblin", "goblin", "ogre"))
    >>> observation = SimpleNamespace(
    ...     encounter=SimpleNamespace(targeting=pending)
    ... )
    >>> allocation_counts(observation)
    {'goblin': 2, 'ogre': 1}
    """

    encounter = observation.encounter
    pending = encounter.targeting if encounter is not None else None
    return dict(Counter(pending.selected_target_refs)) if pending is not None else {}


def allocation_status(observation: GameObservation) -> str | None:
    """Describe pending target or numeric resource allocation.

    >>> from types import SimpleNamespace
    >>> pending = SimpleNamespace(
    ...     resource_pool_total=None, resource_allocations=(),
    ...     selected_target_refs=("goblin",), maximum_targets=3,
    ...     source_label="Scorching Ray",
    ... )
    >>> observation = SimpleNamespace(
    ...     encounter=SimpleNamespace(targeting=pending)
    ... )
    >>> allocation_status(observation)
    'Scorching Ray: 2 allocations remaining (1/3 assigned)'
    """

    encounter = observation.encounter
    pending = encounter.targeting if encounter is not None else None
    if pending is None:
        return None
    if pending.resource_pool_total is not None:
        allocated = sum(item.amount for item in pending.resource_allocations)
        return (
            f"Healing allocated: {allocated}/{pending.resource_pool_total} HP "
            f"({pending.resource_pool_total - allocated} remaining)"
        )
    selected = len(pending.selected_target_refs)
    remaining = max(0, pending.maximum_targets - selected)
    allocation_label = "allocation" if remaining == 1 else "allocations"
    return (
        f"{pending.source_label}: {remaining} {allocation_label} remaining "
        f"({selected}/{pending.maximum_targets} assigned)"
    )


def is_area_spell_action(action: ActionObservation) -> bool:
    """Return whether a spell action supplies geometry for map-based aiming.

    >>> is_area_spell_action(ActionObservation(
    ...     "fireball", "Fireball", "spell", "mage",
    ...     area_preview={"shape": "radius"},
    ... ))
    True
    """

    return action.kind == "spell" and action.area_preview is not None


def is_area_stat_block_action(action: ActionObservation) -> bool:
    """Return whether a stat-block action supplies geometry for map-based aiming.

    >>> is_area_stat_block_action(ActionObservation(
    ...     "breath", "Breath", "stat_block", "dragon",
    ...     area_preview={"shape": "cone"},
    ... ))
    True
    """

    return action.kind == "stat_block" and action.area_preview is not None


def _target_mode_source(action: ActionObservation) -> str | None:
    if action.kind == "attack":
        return action.source_trigger_id or action.preferred_attack_name or action.kind
    if action.kind == "grapple":
        return action.source_trigger_id or action.kind
    if action.kind == "stat_block":
        return action.preferred_attack_name
    return action.source_trigger_id


def _source_label(
    source_id: str | None,
    actions: Sequence[ActionObservation],
) -> str | None:
    if source_id is None:
        return None
    return next(
        (
            action.source_label
            for action in actions
            if action.source_id == source_id and action.source_label is not None
        ),
        None,
    )


def _spell_slot_variant(action: ActionObservation) -> str | None:
    slot_level = action.resource_level
    return f"Level {slot_level}" if slot_level is not None else None
