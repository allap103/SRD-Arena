"""Resolve event-driven termination rules for ongoing spell effects."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from ...rolls.saving_throws import (
    Ability,
    resolve_saving_throw,
)
from ..participants import creatures_are_opponents
from ..state_combat import automatic_save_failure_provider_ids_for
from .removal import _remove_effect_target

if TYPE_CHECKING:
    from ..encounter import EncounterState
    from ..encounter_models.resolution import EncounterProgress


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
    >>> from ...effects.runtime import EndEventRule
    >>> effect = SimpleNamespace(
    ...     target_refs=("target",),
    ...     lifecycle=SimpleNamespace(
    ...         repeat_save=None,
    ...         end_events=(EndEventRule("target_makes_attack", "target"),),
    ...     ),
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
        repeat_save = effect.lifecycle.repeat_save
        if (
            event == "target_damaged"
            and repeat_save is not None
            and repeat_save.damage_grants_advantage
        ):
            ability = repeat_save.ability
            dc = repeat_save.dc
            if ability and dc:
                creature = state.creatures[affected_ref].creature
                roll_rules = state.combat_rules.roll_modifiers(
                    state,
                    affected_ref,
                    "saving_throw",
                    ability=ability,
                )
                save = resolve_saving_throw(
                    creature,
                    cast(Ability, ability),
                    dc,
                    mode="advantage",
                    sourced_modifier_override=roll_rules.resolve_modifier(
                        state.dice.roll_die
                    ),
                    sourced_mode_override=roll_rules.mode,
                    roller=state.dice.roll_die,
                    automatic_failure_reasons=(
                        automatic_save_failure_provider_ids_for(
                            state, affected_ref, ability
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
        for configured in effect.lifecycle.end_events:
            if configured.event != event:
                continue
            source_ref = effect.identity.source.applied_by_ref
            if (
                configured.scope == "source_team"
                and source_ref is not None
                and creatures_are_opponents(state, source_ref, actor_ref)
            ):
                continue
            _remove_effect_target(state, effect, affected_ref)
            break
