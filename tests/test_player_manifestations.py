from srd_arena.content.encounters import EncounterCatalog
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.encounters.encounter_models.resolution import CombatEvent
from srd_arena.engine.api import Session
from srd_arena.engine.player_events import public_events_from_event
from srd_arena.engine.player_manifestations import manifested_state


def test_roll_modifiers_and_generic_applications_do_not_diagnose_poison() -> None:
    for event_type in (
        "attack_resolved",
        "condition_applied",
        "ongoing_effect_resolved",
    ):
        event = CombatEvent(
            1,
            event_type,
            "enemy",
            data={
                "condition": "poisoned",
                "condition_id": "poison-1",
                "hit": False,
                "mode": "disadvantage",
            },
        )
        assert manifested_state(event) is None


def test_manifestation_is_visible_only_and_does_not_export_instance_ids() -> None:
    event = CombatEvent(
        1,
        "condition_manifested",
        "enemy",
        data={
            "condition": "poisoned",
            "condition_id": "private-instance",
            "manifestation": "stinking_cloud_retching",
        },
    )
    assert public_events_from_event(event, visible_creature_refs=frozenset()) == ()
    [public] = public_events_from_event(
        event, visible_creature_refs=frozenset({"enemy"})
    )
    assert public.source_id == "condition:poisoned"
    assert "private-instance" not in repr(public)


def test_discovery_tracks_instance_and_preserves_last_known_state_out_of_view() -> None:
    session = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    session.observe_player("heroes")
    state = session.encounter_state
    assert state is not None
    poison = build_applied_condition(
        condition=Condition.POISONED,
        source_ref="warlock",
        source_label="Cloud",
        target_ref="goblin_1",
        origin_id="cloud-1",
    )
    state.conditions.append(poison)
    assert (
        "poisoned"
        not in session.observe_player("heroes").creature("goblin_1").known_conditions
    )
    session._record_player_events(
        (
            CombatEvent(
                1,
                "condition_manifested",
                "goblin_1",
                data={
                    "condition": "poisoned",
                    "condition_id": poison.id,
                    "manifestation": "stinking_cloud_retching",
                },
            ),
        )
    )
    assert (
        "poisoned"
        in session.observe_player("heroes").creature("goblin_1").known_conditions
    )
    invisible = build_applied_condition(
        condition=Condition.INVISIBLE,
        source_ref="goblin_1",
        source_label="Hidden",
        target_ref="goblin_1",
    )
    state.conditions.append(invisible)
    session.observe_player("heroes")
    state.conditions.remove(poison)
    assert (
        "poisoned"
        in session.observe_player("heroes").creature("goblin_1").known_conditions
    )
    state.conditions.remove(invisible)
    assert (
        "poisoned"
        not in session.observe_player("heroes").creature("goblin_1").known_conditions
    )
    replacement = build_applied_condition(
        condition=Condition.POISONED,
        source_ref="warlock",
        source_label="Different poison",
        target_ref="goblin_1",
        origin_id="poison-2",
    )
    state.conditions.append(replacement)
    assert (
        "poisoned"
        not in session.observe_player("heroes").creature("goblin_1").known_conditions
    )
