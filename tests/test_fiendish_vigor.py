"""Verify Fiendish Vigor as an alternate invocation of False Life."""

from pathlib import Path

import pytest

from srd_arena.content.character_options.classes import (
    load_class_catalog,
    load_optional_feature_catalog,
)
from srd_arena.content.common.paths import SYSTEM_CONTENT_ROOT
from srd_arena.content.creatures import (
    build_creature,
    load_character_snapshot_catalog,
)
from srd_arena.content.encounters import load_encounter_directory
from srd_arena.content.spells import load_spell_catalog
from srd_arena.domain.creatures import Creature
from srd_arena.domain.creatures.feature_rules import (
    spell_invocation_grants,
)
from srd_arena.domain.rolls.randomness import DiceRoller
from srd_arena.engine.queries import SpellOptionDetails
from srd_arena.engine.session import Session
from tests.encounter_runtime_support import player_first_initiative

pytestmark = pytest.mark.usefixtures(player_first_initiative.__name__)

WARLOCK_TRAINING_ENCOUNTER_DIR = (
    Path(__file__).parents[1] / "content" / "encounters" / "warlock_training"
)


def _canonical_warlock(level: int) -> Creature:
    snapshots = load_character_snapshot_catalog(SYSTEM_CONTENT_ROOT)
    return build_creature(
        snapshots.creature_template("warlock", level),
        classes=load_class_catalog(SYSTEM_CONTENT_ROOT),
        optional_features=load_optional_feature_catalog(SYSTEM_CONTENT_ROOT),
        spells=load_spell_catalog(SYSTEM_CONTENT_ROOT),
    )


def test_only_selected_level_exposes_fiendish_vigor_grant() -> None:
    """Keep the invocation tied to the level-five build's selected feature."""

    assert spell_invocation_grants(_canonical_warlock(4)) == ()
    level_five = _canonical_warlock(5)

    assert tuple(grant.id for grant in spell_invocation_grants(level_five)) == (
        "fiendish_vigor",
    )
    assert level_five.spellcasting is not None
    assert {spell.id for spell in level_five.spellcasting.feature_spells} == {
        "false_life"
    }
    assert "false_life" not in {
        spell.id for spell in level_five.spellcasting.learned_spells
    }


def test_fiendish_vigor_cast_is_free_fixed_and_maximized() -> None:
    """Cast False Life through its feature grant without spending a Pact slot."""

    session = Session(
        load_encounter_directory(WARLOCK_TRAINING_ENCOUNTER_DIR),
        dice=DiceRoller(die_roller=lambda _sides: 1),
    )
    session._read()
    assert session.encounter_state is not None
    warlock = session.encounter_state.creatures["warlock"].creature
    assert warlock.spellcasting is not None
    warlock.spellcasting.spell_slots_remaining[3] = 0

    option = next(
        option
        for option in session._read().action_options
        if option.label == "Cast False Life (Fiendish Vigor)"
    )
    assert option.enabled
    assert option.id == "spell-false_life-warlock-via-fiendish_vigor"
    assert isinstance(option.details, SpellOptionDetails)
    assert option.details.source_id == "false_life"
    assert option.details.grant_id == "fiendish_vigor"
    assert option.details.resource_level == 1

    outcome = session._choose(option.id)

    assert warlock.temporary_hit_points == 12
    assert warlock.spellcasting.spell_slots_remaining == {3: 0}
    event = next(event for event in outcome.events if event.type == "spell_cast")
    assert event.data["spell_id"] == "false_life"
    assert event.data["grant_id"] == "fiendish_vigor"
    assert event.data["slot_level"] == 1
    assert event.data["spell_slots_remaining"] is None
    detail = event.data["temporary_hit_point_detail"]
    assert isinstance(detail, dict)
    assert detail["dice_values"] == [4, 4]
    assert detail["total"] == 12
