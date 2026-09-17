"""Complete-cast options disclose allied limits without exposing client drafts."""

from dataclasses import replace

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.engine.api import CastSpell, Session
from srd_arena.engine.player_action_observations import player_action_observations


def _session() -> Session:
    return Session(
        EncounterCatalog().load_encounter("archive/mass_heal_allocation_showcase"),
        seed=42,
    )


def test_owner_can_configure_and_cast_without_full_state() -> None:
    session = _session()
    before = session.observe_player("wounded_party")
    action = next(a for a in before.action_details if a.kind == "spell" and a.enabled)
    assert before.targeting is None
    options = action.spell_cast
    assert options is not None and options.resource_pool == 700
    assert dict(options.resource_limits)["healer"] == 200
    result = session.execute_player(
        "wounded_party",
        CastSpell(action.id, before.decision.id, ("healer",), (("healer", 200),)),
    )
    assert result.accepted, result.failure
    assert result.update is not None and result.update.observation.targeting is None
    assert before.targeting is None


def test_enemy_allocation_limits_are_not_projected() -> None:
    session = _session()
    action = next(
        a for a in session.observe().scene.action_details if a.spell_cast is not None
    )
    assert action.spell_cast is not None
    allies = frozenset({"healer", "guardian", "champion", "scout"})

    def projected(amount: int) -> object:
        assert action.spell_cast is not None
        edited = replace(
            action,
            spell_cast=replace(
                action.spell_cast,
                resource_limits=(
                    *action.spell_cast.resource_limits,
                    ("observer", amount),
                ),
            ),
        )
        return player_action_observations(
            (edited,),
            visible_creature_refs=allies | {"observer"},
            allied_creature_refs=allies,
        )

    assert projected(999) == projected(1)
    result = projected(1)
    assert isinstance(result, tuple)
    assert all(ref != "observer" for ref, _ in result[0].spell_cast.resource_limits)


def test_player_cannot_submit_enemy_healing_allocations_or_other_teams_commands() -> (
    None
):
    session = _session()
    view = session.observe_player("wounded_party")
    action = next(
        a for a in view.action_details if a.spell_cast is not None and a.enabled
    )
    before = session.observe_gameplay()
    assert not session.execute_player(
        "wounded_party",
        CastSpell(action.id, view.decision.id, ("observer",), (("observer", 1),)),
    ).accepted
    assert not session.execute_player(
        "observers",
        CastSpell(action.id, view.decision.id, ("healer",), (("healer", 1),)),
    ).accepted
    assert session.observe_gameplay() == before
