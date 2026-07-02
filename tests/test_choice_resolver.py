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


def test_success_outcome_next_scene_overrides_choice_next_scene(monkeypatch) -> None:
    monkeypatch.setattr(choice_resolver_module, "roll_die", lambda sides: 20)
    actor = make_actor()
    resolver = ChoiceResolver()
    choice = Choice(
        choice_text="Sneak past the guard.",
        next_scene="noticed-by-guard",
        test=SkillTest(
            skill="dexterity",
            difficulty=10,
            effects=Effects(
                on_success=Outcome(
                    message="You pass unnoticed.",
                    next_scene="safe-passage",
                )
            ),
        ),
    )
    scene = Scene(id="guard-post", text="A guard watches the path.", choices=[choice])

    result = resolver.resolve(scene, choice, actor)

    assert result.next_scene_id == "safe-passage"
    assert ("scene", "You pass unnoticed.") in result.messages


def test_failure_outcome_can_transition_to_scene(monkeypatch) -> None:
    monkeypatch.setattr(choice_resolver_module, "roll_die", lambda sides: 1)
    actor = make_actor()
    resolver = ChoiceResolver()
    choice = Choice(
        choice_text="Sneak past the guard.",
        next_scene="safe-passage",
        test=SkillTest(
            skill="dexterity",
            difficulty=99,
            effects=Effects(
                on_failure=Outcome(
                    message="The guard spots you.",
                    next_scene="alarm",
                )
            ),
        ),
    )
    scene = Scene(id="guard-post", text="A guard watches the path.", choices=[choice])

    result = resolver.resolve(scene, choice, actor)

    assert result.next_scene_id == "alarm"
    assert ("scene", "The guard spots you.") in result.messages


def test_load_scene_reads_damage_outcome() -> None:
    scene = load_scene("app/content/scenarios/sample_game/scenes/welcome")
    choice = next(
        choice for choice in scene.choices if choice.choice_text == "Try to sneak away."
    )

    assert choice.test is not None
    assert choice.test.effects is not None
    assert choice.test.effects.on_failure is not None
    assert choice.test.effects.on_failure.damage == 2
    assert choice.test.effects.on_failure.next_scene == "goblin_encounter"


def test_goblin_failure_deals_damage(monkeypatch) -> None:
    monkeypatch.setattr(choice_resolver_module, "roll_die", lambda sides: 1)
    session = Game().create_session()

    choice_index = session.get_scene_view().choices.index("Try to sneak away.")
    result = session.choose(choice_index)

    assert session.player.get_health() == session.player.get_max_health() - 2
    assert any("You take 2 damage" in message for _, message in result.messages)
    assert result.next_scene_id == "goblin_encounter"


def test_goblin_success_still_grants_key(monkeypatch) -> None:
    monkeypatch.setattr(choice_resolver_module, "roll_die", lambda sides: 20)
    session = Game().create_session()

    choice_index = session.get_scene_view().choices.index("Try to sneak away.")
    result = session.choose(choice_index)

    assert session.player.inventory.has_item("key")
    assert result.next_scene_id == "sneaking_success"


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
