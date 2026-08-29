from collections.abc import Sequence
from pathlib import Path

from srd_arena.domain.encounters import EncounterOrchestrator
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.actions import EncounterAction
from srd_arena.infrastructure.scenarios import load_scenario_directory

FIXTURE_ENCOUNTER_DIR = Path(__file__).parent / "fixtures" / "encounter_game"
_ORCHESTRATOR = EncounterOrchestrator()


def test_orchestrator_delegates_scripted_choice_to_actor_selector() -> None:
    session = load_scenario_directory(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.read()
    assert session.encounter_state is not None
    state = session.encounter_state
    creature_ref = "goblin_1"
    state.turn.index = state.initiative_order.index(creature_ref)
    selections: list[tuple[str, tuple[EncounterAction, ...], bool]] = []

    class RecordingSelector:
        def select_action(
            self,
            encounter: EncounterState,
            actor_ref: str,
            actions: Sequence[EncounterAction],
        ) -> EncounterAction:
            selections.append(
                (
                    actor_ref,
                    tuple(actions),
                    all(
                        encounter.action_eligibility(action).allowed
                        for action in actions
                    ),
                )
            )
            return next(action for action in actions if action.kind == "wait")

    state._action_selectors[creature_ref] = RecordingSelector()

    progress = _ORCHESTRATOR.advance(state)

    assert selections
    assert selections[0][0] == creature_ref
    assert all(action.creature_ref == creature_ref for action in selections[0][1])
    assert selections[0][2] is True
    assert ("system", "Goblin Warrior waits.") in progress.messages
