"""Apply typed client configuration to advertised engine actions."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from srd_arena.domain.encounters.actions.eligibility import action_eligibility
from srd_arena.domain.spells.rules import SpellActionPayload
from srd_arena.engine.models import EngineOutcome
from srd_arena.engine.queries import (
    ActionAim,
    ActionConfiguration,
    ActionSpellCast,
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

    if isinstance(configuration, ActionSpellCast):
        if action.kind != "spell" or not isinstance(action.value, SpellActionPayload):
            raise ValueError("Only spell actions accept complete cast configuration.")
        value: SpellActionPayload | str | tuple[float, float] = replace(
            action.value,
            target_refs=configuration.target_refs,
            healing_allocations=configuration.allocations,
            aim_point=configuration.aim,
            selection_complete=True,
        )
    elif isinstance(configuration, ActionAim):
        if action.kind == "spell":
            if not isinstance(action.value, SpellActionPayload):
                raise ValueError(f"Spell action '{action_id}' has no spell payload.")
            value = replace(
                action.value,
                aim_point=(configuration.x, configuration.y),
            )
        elif action.kind == "stat_block":
            value = (configuration.x, configuration.y)
        else:
            raise ValueError(f"Action '{action_id}' cannot be aimed.")
    else:
        raise TypeError(f"Unsupported action configuration: {configuration!r}")

    configured = replace(action, value=value, aim_committed=True)
    if isinstance(configuration, ActionSpellCast):
        assert session.encounter_state is not None
        result = action_eligibility(
            session.encounter_state, configured.creature_ref or "", configured
        )
        if not result.allowed:
            raise ValueError(result.failures[0].message)
    return session._apply_encounter_action(
        configured,
        selected_choice_text=configured.label,
    )
