"""Coverage candidates reuse runtime geometry without reading hidden state."""

from dataclasses import replace
from pathlib import Path
from typing import Literal

import numpy as np
import pytest
import torch

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.domain.encounters.actions.option_discovery.spell_areas import (
    spell_area_targets,
)
from srd_arena.domain.encounters.encounter_models.decisions import DecisionFrame
from srd_arena.domain.encounters.terrain import CoverDegree, TerrainCell
from srd_arena.domain.geometry import GeometryConfig, Position
from srd_arena.engine.api import (
    FilteredAction,
    FilteredObservation,
    PolicyProjector,
    PositionObservation,
    Session,
    area_aims,
)
from srd_arena.frontends.headless.config import load_policy
from srd_arena.frontends.rl.actions import candidates
from srd_arena.frontends.rl.encoding import ACTION_FEATURES, Encoder
from srd_arena.training.model import CandidatePolicy


def encounter(threshold: float = 0.5, wall: bool = False) -> Session:
    """Arrange living allies and enemies around a caster for cone comparisons."""
    game = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
    game.observe()
    state = game.encounter_state
    assert state is not None
    state.interrupts.decision_stack.clear()
    state.turn.index = state.initiative_order.index("warlock")
    state.interrupts.decision_stack.append(
        DecisionFrame("coverage-test", "warlock", "turn", "test")
    )
    placements = {
        "warlock": (3, 3),
        "barbarian": (3, 5),
        "goblin_1": (4, 3),
        "goblin_2": (5, 3),
        "goblin_3": (4, 4),
    }
    for ref, point in placements.items():
        state.creatures[ref].position = Position(*point)
    state.definition = replace(
        state.definition,
        terrain=(TerrainCell(Position(4, 3), cover=CoverDegree.TOTAL),) if wall else (),
    )
    state.creatures["goblin_2"].creature.size = "L"
    state.geometry_config = GeometryConfig(threshold)
    return game


def observation(game: Session, profile: str = "training") -> FilteredObservation:
    """Project the configured player information boundary."""
    return PolicyProjector(
        load_policy(Path(f"config/observations/{profile}.yaml")), "warlock"
    ).project(game.observe_gameplay())


def spell_action(
    view: FilteredObservation, spell_id: str = "burning_hands"
) -> FilteredAction:
    """Find an advertised cast through its public descriptor."""
    return next(
        a for a in view.action_details if a.spell and a.spell.spell_id == spell_id
    )


@pytest.mark.parametrize(
    "spell_id", ["burning_hands", "fireball", "hypnotic_pattern", "stinking_cloud"]
)
@pytest.mark.parametrize("threshold", [0.1, 0.5])
@pytest.mark.parametrize("wall", [False, True])
def test_every_aim_matches_runtime_coverage(
    threshold: float, wall: bool, spell_id: str
) -> None:
    game = encounter(threshold, wall)
    view = observation(game)
    action = spell_action(view, spell_id)
    groups = area_aims(view, action)
    assert groups is not None and action.area_template is not None
    if action.area_template.placement == "directional":
        assert action.area_template.coverage_threshold == threshold
    state = game.encounter_state
    assert state is not None
    actor = state.creatures["warlock"].creature
    assert actor.spellcasting is not None
    spell = next(s for s in actor.spellcasting.learned_spells if s.id == spell_id)
    disclosed = {c.creature_ref for c in view.creatures if c.knowledge == "current"}

    def targets(aim: tuple[float, float]) -> tuple[str, ...]:
        """Use runtime area and footprint resolution as an independent reference."""
        return tuple(
            sorted(
                t.target_ref
                for t in spell_area_targets(state, actor, spell, aim_point=aim)
                if t.target_ref in disclosed
            )
        )

    expected = {
        targets((float(x), float(y)))
        for y in range(view.grid.height)
        for x in range(view.grid.width)
    }
    assert {g.creature_refs for g in groups} == expected
    assert len(groups) == view.grid.width * view.grid.height
    assert len({g.aim for g in groups}) == len(groups)
    assert len(expected) < len(groups)
    assert all(targets(g.aim) == g.creature_refs for g in groups)
    assert any("barbarian" in g for g in expected)


