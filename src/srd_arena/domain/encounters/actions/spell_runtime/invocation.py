"""Commit and evaluate the start of one spell invocation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....effects.runtime import OngoingEffectKind
from ...ongoing_effects import end_concentration, resolve_spell_lifecycle_event
from ...rule_queries import InvocationStartContext, InvocationStartResult
from .rolls import roll_die

if TYPE_CHECKING:
    from ....creatures import Creature, Spellcasting
    from ....spells.definitions import Spell
    from ...encounter import EncounterState
    from ...models import ActionCost, EncounterProgress


_COMPONENT_NAMES = {
    "v": "verbal",
    "s": "somatic",
    "m": "material",
}


def begin_spell_invocation(
    state: EncounterState,
    *,
    actor: Creature,
    spellcasting: Spellcasting,
    spell: Spell,
    cost: ActionCost,
    cast_level: int | None,
    creature_ref: str,
    action_id: str,
    progress: EncounterProgress,
) -> bool:
    """Commit spell resources, publish start effects, and run start checks."""

    state._spend_spell_resources(spellcasting, spell, cost, cast_level)
    if spell.concentration:
        _end_replaced_concentration(
            state,
            actor,
            creature_ref=creature_ref,
            progress=progress,
        )
    resolve_spell_lifecycle_event(
        state,
        "target_casts_spell",
        actor_ref=creature_ref,
        progress=progress,
    )
    components = _spell_components(spell)
    query = state.combat_rules.invocation_start_checks(
        state,
        InvocationStartContext(
            actor_ref=creature_ref,
            kind="cast_spell",
            components=components,
        ),
    )
    result = state.combat_rules.resolve_invocation_start(query, roll_die)
    if result.rolls:
        progress.events.append(
            state._event(
                "invocation_start_checked",
                creature_ref=creature_ref,
                action_id=action_id,
                data=_invocation_event_data(spell, result),
            )
        )
    if result.allowed:
        return True
    progress.messages.extend(
        ("system", failure.message) for failure in result.failures
    )
    progress.events.append(
        state._event(
            "action_resolved",
            creature_ref=creature_ref,
            action_id=action_id,
            data={
                "kind": "spell",
                "spell_id": spell.id,
                "success": False,
                "failure_codes": [failure.code for failure in result.failures],
                "provider_state_ids": [
                    failure.provider_state_id for failure in result.failures
                ],
            },
        )
    )
    return False


def _spell_components(spell: Spell) -> frozenset[str]:
    return frozenset(
        _COMPONENT_NAMES.get(key.casefold(), key.casefold())
        for key, value in spell.components.items()
        if value is not False and value is not None and value != ""
    )


def _invocation_event_data(
    spell: Spell,
    result: InvocationStartResult,
) -> dict[str, object]:
    return {
        "kind": result.context.kind,
        "spell_id": spell.id,
        "components": sorted(result.context.components),
        "allowed": result.allowed,
        "checks": [
            {
                "provider_state_id": check.provider_state_id,
                "source": {
                    "kind": check.source.kind.value,
                    "definition_id": check.source.definition_id,
                    "applied_by_ref": check.source.applied_by_ref,
                    "label": check.source.label,
                    "origin_id": check.source.origin_id,
                },
                "code": check.code,
                "message": check.message,
                "numerator": check.contribution.numerator,
                "denominator": check.contribution.denominator,
                "roll": check.roll,
                "failed": check.failed,
            }
            for check in result.rolls
        ],
    }


def _end_replaced_concentration(
    state: EncounterState,
    actor: Creature,
    *,
    creature_ref: str,
    progress: EncounterProgress,
) -> None:
    existing = next(
        (
            effect
            for effect in state.ongoing_effects
            if effect.kind is OngoingEffectKind.CONCENTRATION
            and effect.identity.source.applied_by_ref == creature_ref
        ),
        None,
    )
    if existing is None:
        return
    effect_label = existing.parameters.get("effect_label")
    if not isinstance(effect_label, str):
        effect_label = existing.identity.source.definition_id.replace(
            "_", " "
        ).title()
    progress.messages.append(
        (
            "system",
            f"{actor.name} drops concentration on {effect_label}.",
        )
    )
    end_concentration(state, creature_ref)
