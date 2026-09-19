"""Verify the canonical Barbarian's passive Danger Sense rules."""

from pathlib import Path

from srd_arena.content.character_options.classes import load_class_catalog
from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import (
    build_creature,
    load_character_snapshot_catalog,
)
from srd_arena.content.encounters import load_encounter_directory
from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.effects.runtime import EffectSourceKind
from srd_arena.domain.encounters.condition_state import apply_condition
from srd_arena.domain.encounters.rule_queries import roll_modifiers
from srd_arena.engine.session import Session

WARLOCK_TRAINING_ENCOUNTER_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "warlock_training"
)


def test_danger_sense_enters_the_canonical_progression_at_level_two() -> None:
    """Compile Danger Sense only once the Barbarian reaches level 2."""

    snapshots = load_character_snapshot_catalog(SYSTEM_CONTENT_ROOT)
    classes = load_class_catalog(SYSTEM_CONTENT_ROOT)
    level_one = build_creature(
        snapshots.creature_template("barbarian", 1),
        classes=classes,
    )
    level_two = build_creature(
        snapshots.creature_template("barbarian", 2),
        classes=classes,
    )

    assert "danger_sense" not in level_one.combat_profile.intrinsic_rule_providers
    assert "danger_sense" in level_two.combat_profile.intrinsic_rule_providers


def test_danger_sense_grants_only_dexterity_save_advantage() -> None:
    """Expose the passive feature through the shared roll query."""

    session = Session(load_encounter_directory(WARLOCK_TRAINING_ENCOUNTER_DIR))
    session._read()
    state = session.encounter_state
    assert state is not None

    dexterity = roll_modifiers(state, "barbarian", "saving_throw", "dexterity")

    assert dexterity.mode == "advantage"
    assert len(dexterity.contributions) == 1
    assert dexterity.contributions[0].source.kind is EffectSourceKind.FEATURE
    assert dexterity.contributions[0].source.definition_id == "danger_sense"
    assert (
        roll_modifiers(
            state,
            "barbarian",
            "saving_throw",
            "wisdom",
        ).mode
        == "normal"
    )


def test_incapacitation_blocks_danger_sense_including_when_implied() -> None:
    """Block the feature when another condition implies Incapacitated."""

    session = Session(load_encounter_directory(WARLOCK_TRAINING_ENCOUNTER_DIR))
    session._read()
    state = session.encounter_state
    assert state is not None
    apply_condition(
        state,
        build_applied_condition(
            condition=Condition.PARALYZED,
            source_ref="test",
            source_label="Test",
            target_ref="barbarian",
        ),
    )

    result = roll_modifiers(state, "barbarian", "saving_throw", "dexterity")

    assert result.mode == "normal"
    assert all(
        contribution.source.definition_id != "danger_sense"
        for contribution in result.contributions
    )
