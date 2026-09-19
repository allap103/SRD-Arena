"""Spell semantics survive permitted projection without leaking enemy catalogs."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.engine.api import PolicyProjector, Session
from srd_arena.frontends.headless.config import load_policy
from srd_arena.frontends.rl.actions import candidates
from srd_arena.frontends.rl.encoding import Encoder
from tests.encounter_runtime_support import player_first_initiative

pytestmark = pytest.mark.usefixtures(player_first_initiative.__name__)


def test_permitted_spell_candidates_are_distinct_and_grants_match() -> None:
    game = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    snapshot = game.observe_gameplay()
    policy = load_policy(Path("config/observations/training.yaml"))
    observation = PolicyProjector(policy, "warlock").project(snapshot)
    choices = candidates(observation)
    encoded = Encoder(observation).encode(observation, choices)
    rows = {
        c.spell.spell_id: encoded.actions[i]
        for i, c in enumerate(choices)
        if c.spell and c.aim == (2.0, 1.0)
    }
    for a, b in (
        ("fireball", "hypnotic_pattern"),
        ("fireball", "stinking_cloud"),
        ("hypnotic_pattern", "stinking_cloud"),
    ):
        assert not np.array_equal(rows[a], rows[b])
    vigor = next(
        c.spell for c in choices if c.spell and c.spell.spell_id == "false_life"
    )
    assert vigor.grant_id == "fiendish_vigor"
    assert vigor.spell_slot_cost == 0 and vigor.cast_level == 1
    # Mutating enemy definitions cannot affect permitted allied action descriptions.
    changed = replace(
        snapshot,
        creatures=tuple(
            replace(c, spell_capabilities=snapshot.creatures[0].spell_capabilities)
            if c.combat.creature_ref != "warlock"
            else c
            for c in snapshot.creatures
        ),
    )
    assert PolicyProjector(policy, "warlock").project(changed) == observation


def test_hidden_policy_still_removes_spell_semantics() -> None:
    game = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    policy = load_policy(Path("config/observations/player.yaml"))
    observation = PolicyProjector(policy, "warlock").project(game.observe_gameplay())
    assert observation.action_details
    assert all(a.spell is None for a in observation.action_details)
    assert all(c.spell is None for c in candidates(observation))


def test_effects_describe_damage_control_and_persistent_cloud() -> None:
    from srd_arena.frontends.headless.serialization import json_value
    from srd_arena.frontends.rl.mechanics_encoding import (
        MECHANIC_FEATURES,
        mechanics_features,
    )

    game = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    catalog = game.observe_player("heroes").creature("warlock").spell_capabilities
    assert catalog is not None
    spells = {s.spell_id: s for s in catalog}
    assert spells["hex"].mechanics["duration_rounds"] == 4800
    vectors = {
        key: dict(zip(MECHANIC_FEATURES, mechanics_features(spells[key]), strict=True))
        for key in (
            "fireball",
            "hypnotic_pattern",
            "stinking_cloud",
            "false_life",
            "burning_hands",
        )
    }
    assert vectors["fireball"]["failure_damage_fire"] == 0.28
    assert vectors["fireball"]["half_damage_on_save"] == 1
    assert vectors["hypnotic_pattern"]["failure_damage_fire"] == 0
    assert vectors["hypnotic_pattern"]["failure_condition_incapacitated"] == 1
    assert vectors["hypnotic_pattern"]["ends_on_damage"] == 1
    assert vectors["hypnotic_pattern"]["ends_on_assistance"] == 1
    cloud = vectors["stinking_cloud"]
    assert (
        cloud["persistent_area"]
        == cloud["obscures_vision"]
        == cloud["repeat_save"]
        == 1
    )
    assert cloud["later_condition_poisoned"] == cloud["effect_action_prohibition"] == 1
    assert cloud["automatic_condition_poisoned"] == 0
    assert vectors["false_life"]["automatic_temporary_hp"] == 0.12
    assert vectors["burning_hands"]["failure_damage_fire"] == 0.175  # 5d6 at level 3
    # JSON remains structured and the detached descriptor cannot be mutated.
    document = json_value(spells["fireball"].mechanics)
    assert isinstance(document, dict) and document["schema_id"] == "spell-mechanics-v1"
    with pytest.raises(TypeError):
        spells["fireball"].mechanics["definition"] = None  # type: ignore[index]


def test_damage_encoding_changes_without_changing_spell_identity() -> None:
    from srd_arena.domain.capabilities import DamageEffect, SavingThrowResolution
    from srd_arena.engine.spell_capability_observations import (
        observe_spell_capabilities,
    )
    from srd_arena.frontends.rl.spell_encoding import spell_features

    game = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    game.observe()
    state = game.encounter_state
    assert state is not None
    actor = state.creatures["warlock"].creature
    casting = actor.spellcasting
    assert casting is not None
    before = next(
        s for s in observe_spell_capabilities(actor) if s.spell_id == "fireball"
    )
    spell = next(s for s in casting.learned_spells if s.id == "fireball")
    definition = spell.definition
    assert definition is not None and isinstance(
        definition.resolution, SavingThrowResolution
    )
    resolution = definition.resolution
    stage = resolution.failure[0]
    stronger = replace(
        spell,
        definition=replace(
            definition,
            resolution=replace(
                resolution,
                failure=(replace(stage, effects=(DamageEffect("12d6", 0, "fire"),)),),
            ),
        ),
    )
    index = casting.learned_spells.index(spell)
    casting.learned_spells[index] = stronger
    after = next(
        s for s in observe_spell_capabilities(actor) if s.spell_id == "fireball"
    )
    assert before.spell_id == after.spell_id
    assert spell_features(before) != spell_features(after)
    # A descriptor already returned by the engine is a snapshot, not a live definition.
    assert before.mechanics != after.mechanics


def test_enemy_action_never_discloses_its_spell_catalog() -> None:
    game = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    snapshot = game.observe_gameplay()
    warlock = next(c for c in snapshot.creatures if c.combat.creature_ref == "warlock")
    team = next(t for t in snapshot.teams if t.team_id == "heroes")
    fireball = next(a for a in team.movement_actions if a.source_id == "fireball")
    # Even an advertised enemy action cannot be joined to its private catalog.
    snapshot = replace(
        snapshot,
        creatures=tuple(
            replace(c, spell_capabilities=warlock.spell_capabilities)
            if c.combat.creature_ref == "goblin_1"
            else c
            for c in snapshot.creatures
        ),
        teams=tuple(
            replace(t, movement_actions=(replace(fireball, creature_ref="goblin_1"),))
            if t.team_id == "heroes"
            else t
            for t in snapshot.teams
        ),
    )
    policy = load_policy(Path("config/observations/training.yaml"))
    observation = PolicyProjector(policy, "warlock").project(snapshot)
    assert len(observation.action_details) == 1
    assert observation.action_details[0].spell is None
