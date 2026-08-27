"""Project engine action choices into application read models."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from srd_arena.domain.geometry import (
    Position,
    Vector2D,
    build_directional_area,
    build_point_cube_area,
    build_radius_area,
    serialize_area,
)
from srd_arena.domain.spells.rules import (
    parse_spell_action_slot,
    parse_spell_action_value,
    spell_area_shape,
    spell_range_squares,
)
from srd_arena.engine.models import ActionView, SceneView

from .observation_models import (
    ActionObservation,
    ActionReasonObservation,
    SceneObservation,
)


def observe_scene(scene: SceneView, state: Any | None) -> SceneObservation:
    return SceneObservation(
        scene_id=scene.scene_id,
        scene_text=scene.scene_text,
        action_details=tuple(
            _observe_action(action, state) for action in scene.action_details
        ),
    )


def _observe_action(action: ActionView, state: Any | None) -> ActionObservation:
    reason_messages = action.unavailable_reasons or (
        (action.unavailable_reason,) if action.unavailable_reason else ()
    )
    reason_codes = action.unavailable_codes or tuple(
        action.availability for _ in reason_messages
    )
    semantics = _action_semantics(action, state)
    return ActionObservation(
        id=action.id,
        label=action.label,
        kind=action.kind,
        creature_ref=action.creature_ref,
        cost=MappingProxyType(dict(action.cost)),
        enabled=action.enabled,
        availability=action.availability,
        reasons=tuple(
            ActionReasonObservation(code=code, message=message)
            for code, message in zip(reason_codes, reason_messages, strict=False)
        ),
        source_trigger_id=action.source_trigger_id,
        preferred_attack_type=action.preferred_attack_type,
        preferred_attack_name=action.preferred_attack_name,
        **semantics,
    )


def _action_semantics(
    action: ActionView,
    state: Any | None,
) -> dict[str, Any]:
    if state is None:
        return {}
    creature_state = state.creatures.get(action.creature_ref)
    if creature_state is None:
        return {}
    creature = creature_state.creature
    if action.kind in {"spell", "toggle_spell_target"}:
        source_id, target_ref, aim_point = _spell_action_parts(action)
        spell = _find_spell(creature, source_id)
        return {
            "source_id": source_id,
            "source_label": spell.name if spell is not None else source_id,
            "source_level": spell.level if spell is not None else None,
            "resource_level": (
                parse_spell_action_slot(action.value)
                if action.kind == "spell" and isinstance(action.value, str)
                else None
            ),
            "target_ref": target_ref,
            "aim_point": aim_point,
            "area_preview": _spell_area_preview(state, creature_state, spell, aim_point),
        }
    if action.kind == "stat_block":
        definition = creature.stat_block_actions.get(action.preferred_attack_name or "")
        return {
            "source_id": action.preferred_attack_name,
            "source_label": action.preferred_attack_name,
            "target_ref": _direct_target_ref(action.value),
            "area_preview": _stat_block_area_preview(
                state,
                creature_state,
                definition,
            ),
        }
    if action.kind == "feature" and isinstance(action.value, str):
        return {"feature_id": action.value}
    if action.kind == "move" and isinstance(action.value, str):
        return {"movement_direction": action.value}
    if action.kind == "set_spell_resource_allocation" and isinstance(
        action.value, str
    ):
        return {"target_ref": action.value.rpartition("~")[0]}
    if action.kind in {"attack", "grapple", "opportunity_attack"}:
        return {"target_ref": _direct_target_ref(action.value)}
    return {}


def _spell_action_parts(
    action: ActionView,
) -> tuple[str | None, str | None, tuple[float, float] | None]:
    if action.kind == "spell" and isinstance(action.value, str):
        return parse_spell_action_value(action.value)
    return (
        action.source_trigger_id,
        action.value if isinstance(action.value, str) else None,
        None,
    )


def _direct_target_ref(
    value: str | int | tuple[float, float] | None,
) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return f"participant:{value}"
    return None


def _find_spell(creature: Any, spell_id: str | None) -> Any | None:
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
    state: Any,
    creature_state: Any,
    spell: Any | None,
    aim_point: tuple[float, float] | None,
) -> dict[str, object] | None:
    if spell is None or aim_point is not None:
        return None
    grid = state.definition.grid
    if spell.geometry_mode == "point_area":
        if spell.area_size_feet is None:
            return None
        size_squares = int(
            grid.distance_from_feet(spell.area_size_feet, minimum=1)
        )
        area = (
            build_point_cube_area(Position(0, 0), size_squares, grid)
            if spell_area_shape(spell) == "cube"
            else build_radius_area(Position(0, 0), size_squares, grid)
        )
        return serialize_area(area)
    if spell.geometry_mode != "directional_area":
        return None
    length = spell_range_squares(spell, grid)
    if length is None:
        return None
    return serialize_area(
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
    )


def _stat_block_area_preview(
    state: Any,
    creature_state: Any,
    definition: Any | None,
) -> dict[str, object] | None:
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
    return serialize_area(
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
    )
