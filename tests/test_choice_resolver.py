from hypothesis import given
from hypothesis import strategies as st

import game.choice_resolver as choice_resolver_module
from game.choice_resolver import ChoiceResolver
from game.engine import Game
from game.loaders import load_scene
from game.models.choice import Choice, Effects, Outcome, SkillTest
from game.models.scene import Scene

from tests.helpers import make_actor


def test_resolve_applies_damage_outcome() -> None:
    actor = make_actor()
    resolver = ChoiceResolver()
    choice = Choice(
        choice_text="Touch the cursed idol.",
        next_scene="idol-room",
        test=SkillTest(
            skill="dexterity",
            difficulty=99,
            effects=Effects(on_failure=Outcome(damage=4)),
        ),
    )
    scene = Scene(id="idol-room", text="A dusty shrine.", choices=[choice])

    result = resolver.resolve(scene, choice, actor)

    assert result.next_scene_id == "idol-room"
    assert actor.get_health() == actor.get_max_health() - 4
    assert ("system", "You take 4 damage and now have 8 health.") in result.messages


def test_load_scene_reads_damage_outcome() -> None:
    scene = load_scene("sample_game/scenes/scene_1_house")
    choice = scene.choices[0]

    assert choice.test is not None
    assert choice.test.effects is not None
    assert choice.test.effects.on_failure is not None
    assert choice.test.effects.on_failure.damage == 2


def test_goblin_failure_deals_damage(monkeypatch) -> None:
    monkeypatch.setattr(choice_resolver_module, "roll_die", lambda sides: 1)
    session = Game().create_session()
    session.current_scene_id = "scene_1_house"

    result = session.choose(0)

    assert session.player.get_health() == 10
    assert any("You take 2 damage" in message for _, message in result.messages)


def test_goblin_success_still_grants_key(monkeypatch) -> None:
    monkeypatch.setattr(choice_resolver_module, "roll_die", lambda sides: 20)
    session = Game().create_session()
    session.current_scene_id = "scene_1_house"

    result = session.choose(0)

    assert session.player.inventory.has_item("key")
    assert result.next_scene_id == "scene_1_house_key"


@given(st.integers(min_value=0, max_value=20))
def test_damage_outcome_never_makes_health_negative(amount: int) -> None:
    actor = make_actor()
    resolver = ChoiceResolver()
    choice = Choice(
        choice_text="Step into the trap.",
        next_scene="trap-room",
        test=SkillTest(
            skill="dexterity",
            difficulty=99,
            effects=Effects(on_failure=Outcome(damage=amount)),
        ),
    )
    scene = Scene(id="trap-room", text="A hidden mechanism clicks.", choices=[choice])

    resolver.resolve(scene, choice, actor)

    assert 0 <= actor.get_health() <= actor.get_max_health()