@pytest.mark.parametrize(
    "spell_id", ["burning_hands", "fireball", "hypnotic_pattern", "stinking_cloud"]
)
def test_last_known_and_hidden_creatures_cannot_affect_coverage(spell_id: str) -> None:
    view = observation(encounter())
    action = spell_action(view, spell_id)
    for knowledge in ("unknown", "last_known"):
        hidden = replace(
            view,
            creatures=tuple(
                replace(c, knowledge=knowledge, currently_visible=False)
                if c.allegiance == "enemy"
                else c
                for c in view.creatures
            ),
        )
        changed = replace(
            hidden,
            creatures=tuple(
                replace(c, position=PositionObservation(0, 0), size="G", defeated=True)
                if c.allegiance == "enemy"
                else c
                for c in hidden.creatures
            ),
        )
        assert area_aims(hidden, action) == area_aims(changed, action)
        assert all(
            "goblin" not in ref
            for g in area_aims(hidden, action) or ()
            for ref in g.creature_refs
        )


def test_policy_omission_keeps_all_aims_with_unknown_coverage() -> None:
    game = encounter()
    view = observation(game)
    action = spell_action(view)
    missing = replace(
        view,
        creatures=tuple(
            replace(c, size=None) if c.creature_ref == "warlock" else c
            for c in view.creatures
        ),
    )
    assert area_aims(missing, action) is None
    count = view.grid.width * view.grid.height
    fallback = [
        c
        for c in candidates(missing)
        if c.spell and c.spell.spell_id == "burning_hands"
    ]
    assert len(fallback) == count and all(c.affected_refs is None for c in fallback)
    player = observation(game, "player")
    assert all(a.area_template is None for a in player.action_details)
    assert all(c.affected_refs is None for c in candidates(player))
    for spell_id in ("fireball", "hypnotic_pattern", "stinking_cloud"):
        others = [
            c for c in candidates(view) if c.spell and c.spell.spell_id == spell_id
        ]
        assert len(others) == count and all(c.affected_refs is not None for c in others)


def test_coverage_tensor_routes_creatures_and_changes_policy_scores() -> None:
    view = observation(encounter())
    choices = candidates(view)
    encoder = Encoder(view)
    encoded = encoder.encode(view, choices)
    for index, choice in enumerate(choices):
        actual = {
            encoder.refs[slot]
            for slot in np.flatnonzero(encoded.affected_entity_mask[index])
        }
        assert actual == set(choice.affected_refs or ())
        assert encoded.actions[index, ACTION_FEATURES.index("coverage_known")] == (
            choice.affected_refs is not None
        )
    assert not encoded.affected_entity_mask[:, len(encoder.refs) :].any()
    torch.manual_seed(2)
    model = CandidatePolicy(8)
    baseline = model(encoded)[0].detach()
    changed = replace(
        encoded, affected_entity_mask=np.zeros_like(encoded.affected_entity_mask)
    )
    scores = model(changed)[0].detach()
    covered = encoded.affected_entity_mask.any(axis=1)
    assert covered.any() and not torch.equal(baseline[covered], scores[covered])
    assert torch.equal(baseline[~covered], scores[~covered])


@pytest.mark.parametrize(
    "spell_id", ["burning_hands", "fireball", "hypnotic_pattern", "stinking_cloud"]
)
def test_casts_resolve_advertised_nonempty_coverage(spell_id: str) -> None:
    from srd_arena.engine.api import AimAction

    initial = observation(encounter())
    expected = area_aims(initial, spell_action(initial, spell_id))
    assert expected is not None
    seen = set()
    for group in expected:
        if not group.creature_refs or group.creature_refs in seen:
            continue
        seen.add(group.creature_refs)
        game = encounter()
        view = observation(game)
        action = spell_action(view, spell_id)
        before = len(game.observe_gameplay().history)
        result = game.execute_player(
            "heroes", AimAction(action.id, *group.aim, view.decision.id)
        )
        assert result.accepted, result.failure
        event = next(
            e
            for e in game.observe_gameplay().history[before:]
            if e.type == "spell_cast"
        )
        refs = event.data["target_refs"]
        assert isinstance(refs, tuple)
        assert set(refs) == set(group.creature_refs)


