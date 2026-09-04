"""Verify the canonical Berserker Barbarian's Frenzy damage trigger."""

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from srd_arena.content.character_options.classes import load_class_catalog
from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import (
    build_creature,
    load_character_snapshot_catalog,
)
from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.geometry import Position
from srd_arena.engine.models import EngineOutcome
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import (
    keep_alert_initiative,
    use_deterministic_dice,
)

WARLOCK_TRAINING_ENCOUNTER_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "warlock_training"
)


def _prepared_session(d20_rolls: tuple[int, ...]) -> Session:
    """Give the level-five Barbarian an externally controlled adjacent target."""

    session = Session(load_encounter_directory(WARLOCK_TRAINING_ENCOUNTER_DIR))
    keep_alert_initiative(session)
    state = session.encounter_state
    assert state is not None
    participant = next(
        participant
        for participant in state.definition.participants
        if participant.creature_id == "barbarian"
    )
    participant.controller = "external"
    state.turn.index = state.initiative_order.index("barbarian")
    state.creatures["barbarian"].position = Position(4, 4)
    state.creatures["ogre_target"].position = Position(5, 4)
    state.creatures["barbarian"].features_used_this_turn.add("savage_attacker")
    rolls = iter(d20_rolls)
    use_deterministic_dice(
        session,
        die_roller=lambda sides: next(rolls) if sides == 20 else 4,
    )
    return session


def _action_id(
    session: Session,
    *,
    kind: str,
    label: str,
    target_ref: str | None = None,
) -> str:
    """Return one currently advertised action matching its kind and label."""

    return next(
        option.id
        for option in session._read().action_options
        if option.kind == kind
        and option.label == label
        and (
            target_ref is None
            or (
                option.details is not None
                and getattr(option.details, "target_ref", None) == target_ref
            )
        )
    )


def _mapping(value: object) -> Mapping[str, object]:
    """Narrow an event payload value to a mapping for focused assertions."""

    return cast(Mapping[str, object], value)


def _rage_and_attack_recklessly(session: Session) -> EngineOutcome:
    """Enter Rage, select a Maul attack, and accept Reckless Attack."""

    session._choose(_action_id(session, kind="feature", label="Rage"))
    session._choose(
        _action_id(session, kind="attack", label="Maul", target_ref="ogre_target")
    )
    return session._choose(
        next(
            option.id
            for option in session._read().action_options
            if option.kind == "use_reckless_attack"
        )
    )


def test_frenzy_enters_only_with_the_berserker_subclass_at_level_three() -> None:
    """Compile the selected subclass's first feature at its earned level."""

    snapshots = load_character_snapshot_catalog(SYSTEM_CONTENT_ROOT)
    classes = load_class_catalog(SYSTEM_CONTENT_ROOT)
    level_two = build_creature(
        snapshots.creature_template("barbarian", 2),
        classes=classes,
    )
    level_three = build_creature(
        snapshots.creature_template("barbarian", 3),
        classes=classes,
    )

    assert all(feature.id != "frenzy" for feature in level_two.class_features)
    frenzy = next(
        feature for feature in level_three.class_features if feature.id == "frenzy"
    )
    assert frenzy.data == {"damage_dice": "2d6"}


def test_frenzy_adds_inherited_damage_to_the_first_reckless_rage_hit() -> None:
    """Roll 2d6 of the Maul's type without repeating Rage Damage on the rider."""

    session = _prepared_session((3, 17))

    result = _rage_and_attack_recklessly(session)
    event = next(event for event in result.events if event.type == "attack_resolved")
    detail = _mapping(event.data["damage_roll_detail"])
    additional = cast(list[Mapping[str, object]], detail["additional_damage"])

    assert detail["total"] == 14  # 2d6 + Strength + Rage Damage
    assert additional == [
        {
            "dice": "2d6",
            "dice_values": [4, 4],
            "die_rolls": [[4], [4]],
            "dice_total": 8,
            "modifier": 0,
            "sourced_modifier": 0,
            "total": 8,
            "damage_type": "bludgeoning",
            "critical_hit": False,
            "provider_state_ids": ["intrinsic:barbarian:frenzy"],
        }
    ]


def test_frenzy_waits_for_a_hit_and_applies_only_once_per_turn() -> None:
    """Preserve Frenzy after a miss and consume it after the next hit."""

    session = _prepared_session((1, 2, 10, 11, 12, 13))
    state = session.encounter_state
    assert state is not None

    first = _rage_and_attack_recklessly(session)
    first_event = next(
        event for event in first.events if event.type == "attack_resolved"
    )
    second = session._choose(
        _action_id(session, kind="attack", label="Maul", target_ref="ogre_target")
    )
    second_event = next(
        event for event in second.events if event.type == "attack_resolved"
    )

    assert first_event.data["hit"] is False
    assert second_event.data["hit"] is True
    assert state.creatures["barbarian"].features_used_this_turn >= {"frenzy"}
    assert (
        len(
            cast(
                list[object],
                _mapping(second_event.data["damage_roll_detail"])["additional_damage"],
            )
        )
        == 1
    )

    # Give the same turn one more attack to prove the consumed rider stays absent.
    state.creatures["barbarian"].attacks_remaining = 1
    third = session._choose(
        _action_id(session, kind="attack", label="Maul", target_ref="ogre_target")
    )
    third_event = next(
        event for event in third.events if event.type == "attack_resolved"
    )
    assert _mapping(third_event.data["damage_roll_detail"])["additional_damage"] == []


def test_frenzy_requires_both_rage_and_reckless_attack() -> None:
    """Do not add subclass damage when either prerequisite is absent."""

    without_rage = _prepared_session((3, 17))
    without_rage._choose(
        _action_id(
            without_rage,
            kind="attack",
            label="Maul",
            target_ref="ogre_target",
        )
    )
    result = without_rage._choose(
        next(
            option.id
            for option in without_rage._read().action_options
            if option.kind == "use_reckless_attack"
        )
    )
    event = next(event for event in result.events if event.type == "attack_resolved")
    assert _mapping(event.data["damage_roll_detail"])["additional_damage"] == []

    without_reckless = _prepared_session((12,))
    without_reckless._choose(_action_id(without_reckless, kind="feature", label="Rage"))
    without_reckless._choose(
        _action_id(
            without_reckless,
            kind="attack",
            label="Maul",
            target_ref="ogre_target",
        )
    )
    result = without_reckless._choose(
        next(
            option.id
            for option in without_reckless._read().action_options
            if option.kind == "decline_reckless_attack"
        )
    )
    event = next(event for event in result.events if event.type == "attack_resolved")
    assert _mapping(event.data["damage_roll_detail"])["additional_damage"] == []
