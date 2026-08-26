from collections.abc import Mapping

import pytest

from srd_arena.application.commands import GameEvent
from srd_arena.application.observations import ActionObservation


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
            "cells": [{"x": 0, "y": 0}],
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
        data={"detail": {"rolls": [4, 5]}},
    )

    detail = event.data["detail"]
    assert isinstance(detail, Mapping)
    assert detail["rolls"] == (4, 5)
    with pytest.raises(TypeError):
        detail["rolls"] = ()  # type: ignore[index]
