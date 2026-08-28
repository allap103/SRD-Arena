"""Project engine action choices into application read models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from srd_arena.domain.creatures import Creature, StatBlockActionDefinition
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.state import EncounterCreatureState
from srd_arena.domain.geometry import (
    Position,
    Vector2D,
    build_directional_area,
    build_point_cube_area,
    build_radius_area,
    serialize_area,
)
from srd_arena.domain.spells import Spell
from srd_arena.domain.spells.rules import (
    spell_area_shape,
    spell_range_squares,
)
from srd_arena.engine.queries import (
    ActionOption,
    DirectTargetOptionDetails,
    FeatureOptionDetails,
    MovementOptionDetails,
    ResourceAllocationOptionDetails,
    SessionRead,
    SpellOptionDetails,
    StatBlockOptionDetails,
)

from .observation_models import (
    ActionObservation,
    ActionReasonObservation,
    SceneObservation,
)
from .values import ApplicationValue


@dataclass(frozen=True)
class _ActionSemantics:
    source_id: str | None = None
    source_label: str | None = None
    source_level: int | None = None
    resource_level: int | None = None
    feature_id: str | None = None
    movement_direction: str | None = None
    target_ref: str | None = None
    aim_point: tuple[float, float] | None = None
    area_preview: Mapping[str, ApplicationValue] | None = None


def observe_scene(read: SessionRead) -> SceneObservation:
    """Project the engine's advertised choices into immutable client action data.

    >>> read = SessionRead(
    ...     scene_id="demo", scene_text="Choose", action_options=(
    ...         ActionOption("exit", "Exit", "system_exit", ""),),
    ...     encounter_state=None, transition_message=None, team_ids=(),
    ...     creature_labels={}, creature_team_ids={}, item_names={},
    ...     requires_automatic_advance=False)
    >>> scene = observe_scene(read)
    >>> (scene.scene_id, scene.action_details[0].label)
    ('demo', 'Exit')
    """

    return SceneObservation(
        scene_id=read.scene_id,
        scene_text=read.scene_text,
        action_details=tuple(
            _observe_action(option, read.encounter_state)
            for option in read.action_options
        ),
    )


def _observe_action(
    option: ActionOption,
    state: EncounterState | None,
) -> ActionObservation:
    reason_entries = tuple(
        dict.fromkeys(
            (failure.code, failure.message) for failure in option.eligibility.failures
        )
    )
    semantics = _action_semantics(option, state)
    return ActionObservation(
        id=option.id,
        label=option.label,
        kind=option.kind,
        creature_ref=option.creature_ref,
        cost=MappingProxyType(
            {
                "movement": option.cost.movement,
                "action": option.cost.action,
                "bonus_action": option.cost.bonus_action,
                "reaction": option.cost.reaction,
            }
        ),
        enabled=option.enabled,
        availability=option.availability,
        reasons=tuple(
            ActionReasonObservation(code=code, message=message)
            for code, message in reason_entries
        ),
        source_trigger_id=option.source_trigger_id,
        preferred_attack_type=option.preferred_attack_type,
        preferred_attack_name=option.preferred_attack_name,
        source_id=semantics.source_id,
        source_label=semantics.source_label,
        source_level=semantics.source_level,
        resource_level=semantics.resource_level,
        feature_id=semantics.feature_id,
        movement_direction=semantics.movement_direction,
        target_ref=semantics.target_ref,
        aim_point=semantics.aim_point,
        area_preview=semantics.area_preview,
    )


def _action_semantics(
    action: ActionOption,
    state: EncounterState | None,
) -> _ActionSemantics:
    if state is None:
        return _ActionSemantics()
    creature_state = state.creatures.get(action.creature_ref)
    if creature_state is None:
        return _ActionSemantics()
    creature = creature_state.creature
    details = action.details
    if isinstance(details, SpellOptionDetails):
        spell = _find_spell(creature, details.source_id)
        return _ActionSemantics(
            source_id=details.source_id,
            source_label=(spell.name if spell is not None else details.source_id),
            source_level=spell.level if spell is not None else None,
            resource_level=details.resource_level,
            target_ref=details.target_ref,
            aim_point=details.aim_point,
            area_preview=_spell_area_preview(
                state,
                creature_state,
                spell,
                details.aim_point,
            ),
        )
    if isinstance(details, StatBlockOptionDetails):
        definition = creature.stat_block_actions.get(details.source_id or "")
        return _ActionSemantics(
            source_id=details.source_id,
            source_label=details.source_id,
            target_ref=details.target_ref,
            area_preview=_stat_block_area_preview(
                state,
                creature_state,
                definition,
            ),
        )
    if isinstance(details, FeatureOptionDetails):
        return _ActionSemantics(feature_id=details.feature_id)
    if isinstance(details, MovementOptionDetails):
        return _ActionSemantics(movement_direction=details.direction)
    if isinstance(details, ResourceAllocationOptionDetails):
        return _ActionSemantics(target_ref=details.target_ref)
    if isinstance(details, DirectTargetOptionDetails):
        return _ActionSemantics(target_ref=details.target_ref)
    return _ActionSemantics()


def _find_spell(creature: Creature, spell_id: str | None) -> Spell | None:
    if spell_id is None or creature.spellcasting is None:
        return None
    return next(
        (
            spell
            for spell in creature.spellcasting.learned_spells
            if spell.id == spell_id
        ),
        None,
    )


def _spell_area_preview(
    state: EncounterState,
    creature_state: EncounterCreatureState,
    spell: Spell | None,
    aim_point: tuple[float, float] | None,
) -> Mapping[str, ApplicationValue] | None:
    if spell is None or aim_point is not None:
        return None
    grid = state.definition.grid
    if spell.geometry_mode == "point_area":
        if spell.area_size_feet is None:
            return None
        size_squares = int(grid.distance_from_feet(spell.area_size_feet, minimum=1))
        area = (
            build_point_cube_area(Position(0, 0), size_squares, grid)
            if spell_area_shape(spell) == "cube"
            else build_radius_area(Position(0, 0), size_squares, grid)
        )
        return cast(
            Mapping[str, ApplicationValue] | None,
            serialize_area(area),
        )
    if spell.geometry_mode != "directional_area":
        return None
    length = spell_range_squares(spell, grid)
    if length is None:
        return None
    return cast(
        Mapping[str, ApplicationValue] | None,
        serialize_area(
            build_directional_area(
                spell.range_data.get("type"),
                Position(creature_state.position.x, creature_state.position.y),
                Vector2D(1.0, 0.0),
                length,
                grid,
                coverage_threshold=(
                    state.geometry_config.directional_area_cell_coverage_threshold
                ),
            )
        ),
    )


def _stat_block_area_preview(
    state: EncounterState,
    creature_state: EncounterCreatureState,
    definition: StatBlockActionDefinition | None,
) -> Mapping[str, ApplicationValue] | None:
    target = getattr(definition, "target", None)
    shape = getattr(target, "shape", None)
    size_feet = getattr(target, "size_feet", None)
    if (
        getattr(target, "kind", None) != "area"
        or not isinstance(shape, str)
        or not isinstance(size_feet, int)
    ):
        return None
    grid = state.definition.grid
    width_feet = getattr(target, "width_feet", None)
    width_squares = max(
        1.0,
        (width_feet if isinstance(width_feet, int) else grid.square_size_feet)
        / grid.square_size_feet,
    )
    return cast(
        Mapping[str, ApplicationValue] | None,
        serialize_area(
            build_directional_area(
                shape,
                Position(creature_state.position.x, creature_state.position.y),
                Vector2D(1.0, 0.0),
                int(grid.distance_from_feet(size_feet, minimum=1)),
                grid,
                width_squares=width_squares,
                coverage_threshold=(
                    state.geometry_config.directional_area_cell_coverage_threshold
                ),
            )
        ),
    )
