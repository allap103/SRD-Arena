"""Select deterministic actions for the fixed Barbarian training ally."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from ..encounter_models.actions import CreatureRef, EncounterAction
from ..movement_routing import shortest_approach_directions
from ..participants import creatures_are_opponents
from ..spatial import creature_distance
from ..state_runtime import living_creature_refs

if TYPE_CHECKING:
    from ..encounter import EncounterState

_UNSPECIFIED = object()


class BarbarianAllyActionSelector:
    """Drive the fixed Barbarian ally through deterministic combat priorities.

    The policy consumes only advertised actions and public encounter state, so it
    can later be replaced without changing Barbarian rules or turn orchestration.
    """

    def select_action(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
        actions: Sequence[EncounterAction],
    ) -> EncounterAction:
        """Choose class-feature decisions before attacks and pursuit.

        >>> from unittest.mock import Mock
        >>> selector = BarbarianAllyActionSelector()
        >>> state = Mock()
        >>> state.current_decision.return_value.kind = "reckless_attack"
        >>> choice = selector.select_action(
        ...     state, "barbarian",
        ...     (EncounterAction("Use", "use_reckless_attack"),
        ...      EncounterAction("Decline", "decline_reckless_attack")),
        ... )
        >>> choice.kind
        'use_reckless_attack'
        """

        forced = _first_action(actions, kind="obey_compelled_turn")
        if forced is not None:
            return forced
        decision_kind = state.current_decision().kind
        if decision_kind == "reckless_attack":
            reckless = _first_action(actions, kind="use_reckless_attack")
            if reckless is not None:
                return reckless
        if decision_kind == "weapon_mastery":
            mastery = _first_action(actions, kind="use_weapon_mastery")
            if mastery is not None:
                return mastery
        if decision_kind != "turn":
            return _required_choice(actions)
        return self._select_turn_action(state, creature_ref, actions)

    def _select_turn_action(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
        actions: Sequence[EncounterAction],
    ) -> EncounterAction:
        target_ref = _nearest_opponent(state, creature_ref)
        wait = _first_action(actions, kind="wait")
        if target_ref is None:
            return wait or _required_choice(actions)

        for feature_id in ("rage", "extend_rage"):
            feature = _first_action(actions, kind="feature", value=feature_id)
            if feature is not None:
                return feature

        melee = _first_action(
            actions,
            kind="attack",
            value=target_ref,
            preferred_attack_type="melee",
            preferred_attack_name="Maul",
        ) or _first_action(
            actions,
            kind="attack",
            value=target_ref,
            preferred_attack_type="melee",
        )
        if melee is not None:
            return melee

        approach_directions = shortest_approach_directions(
            state,
            creature_ref,
            target_ref,
        )
        movement = next(
            (
                action
                for action in actions
                if action.kind == "move" and action.value in approach_directions
            ),
            None,
        )
        if movement is not None:
            return movement

        javelin = _first_action(
            actions,
            kind="attack",
            value=target_ref,
            preferred_attack_type="ranged",
            preferred_attack_name="Javelin",
        )
        if javelin is not None:
            return javelin
        return wait or _required_choice(actions)


def _nearest_opponent(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> CreatureRef | None:
    opponents = [
        target_ref
        for target_ref in living_creature_refs(state)
        if creatures_are_opponents(state, creature_ref, target_ref)
    ]
    if not opponents:
        return None
    return min(
        opponents,
        key=lambda target_ref: creature_distance(state, creature_ref, target_ref),
    )


def _first_action(
    actions: Sequence[EncounterAction],
    *,
    kind: str,
    value: object = _UNSPECIFIED,
    preferred_attack_type: object = _UNSPECIFIED,
    preferred_attack_name: object = _UNSPECIFIED,
) -> EncounterAction | None:
    """Return the first action matching the supplied stable selection fields."""

    for action in actions:
        if action.kind != kind:
            continue
        if value is not _UNSPECIFIED and action.value != value:
            continue
        if (
            preferred_attack_type is not _UNSPECIFIED
            and action.preferred_attack_type != preferred_attack_type
        ):
            continue
        if (
            preferred_attack_name is not _UNSPECIFIED
            and action.preferred_attack_name != preferred_attack_name
        ):
            continue
        return action
    return None


def _required_choice(actions: Sequence[EncounterAction]) -> EncounterAction:
    if not actions:
        raise RuntimeError("A scripted creature has no legal action.")
    return actions[0]
