"""Apply typed application configuration to advertised engine actions."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from srd_arena.domain.spells.rules import spell_action_value
from srd_arena.engine.action_queries import option_details
from srd_arena.engine.models import EngineOutcome
from srd_arena.engine.queries import (
    ActionAim,
    ActionConfiguration,
    ActionResourceAllocation,
    SpellOptionDetails,
)

if TYPE_CHECKING:
    from srd_arena.engine.session import Session


def configure_action(
    session: Session,
    action_id: str,
    configuration: ActionConfiguration,
) -> EngineOutcome:
    """Apply typed configuration to an advertised executable action.

    Configuration is accepted only for an action in the latest engine read.

    >>> from types import SimpleNamespace
    >>> session = SimpleNamespace(
    ...     _ensure_encounter_state=lambda: None, _encounter_actions=[])
    >>> configure_action(session, "missing", ActionAim(2, 3))
    Traceback (most recent call last):
    ...
    KeyError: "Action 'missing' is unavailable."
    """

    session._ensure_encounter_state()
    action = next(
        (
            candidate
            for candidate in session._encounter_actions
            if candidate.id == action_id
        ),
        None,
    )
    if action is None:
        raise KeyError(f"Action '{action_id}' is unavailable.")

    if isinstance(configuration, ActionAim):
        if action.kind == "spell":
            details = option_details(action)
            if not isinstance(details, SpellOptionDetails) or details.source_id is None:
                raise ValueError(
                    f"Spell action '{action_id}' has no source identifier."
                )
            value: str | tuple[float, float] = spell_action_value(
                details.source_id,
                target_ref=details.target_refs or None,
                aim_point=(configuration.x, configuration.y),
                selected_condition=details.selected_condition,
                selected_damage_type=details.selected_damage_type,
                selected_ability=details.selected_ability,
                slot_level=details.resource_level,
                healing_allocations=dict(details.healing_allocations),
            )
        elif action.kind == "stat_block":
            value = (configuration.x, configuration.y)
        else:
            raise ValueError(f"Action '{action_id}' cannot be aimed.")
    elif isinstance(configuration, ActionResourceAllocation):
        if action.kind != "set_spell_resource_allocation":
            raise ValueError(
                f"Action '{action_id}' does not accept resource allocation."
            )
        value = f"{configuration.target_ref}~{configuration.amount}"
    else:
        raise TypeError(f"Unsupported action configuration: {configuration!r}")

    configured = replace(action, value=value)
    return session._apply_encounter_action(
        configured,
        selected_choice_text=configured.label,
    )
