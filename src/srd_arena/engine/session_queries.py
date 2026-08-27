"""Build typed read queries from the mutable engine session."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.encounters.actions.eligibility_rules.models import (
    ActionEligibility,
    EligibilityFailure,
)
from srd_arena.domain.encounters.models import ActionCost, EncounterAction
from srd_arena.engine.action_queries import option_details
from srd_arena.engine.queries import (
    CONTINUE_CHOICE_TEXT,
    EXIT_CHOICE_TEXT,
    ActionOption,
    ActionOptionCost,
    SessionRead,
)

if TYPE_CHECKING:
    from srd_arena.engine.session import Session


def read_session(session: Session) -> SessionRead:
    """Return the intentional typed inputs for application observation.

    A pending transition advertises only Continue and system-level choices.

    >>> from types import SimpleNamespace
    >>> session = SimpleNamespace(
    ...     pending_scene_transition=SimpleNamespace(message="Victory!"),
    ...     encounter_state=None,
    ...     current_encounter=SimpleNamespace(id="demo", teams=[]),
    ...     item_templates={})
    >>> [option.label for option in read_session(session).action_options]
    ['Continue', 'Exit game']
    """

    if session.pending_scene_transition is not None:
        action_options = [
            _action_option(
                EncounterAction(
                    id="system-continue-scene-transition",
                    label=CONTINUE_CHOICE_TEXT,
                    kind="system_continue_transition",
                    creature_ref=_system_action_creature_ref(session),
                )
            )
        ]
        action_options.extend(_system_action_options(session))
        return _session_read(
            session,
            scene_text=session.pending_scene_transition.message,
            action_options=action_options,
        )

    session._ensure_encounter_state()
    state = session.encounter_state
    assert state is not None
    session._encounter_actions = state.available_actions()
    action_ids = [action.id for action in session._encounter_actions]
    if len(action_ids) != len(set(action_ids)):
        raise ValueError("Available encounter action IDs must be unique.")

    decision = state.current_decision()
    if (
        decision.kind == "turn"
        and state._creature_controller(decision.creature_ref) == "external"
    ):
        candidates = state._creature_action_candidates(decision.creature_ref)
        action_options = [
            _action_option(action, state.action_eligibility(action))
            for action in candidates
        ]
        action_options.extend(
            _unimplemented_stat_block_action_options(
                session,
                decision.creature_ref,
                candidates,
            )
        )
    else:
        action_options = [
            _action_option(action) for action in session._encounter_actions
        ]

    action_options.extend(_system_action_options(session))
    return _session_read(session, scene_text=None, action_options=action_options)


def _session_read(
    session: Session,
    *,
    scene_text: str | None,
    action_options: list[ActionOption],
) -> SessionRead:
    state = session.encounter_state
    transition_message = (
        session.pending_scene_transition.message
        if session.pending_scene_transition is not None
        else None
    )
    return SessionRead(
        scene_id=session.current_encounter.id,
        scene_text=scene_text,
        action_options=tuple(action_options),
        encounter_state=state,
        transition_message=transition_message,
        team_ids=tuple(team.id for team in session.current_encounter.teams),
        creature_labels=(
            {
                creature_ref: state._creature_label(creature_ref)
                for creature_ref in state.creatures
            }
            if state is not None
            else {}
        ),
        creature_team_ids=(
            {
                creature_ref: state._creature_team_id(creature_ref)
                for creature_ref in state.creatures
            }
            if state is not None
            else {}
        ),
        item_names={
            item_id: item.name for item_id, item in session.item_templates.items()
        },
        requires_automatic_advance=(
            transition_message is None
            and state is not None
            and state.requires_automatic_advance()
        ),
    )


def _action_option(
    action: EncounterAction,
    eligibility: ActionEligibility | None = None,
) -> ActionOption:
    checked_eligibility = eligibility or ActionEligibility()
    implemented = not any(
        failure.code == "unsupported_stat_block_capability"
        for failure in checked_eligibility.failures
    )
    return ActionOption(
        id=action.id,
        label=action.label,
        kind=action.kind,
        creature_ref=action.creature_ref or "",
        cost=ActionOptionCost(
            movement=int(action.cost.movement),
            action=action.cost.action,
            bonus_action=action.cost.bonus_action,
            reaction=action.cost.reaction,
        ),
        source_trigger_id=action.source_trigger_id,
        preferred_attack_type=action.preferred_attack_type,
        preferred_attack_name=action.preferred_attack_name,
        eligibility=checked_eligibility,
        implemented=implemented,
        details=option_details(action),
    )


def _unimplemented_stat_block_action_options(
    session: Session,
    creature_ref: str,
    candidates: list[EncounterAction],
) -> list[ActionOption]:
    state = session.encounter_state
    assert state is not None
    creature = state.creatures[creature_ref].creature
    represented_names = {
        action.preferred_attack_name
        for action in candidates
        if action.preferred_attack_name is not None
    }
    if any(action.kind == "multiattack" for action in candidates):
        represented_names.update(
            declaration.name
            for declaration in creature.declared_stat_block_actions
            if declaration.capability_type == "multiattack"
        )

    options: list[ActionOption] = []
    for index, declaration in enumerate(creature.declared_stat_block_actions):
        if declaration.name in represented_names:
            continue
        reason = (
            "No structured capabilities are available for this action."
            if declaration.capability_type is None
            else (
                f"Actions using '{declaration.capability_type}' capability "
                "are not executable yet."
            )
        )
        action = EncounterAction(
            id=f"{creature_ref}-unimplemented-stat-block-{index}",
            label=declaration.display_name,
            kind="stat_block",
            creature_ref=creature_ref,
            cost=(
                ActionCost(bonus_action=1)
                if declaration.section == "bonus_action"
                else ActionCost(action=1)
            ),
            preferred_attack_name=declaration.name,
        )
        options.append(
            _action_option(
                action,
                ActionEligibility(
                    (
                        EligibilityFailure(
                            code="unsupported_stat_block_capability",
                            message=reason,
                        ),
                    )
                ),
            )
        )
    return options


def _system_action_options(session: Session) -> list[ActionOption]:
    return [
        _action_option(
            EncounterAction(
                id="system-exit",
                label=EXIT_CHOICE_TEXT,
                kind="system_exit",
                creature_ref=_system_action_creature_ref(session),
            )
        ),
    ]


def _system_action_creature_ref(session: Session) -> str:
    if session.encounter_state is None:
        return ""
    return session.encounter_state.current_decision().creature_ref
