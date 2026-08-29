import os
from dataclasses import FrozenInstanceError

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from srd_arena.frontends.gui.presentation.models import (
    BattlefieldCreatureView,
    BattlefieldView,
    GridPositionView,
)
from srd_arena.frontends.gui.ui.encounter import BattlefieldWidget
from srd_arena.frontends.gui.ui.encounter.battlefield_renderer import (
    BattlefieldRenderer,
    BattlefieldRenderInput,
)
from srd_arena.frontends.gui.ui.encounter.config import BattlefieldRenderGeometry


def test_renderer_returns_hit_regions_from_the_same_completed_paint() -> None:
    app = QApplication.instance() or QApplication([])
    battlefield = BattlefieldView(
        width=2,
        height=2,
        creatures=(
            BattlefieldCreatureView(
                creature_ref="hero",
                creature_id="hero",
                name="Hero",
                label="H",
                token_image=None,
                team_color="#3f7fd5",
                position=GridPositionView(0, 0),
                health=10,
                conditions=("Prone",),
            ),
        ),
        summary_text="",
    )
    geometry = BattlefieldRenderGeometry(
        viewport=(0, 0, 200, 200),
        origin_x=0,
        origin_y=0,
        cell_size=100,
        columns=2,
        rows=2,
    )
    render_input = BattlefieldRenderInput(
        battlefield=battlefield,
        geometry=geometry,
        area_overlay=None,
        movement_plan=None,
        hover_cell=(0, 0),
        targetable_creature_refs=frozenset({"hero"}),
        selected_creature_ref="hero",
        target_allocation_counts=(("hero", 2),),
        targeting_label="Choose a target",
        visible_status_tooltip=None,
        status_tooltip_anchor=None,
        show_team_outlines=True,
        always_show_creature_names=False,
        viewport_width=200,
        viewport_height=200,
    )
    image = QImage(200, 200, QImage.Format.Format_ARGB32)
    painter = QPainter(image)

    result = BattlefieldRenderer().paint(painter, render_input)
    painter.end()

    assert len(result.creature_hits) == 1
    assert result.creature_hits[0].creature_ref == "hero"
    assert (result.creature_hits[0].center_x, result.creature_hits[0].center_y) == (
        50,
        50,
    )
    assert [hit.tooltip for hit in result.status_marker_hits] == [
        "Conditions:\n- Prone"
    ]
    app.processEvents()


def test_battlefield_render_input_rejects_transient_state_mutation() -> None:
    cells = [{"x": 0, "y": 0}]
    overlay: dict[str, object] = {"shape": "radius", "cells": cells}
    render_input = BattlefieldRenderInput(
        battlefield=BattlefieldView(1, 1, (), ""),
        geometry=BattlefieldRenderGeometry((0, 0, 10, 10), 0, 0, 10, 1, 1),
        area_overlay=overlay,
        movement_plan=None,
        hover_cell=None,
        targetable_creature_refs=frozenset(),
        selected_creature_ref=None,
        target_allocation_counts=(),
        targeting_label=None,
        visible_status_tooltip=None,
        status_tooltip_anchor=None,
        show_team_outlines=True,
        always_show_creature_names=False,
        viewport_width=10,
        viewport_height=10,
    )

    with pytest.raises(FrozenInstanceError):
        render_input.targeting_label = "Changed"  # type: ignore[misc]

    overlay["shape"] = "line"
    cells[0]["x"] = 9
    assert render_input.area_overlay is not None
    assert render_input.area_overlay["shape"] == "radius"
    assert render_input.area_overlay["cells"] == ({"x": 0, "y": 0},)
    with pytest.raises(TypeError):
        render_input.area_overlay["shape"] = "cone"  # type: ignore[index]


def test_widget_keeps_viewport_geometry_and_hit_testing_aligned() -> None:
    app = QApplication.instance() or QApplication([])
    widget = BattlefieldWidget()
    widget.resize(324, 324)
    widget.set_battlefield(BattlefieldView(2, 2, (), ""))

    geometry = widget._render_geometry()

    assert (geometry.origin_x, geometry.origin_y, geometry.cell_size) == (
        12,
        12,
        150,
    )
    assert widget._cell_at_point(87, 87) == (0, 0)
    assert widget._cell_at_point(237, 237) == (1, 1)
    assert widget._cell_at_point(323, 323) is None
    assert widget._point_at_pixel(162, 87) == (1.0, 0.5)
    widget.deleteLater()
    app.processEvents()


def test_widget_clamps_zoomed_pan_without_exposing_empty_viewport() -> None:
    app = QApplication.instance() or QApplication([])
    widget = BattlefieldWidget()
    widget.resize(324, 324)
    widget.set_battlefield(BattlefieldView(2, 2, (), ""))
    widget._zoom = 2
    widget._pan_offset = (999, -999)

    geometry = widget._render_geometry()

    assert widget._pan_offset == (150, -150)
    assert geometry.origin_x == 12
    assert geometry.origin_y == -288
    assert geometry.origin_x + geometry.board_width == 612
    assert geometry.origin_y + geometry.board_height == 312
    widget.deleteLater()
    app.processEvents()
