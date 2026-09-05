"""Resolve sourced rules that can prevent a damage-triggered defeat."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.effects.rule_effects import DamageTriggeredDefeatSave
from srd_arena.domain.rolls.saving_throws import resolve_saving_throw

from .effect_lifecycle.roll_usage import resolve_saving_throw_modifier
from .encounter_models.state import LethalDamage
from .rule_queries.providers import creature_rule_effects
from .rule_queries.rolls import roll_modifiers
from .state_runtime import create_event

if TYPE_CHECKING:
    from .encounter import EncounterState
    from .encounter_models.resolution import EncounterProgress


def prevent_damage_defeat(
    state: EncounterState,
    creature_ref: str,
    lethal_damage: LethalDamage,
    *,
    progress: EncounterProgress,
    action_id: str | None,
    frame_id: str | None,
) -> bool:
    """Try each applicable sourced rule before a defeat becomes final."""

    creature = state.creatures[creature_ref].creature
    for provider_state_id, source, rule in creature_rule_effects(state, creature_ref):
        if not isinstance(rule, DamageTriggeredDefeatSave):
            continue
        bypassed = (rule.bypass_critical_hits and lethal_damage.critical_hit) or bool(
            rule.bypass_damage_types.intersection(lethal_damage.damage_types)
        )
        if bypassed:
            continue
        ability = rule.ability
        save_rules = roll_modifiers(
            state,
            creature_ref,
            "saving_throw",
            ability=ability,
        )
        dc = rule.base_dc + lethal_damage.amount * rule.damage_multiplier
        saving_throw = resolve_saving_throw(
            creature,
            ability,
            dc,
            sourced_modifier_override=resolve_saving_throw_modifier(
                state,
                creature_ref,
                save_rules,
            ),
            sourced_mode_override=save_rules.mode,
            roller=state.dice.roll_die,
        )
        succeeded = saving_throw.check.success
        source_label = source.label or source.definition_id
        progress.events.append(
            create_event(
                state,
                "feature_triggered",
                creature_ref=creature_ref,
                frame_id=frame_id,
                action_id=action_id,
                data={
                    "feature_id": source.definition_id,
                    "feature_name": source_label,
                    "provider_state_id": provider_state_id,
                    "damage": lethal_damage.amount,
                    "damage_types": sorted(lethal_damage.damage_types),
                    "critical_hit": lethal_damage.critical_hit,
                    "save_ability": ability,
                    "save_die": saving_throw.check.roll.selected,
                    "save_dice": list(saving_throw.check.roll.dice),
                    "save_mode": saving_throw.check.roll.mode,
                    "save_modifier": saving_throw.modifiers.total,
                    "save_total": saving_throw.check.roll.total,
                    "save_dc": saving_throw.check.target,
                    "success": succeeded,
                    "prevented_defeat": succeeded,
                },
            )
        )
        outcome = "succeeds" if succeeded else "fails"
        progress.messages.append(
            (
                "system",
                f"{creature.name} {outcome} its {source_label} "
                f"{ability.title()} save ({saving_throw.check.roll.total} vs DC {dc}).",
            )
        )
        if succeeded:
            creature.current_health = min(
                rule.hit_points_on_success,
                creature.get_max_health(),
            )
            progress.messages.append(
                (
                    "system",
                    f"{creature.name} drops to {creature.get_health()} Hit Point instead.",
                )
            )
            return True
    return False
