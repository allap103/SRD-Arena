"""Apply lifecycle consequences shared by resolved attack rolls."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.effects.results import AttackHitRetaliationApplication
from srd_arena.domain.effects.rule_effects import AttackHitRetaliation

from ..defeat import resolve_creature_defeat
from ..effect_lifecycle.concentration import resolve_concentration_damage
from ..effect_lifecycle.lifecycle_events import resolve_spell_lifecycle_event
from ..rule_queries.models import SourcedRuleContribution
from ..state_combat import apply_combat_damage
from ..state_runtime import create_event, creature_label

if TYPE_CHECKING:
    from ..encounter import EncounterState
    from ..encounter_models.resolution import EncounterProgress


def resolve_attack_lifecycle(
    state: EncounterState,
    *,
    attacker_ref: str,
    target_ref: str,
    damage: int,
    progress: EncounterProgress,
    retaliations: tuple[SourcedRuleContribution[AttackHitRetaliation], ...] = (),
    action_id: str | None = None,
    frame_id: str | None = None,
) -> None:
    """Publish attack/damage triggers and resolve concentration damage.

    A damaging attack publishes the attack itself plus both damage-facing
    lifecycle events before checking the target's concentration.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import patch
    >>> from srd_arena.domain.encounters.encounter_models.resolution import EncounterProgress
    >>> with patch(
    ...     "srd_arena.domain.encounters.reaction_runtime.attack_lifecycle."
    ...     "resolve_spell_lifecycle_event"
    ... ) as lifecycle, patch(
    ...     "srd_arena.domain.encounters.reaction_runtime.attack_lifecycle."
    ...     "resolve_concentration_damage"
    ... ) as concentration:
    ...     resolve_attack_lifecycle(
    ...         SimpleNamespace(),
    ...         attacker_ref="guard",
    ...         target_ref="hero",
    ...         damage=7,
    ...         progress=EncounterProgress(),
    ...     )
    >>> [call.args[1] for call in lifecycle.call_args_list]
    ['target_makes_attack', 'target_damaged', 'target_deals_damage']
    >>> concentration.call_args.args[2]
    7
    """

    resolve_spell_lifecycle_event(
        state,
        "target_makes_attack",
        actor_ref=attacker_ref,
        target_ref=target_ref,
        progress=progress,
    )
    if damage > 0:
        resolve_spell_lifecycle_event(
            state,
            "target_damaged",
            actor_ref=attacker_ref,
            target_ref=target_ref,
            progress=progress,
        )
        resolve_spell_lifecycle_event(
            state,
            "target_deals_damage",
            actor_ref=attacker_ref,
            target_ref=target_ref,
            progress=progress,
        )
    resolve_concentration_damage(state, target_ref, damage, progress)
    resolve_attack_hit_retaliations(
        state,
        attacker_ref=attacker_ref,
        applications=tuple(
            AttackHitRetaliationApplication(
                protected_target_ref=target_ref,
                provider_state_id=contribution.provider_state_id,
                source_definition_id=contribution.source.definition_id,
                source_ref=contribution.source.applied_by_ref,
                damage=contribution.value.damage,
                damage_type=contribution.value.damage_type,
            )
            for contribution in retaliations
        ),
        progress=progress,
        action_id=action_id,
        frame_id=frame_id,
    )


def resolve_attack_hit_retaliations(
    state: EncounterState,
    *,
    attacker_ref: str,
    applications: tuple[AttackHitRetaliationApplication, ...],
    progress: EncounterProgress,
    action_id: str | None,
    frame_id: str | None,
) -> None:
    """Apply retaliation rules captured before the triggering hit dealt damage."""

    if not applications:
        return
    attacker = state.creatures[attacker_ref].creature
    attacker_label = creature_label(state, attacker_ref)
    was_alive = attacker.get_health() > 0
    for application in applications:
        defender_ref = application.protected_target_ref
        defender_label = creature_label(state, defender_ref)
        applied = apply_combat_damage(
            state,
            attacker_ref,
            application.damage,
            application.damage_type,
        )
        progress.messages.append(
            (
                "system",
                f"{attacker_label} takes {applied} "
                f"{application.damage_type.title()} damage after hitting "
                f"{defender_label}.",
            )
        )
        progress.events.append(
            create_event(
                state,
                "attack_hit_retaliation",
                creature_ref=defender_ref,
                frame_id=frame_id,
                action_id=action_id,
                data={
                    "attacker_ref": attacker_ref,
                    "attacker_label": attacker_label,
                    "defender_ref": defender_ref,
                    "defender_label": defender_label,
                    "provider_state_id": application.provider_state_id,
                    "source_definition_id": application.source_definition_id,
                    "source_ref": application.source_ref,
                    "requested_damage": application.damage,
                    "damage": applied,
                    "damage_type": application.damage_type,
                },
            )
        )
        if applied > 0:
            resolve_spell_lifecycle_event(
                state,
                "target_damaged",
                actor_ref=defender_ref,
                target_ref=attacker_ref,
                progress=progress,
            )
            resolve_spell_lifecycle_event(
                state,
                "target_deals_damage",
                actor_ref=defender_ref,
                target_ref=attacker_ref,
                progress=progress,
            )
        resolve_concentration_damage(state, attacker_ref, applied, progress)
    if was_alive and attacker.get_health() <= 0:
        resolve_creature_defeat(
            state,
            attacker_ref,
            defeated_by_ref=applications[0].protected_target_ref,
            progress=progress,
            frame_id=frame_id,
            action_id=action_id,
        )