def test_movement_recomputes_coverage_and_mask_is_permutation_consistent() -> None:
    game = encounter()
    before = observation(game)
    before_groups = area_aims(before, spell_action(before))
    state = game.encounter_state
    assert state is not None
    state.creatures["warlock"].position = Position(3, 2)
    after = observation(game)
    after_groups = area_aims(after, spell_action(after))
    assert before_groups != after_groups
    assert (
        area_aims(
            replace(after, creatures=tuple(reversed(after.creatures))),
            spell_action(after),
        )
        == after_groups
    )
    choices = candidates(after)
    encoder = Encoder(after)
    a = encoder.encode(after, choices)
    b = encoder.encode(after, tuple(reversed(choices)))
    assert np.array_equal(a.affected_entity_mask, b.affected_entity_mask[::-1])


@pytest.mark.parametrize("shape", ["cone", "line", "cube"])
def test_directional_geometry_is_independent_of_spell_identity(
    shape: Literal["cone", "line", "cube"],
) -> None:
    from srd_arena.domain.spells.metadata import SpellRange, SpellRangeDistance

    game = encounter(wall=True)
    state = game.encounter_state
    assert state is not None
    actor = state.creatures["warlock"].creature
    casting = actor.spellcasting
    assert casting is not None
    original = next(s for s in casting.learned_spells if s.id == "burning_hands")
    spell = replace(
        original,
        id="test_area",
        name="Test area",
        range=SpellRange(shape, SpellRangeDistance("feet", 15)),
    )
    casting.learned_spells.append(spell)
    view = observation(game)
    action = spell_action(view, "test_area")
    assert action.area_template is not None
    assert action.area_template.shape == shape
    assert action.area_template.placement == "directional"
    aims = area_aims(view, action)
    assert aims is not None
    disclosed = {c.creature_ref for c in view.creatures if c.knowledge == "current"}
    for item in aims:
        expected = {
            t.target_ref
            for t in spell_area_targets(state, actor, spell, aim_point=item.aim)
            if t.target_ref in disclosed
        }
        assert set(item.creature_refs) == expected


def test_equal_coverage_retains_distinct_positions_and_candidate_capacity() -> None:
    view = observation(encounter())
    choices = candidates(view)
    for spell_id in ("burning_hands", "fireball", "hypnotic_pattern", "stinking_cloud"):
        aims = [c for c in choices if c.spell and c.spell.spell_id == spell_id]
        assert len(aims) == view.grid.width * view.grid.height
        assert len({c.aim for c in aims}) == len(aims)
        assert len({c.affected_refs for c in aims}) < len(aims)
        assert all(c.affected_refs is not None for c in aims)
    with pytest.raises(ValueError, match="action candidates"):
        candidates(view, maximum=len(choices) - 1)


@pytest.mark.parametrize("field", ["position", "size", "defeated"])
def test_missing_current_footprint_information_is_unknown_for_every_area(
    field: str,
) -> None:
    view = observation(encounter())
    missing = replace(
        view,
        creatures=tuple(
            replace(
                c,
                position=None if field == "position" else c.position,
                size=None if field == "size" else c.size,
                defeated=None if field == "defeated" else c.defeated,
            )
            if c.creature_ref == "goblin_1"
            else c
            for c in view.creatures
        ),
    )
    for spell_id in ("burning_hands", "fireball", "hypnotic_pattern", "stinking_cloud"):
        assert area_aims(missing, spell_action(missing, spell_id)) is None


def test_defeated_creatures_are_excluded_and_terrain_changes_recompute_coverage() -> (
    None
):
    game = encounter()
    before = observation(game)
    action = spell_action(before, "fireball")
    baseline = area_aims(before, action)
    assert baseline is not None
    dead = replace(
        before,
        creatures=tuple(
            replace(c, defeated=True) if c.creature_ref == "goblin_1" else c
            for c in before.creatures
        ),
    )
    assert all("goblin_1" not in a.creature_refs for a in area_aims(dead, action) or ())
    wall = observation(encounter(wall=True))
    assert area_aims(wall, spell_action(wall, "fireball")) != baseline
