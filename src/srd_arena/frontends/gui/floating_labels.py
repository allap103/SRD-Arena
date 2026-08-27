"""Provide floating labels support for the gui package."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FloatingLabelStyle:
    """Visual tokens shared by painted labels and native Qt tooltips."""

    background_rgba: tuple[int, int, int, int]
    foreground: str
    corner_radius: int
    horizontal_padding: int
    vertical_padding: int
    font_point_size: int
    font_weight: int

    def qt_tooltip_rule(self) -> str:
        red, green, blue, alpha = self.background_rgba
        return f"""
QToolTip {{
    background-color: rgba({red}, {green}, {blue}, {alpha});
    color: {self.foreground};
    border: none;
    border-radius: {self.corner_radius}px;
    padding: {self.vertical_padding}px {self.horizontal_padding}px;
    font-size: {self.font_point_size}pt;
    font-weight: {self.font_weight};
}}
"""


BATTLEFIELD_FLOATING_LABEL_STYLE = FloatingLabelStyle(
    background_rgba=(16, 14, 11, 175),
    foreground="#f7edd9",
    corner_radius=4,
    horizontal_padding=8,
    vertical_padding=6,
    font_point_size=10,
    font_weight=700,
)
