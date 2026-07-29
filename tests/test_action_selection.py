from pathlib import Path

from srd_arena.domain.encounters.models import EncounterAction
from srd_arena.runtime.scenario import Scenario


FIXTURE_ENCOUNTER_DIR = Path(__file__).parent / "fixtures" / "encounter_game"


def test_turn_engine_delegates_scripted_choice_to_actor_selector() -> None:
    session = Scenario(str(FIXTURE_ENCOUNTER_DIR)).create_session()
    session.current_scene_id = "goblin_encounter"
    session.get_scene_view()
    assert session.encounter_state is not None
    state = session.encounter_state
    creature_ref = "goblin_1"
    state.turn_index = state.initiative_order.index(creature_ref)
    selections: list[tuple[str, tuple[EncounterAction, ...], bool]] = []

    class RecordingSelector:
        def select_action(self, encounter, actor_ref, actions):
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

    progress = state.advance_until_next_decision()

    assert selections
    assert selections[0][0] == creature_ref
    assert all(action.creature_ref == creature_ref for action in selections[0][1])
    assert selections[0][2] is True
    assert ("system", "Goblin Warrior waits.") in progress.messages
