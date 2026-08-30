"""Group advertised actions for the encounter action menu."""

from __future__ import annotations

from collections.abc import Sequence

from srd_arena.engine.api import ActionObservation

ACTION_BUCKETS = (
    ("attack", "Attack"),
    ("magic", "Magic"),
    ("class", "Class"),
    ("utilize", "Utilize"),
    ("other", "Other"),
)
ACTION_ECONOMIES = ("action", "bonus_action", "reaction")


def group_actions(
    actions: Sequence[ActionObservation],
) -> dict[str, dict[str, list[ActionObservation]]]:
    """Group actions first by economy and then by presentation category.

    >>> attack = ActionObservation("attack", "Attack", "attack", "hero")
    >>> spell = ActionObservation(
    ...     "spell", "Fireball", "spell", "hero", cost={"action": 1}
    ... )
    >>> groups = group_actions((attack, spell))
    >>> ([item.label for item in groups["action"]["attack"]],
    ...  [item.label for item in groups["action"]["magic"]])
    (['Attack'], ['Fireball'])
    """

    groups: dict[str, dict[str, list[ActionObservation]]] = {
        economy: {bucket: [] for bucket, _label in ACTION_BUCKETS}
        for economy in ACTION_ECONOMIES
    }
    for action in actions:
        if action.kind == "set_spell_resource_allocation":
            continue
        groups[action_economy(action)][action_bucket(action)].append(action)
    return groups


def action_economy(action: ActionObservation) -> str:
    """Return the action-economy column used to present an option.

    >>> action_economy(
    ...     ActionObservation("dash", "Dash", "feature", "hero", cost={"bonus_action": 1})
    ... )
    'bonus_action'
    >>> action_economy(ActionObservation("pass", "Pass", "pass", "hero"))
    'reaction'
    """

    if action.cost.get("bonus_action", 0) > 0:
        return "bonus_action"
    if action.cost.get("reaction", 0) > 0 or action.kind in {
        "opportunity_attack",
        "pass",
    }:
        return "reaction"
    return "action"


def action_bucket(action: ActionObservation) -> str:
    """Return the action-menu category used to present an option.

    >>> action_bucket(ActionObservation("spell", "Fireball", "spell", "hero"))
    'magic'
    >>> action_bucket(ActionObservation("potion", "Potion", "utilize", "hero"))
    'utilize'
    """

    if action.kind in {"attack", "multiattack", "opportunity_attack", "grapple"}:
        return "attack"
    if action.kind in {"magic", "spell"}:
        return "magic"
    if action.kind == "feature":
        return "class"
    if action.kind == "utilize":
        return "utilize"
    return "other"
