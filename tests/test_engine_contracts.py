import json
from collections.abc import Mapping
from dataclasses import fields, is_dataclass

import pytest

from srd_arena.engine.api import (
    ActionObservation,
    AimAction,
    CancelTargeting,
    ChangeTarget,
    CommandResult,
    ConfirmTargeting,
    GameEvent,
    GameObservation,
    GameUpdate,
    SceneObservation,
    SelectAction,
    SetResourceAllocation,
)


def test_action_observation_values_are_recursively_immutable() -> None:
    action = ActionObservation(
        id="caster-fireball",
        label="Cast Fireball",
        kind="spell",
        creature_ref="caster",
        cost={"action": 1},
        area_preview={
            "shape": "radius",
            "origin": {"x": 0, "y": 0},
            "cells": ({"x": 0, "y": 0},),
        },
    )

    assert action.area_preview is not None
    assert isinstance(action.area_preview["origin"], Mapping)
    assert isinstance(action.area_preview["cells"], tuple)
    with pytest.raises(TypeError):
        action.area_preview["shape"] = "cone"  # type: ignore[index]
    with pytest.raises(TypeError):
        action.cost["action"] = 0  # type: ignore[index]


def test_game_event_values_are_recursively_immutable() -> None:
    event = GameEvent(
        seq=1,
        type="example",
        data={"detail": {"rolls": (4, 5)}},
    )

    detail = event.data["detail"]
    assert isinstance(detail, Mapping)
    assert detail["rolls"] == (4, 5)
    with pytest.raises(TypeError):
        detail["rolls"] = ()  # type: ignore[index]


def test_public_commands_and_observations_are_transport_shaped() -> None:
    observation = GameObservation(
        scene=SceneObservation(
            scene_id="example",
            scene_text="Choose an action.",
            action_details=(
                ActionObservation(
                    id="caster-fireball",
                    label="Cast Fireball",
                    kind="spell",
                    creature_ref="caster",
                    cost={"action": 1},
                    area_preview={"shape": "radius", "radius": 4},
                ),
            ),
        ),
        encounter=None,
        transition=None,
        requires_automatic_advance=False,
    )
    update = GameUpdate(
        observation=observation,
        messages=(("system", "Ready."),),
        events=(
            GameEvent(
                seq=1,
                type="example",
                data={"rolls": (4, 5)},
            ),
        ),
        selected_action_id=None,
        selected_choice_text=None,
        scene_changed=False,
        should_exit=False,
    )
    boundary_values = (
        SelectAction("wait", expected_decision_id="decision-1"),
        AimAction("fireball", 4.5, 3.5, expected_decision_id="decision-1"),
        ChangeTarget("target", False, "decision-1"),
        SetResourceAllocation("target", 10, "decision-1"),
        ConfirmTargeting("decision-1"),
        CancelTargeting("decision-1"),
        observation,
        CommandResult(update=update),
    )

    for value in boundary_values:
        json.dumps(_to_json_value(value))


def _to_json_value(value: object) -> object:
    """Mechanically convert an engine contract into JSON-shaped data."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _to_json_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        assert all(isinstance(key, str) for key in value)
        return {key: _to_json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_to_json_value(item) for item in value]
    raise AssertionError(f"Engine contract contains non-transport value {value!r}.")
