"""Event perception must not depend on projection frequency or batch boundaries."""

import pytest

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.encounters.event_stream import create_event
from srd_arena.engine.api import Session


@pytest.mark.parametrize("observe_between_events", [False, True])
def test_batched_events_retain_their_own_visibility(
    observe_between_events: bool,
) -> None:
    session = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    session.observe_player("heroes")
    state = session.encounter_state
    assert state is not None
    visible_damage = create_event(
        state, "attack_resolved", data={"target_ref": "goblin_1", "damage": 2}
    )
    invisibility = build_applied_condition(
        condition=Condition.INVISIBLE,
        source_ref="goblin_1",
        source_label="Invisibility",
        target_ref="goblin_1",
    )
    state.conditions.append(invisibility)
    if observe_between_events:
        session.observe_player("heroes")
    hidden_damage = create_event(
        state, "attack_resolved", data={"target_ref": "goblin_1", "damage": 30}
    )
    state.conditions.remove(invisibility)
    if observe_between_events:
        session.observe_player("heroes")
    revealed_damage = create_event(
        state, "attack_resolved", data={"target_ref": "goblin_1", "damage": 5}
    )
    # Resolution ends with the target hidden again: final-state sight is also
    # insufficient to reconstruct the visibility of this batch.
    state.conditions.append(invisibility)
    session._record_gameplay_events((visible_damage, hidden_damage, revealed_damage))
    observed = session.observe_player("heroes")
    assert not observed.creature("goblin_1").currently_visible
    assert observed.creature("goblin_1").observed_damage_total == 7


def test_events_before_first_player_projection_are_remembered() -> None:
    session = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    session._read()
    state = session.encounter_state
    assert state is not None
    event = create_event(
        state, "attack_resolved", data={"target_ref": "goblin_1", "damage": 3}
    )
    session._record_gameplay_events((event,))
    assert (
        session.observe_player("heroes").creature("goblin_1").observed_damage_total == 3
    )
