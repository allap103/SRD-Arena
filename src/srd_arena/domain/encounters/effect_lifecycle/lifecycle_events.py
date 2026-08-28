"""Resolve event-driven termination rules for ongoing spell effects."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from ...rolls.saving_throws import (
    Ability,
    SavingThrowCreature,
    resolve_saving_throw,
)
from .removal import _remove_effect_target
from .rolls import roll_die

if TYPE_CHECKING:
    from ..encounter import EncounterState
    from ..models import EncounterProgress


def resolve_spell_lifecycle_event(
    state: EncounterState,
    event: str,
    *,
    actor_ref: str,
    target_ref: str | None = None,
    progress: EncounterProgress | None = None,
) -> None:
    """Apply event-triggered repeat saves and configured termination rules.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import patch
    >>> source = SimpleNamespace(applied_by_ref="mage", label="Hideous Laughter")
    >>> effect = SimpleNamespace(
    ...     target_refs=("target",),
    ...     parameters={"end_events": [["target_makes_attack", "target"]]},
    ...     identity=SimpleNamespace(source=source),
    ... )
    >>> state = SimpleNamespace(ongoing_effects=[effect])
    >>> with patch(
    ...     "srd_arena.domain.encounters.effect_lifecycle.lifecycle_events."
    ...     "_remove_effect_target"
    ... ) as remove:
    ...     resolve_spell_lifecycle_event(
    ...         state, "target_makes_attack", actor_ref="target"
    ...     )
    >>> remove.call_args.args[2]
    'target'
    """

    for effect in tuple(state.ongoing_effects):
        affected_ref = (
            target_ref
            if event in {"target_damaged", "adjacent_creature_wakes_target"}
            and target_ref is not None
            else actor_ref
        )
        if affected_ref not in effect.target_refs:
            continue
        if event == "target_damaged" and effect.parameters.get(
            "damage_repeat_save_advantage"
        ):
            ability = effect.parameters.get("save_ability")
            dc = effect.parameters.get("save_dc")
            if isinstance(ability, str) and isinstance(dc, int):
                creature = state.creatures[affected_ref].creature
                roll_rules = state.combat_rules.roll_modifiers(
                    state,
                    affected_ref,
                    "saving_throw",
                    ability=ability,
                )
                save = resolve_saving_throw(
                    cast(SavingThrowCreature, creature),
                    cast(Ability, ability),
                    dc,
                    mode="advantage",
                    sourced_modifier_override=roll_rules.resolve_modifier(roll_die),
                    sourced_mode_override=roll_rules.mode,
                    roller=roll_die,
                    automatic_failure_reasons=(
                        state._automatic_save_failure_provider_ids_for(
                            affected_ref, ability
                        )
                    ),
                )
                if save.check.success:
                    _remove_effect_target(state, effect, affected_ref)
                    if progress is not None:
                        progress.messages.append(
                            (
                                "system",
                                f"{creature.name} ends "
                                f"{effect.identity.source.label} after taking damage.",
                            )
                        )
                    continue
        end_events = effect.parameters.get("end_events", [])
        if not isinstance(end_events, list):
            continue
        for configured in end_events:
            if not isinstance(configured, list) or len(configured) != 2:
                continue
            configured_event, scope = configured
            if configured_event != event:
                continue
            source_ref = effect.identity.source.applied_by_ref
            if (
                scope == "source_team"
                and source_ref is not None
                and state._creatures_are_opponents(source_ref, actor_ref)
            ):
                continue
            _remove_effect_target(state, effect, affected_ref)
            break
