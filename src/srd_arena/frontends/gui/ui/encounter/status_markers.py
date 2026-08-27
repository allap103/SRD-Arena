"""Pure presentation helpers for battlefield token overlays."""

from dataclasses import dataclass
from typing import Literal

from ....shared.models import BattlefieldCreatureView

MarkerCorner = Literal["top_left", "top_right", "bottom_left", "bottom_right"]


@dataclass(frozen=True)
class StatusMarkerSpec:
    """Describe the corner, color, and explanation of one token status marker."""

    corner: MarkerCorner
    color: str
    tooltip: str


@dataclass(frozen=True)
class StatusMarkerHit:
    """Pair a painted marker's hover region with its tooltip text."""

    center_x: float
    center_y: float
    radius: float
    tooltip: str

    def contains(self, x: float, y: float) -> bool:
        """Return whether a point lies within the marker's hover target.

        >>> marker = StatusMarkerHit(10.0, 10.0, 3.0, "Prone")
        >>> marker.contains(12.0, 10.0)
        True
        >>> marker.contains(14.0, 10.0)
        False
        """
        delta_x = x - self.center_x
        delta_y = y - self.center_y
        return delta_x * delta_x + delta_y * delta_y <= self.radius * self.radius


def build_status_marker_specs(
    creature: BattlefieldCreatureView,
) -> tuple[StatusMarkerSpec, ...]:
    """Create only the concentration and status markers applicable to a token."""

    specs: list[StatusMarkerSpec] = []
    if creature.buffs:
        specs.append(
            StatusMarkerSpec(
                corner="top_left",
                color="#2eaf62",
                tooltip=_status_list_tooltip("Buffs", creature.buffs),
            )
        )
    if creature.debuffs:
        specs.append(
            StatusMarkerSpec(
                corner="top_right",
                color="#e05252",
                tooltip=_status_list_tooltip("Debuffs", creature.debuffs),
            )
        )
    if creature.is_concentrating:
        specs.append(
            StatusMarkerSpec(
                corner="bottom_left",
                color="#3887e8",
                tooltip="Concentrating on a spell",
            )
        )
    if creature.conditions:
        specs.append(
            StatusMarkerSpec(
                corner="bottom_right",
                color="#efc84a",
                tooltip=_status_list_tooltip("Conditions", creature.conditions),
            )
        )
    return tuple(specs)


def status_marker_positions(
    *,
    cell_x: float,
    cell_y: float,
    center_x: float,
    center_y: float,
    token_radius: float,
    cell_size: float,
) -> tuple[dict[MarkerCorner, tuple[float, float]], float]:
    """Place the four marker anchors around a token and return their radius."""

    marker_radius = max(4.0, cell_size * 0.065)
    token_offset = token_radius * 0.82
    cell_inset = max(marker_radius + 3.0, cell_size * 0.1)
    return (
        {
            "top_left": (
                center_x - token_offset,
                center_y - token_offset,
            ),
            "top_right": (
                center_x + token_offset,
                center_y - token_offset,
            ),
            "bottom_left": (
                cell_x + cell_inset,
                cell_y + cell_size - cell_inset,
            ),
            "bottom_right": (
                center_x + token_offset,
                center_y + token_offset,
            ),
        },
        marker_radius,
    )


def status_marker_hit_radius(marker_radius: float) -> float:
    """Return a comfortably hoverable radius without enlarging the marker."""

    return max(7.0, marker_radius * 1.5)


def target_allocation_badge_position(
    *,
    center_x: float,
    center_y: float,
    token_radius: float,
    top_right_reserved: bool,
) -> tuple[float, float]:
    """Keep the transient target-count badge clear of status markers."""

    if top_right_reserved:
        return center_x, center_y
    return center_x + token_radius * 0.72, center_y - token_radius * 0.72


def creature_name_label_rect(
    *,
    center_x: float,
    center_y: float,
    token_radius: float,
    cell_size: float,
    text_width: float,
    viewport_width: float,
    viewport_height: float,
    text_height: float = 0.0,
    horizontal_padding: float = 6.0,
    vertical_padding: float = 0.0,
) -> tuple[float, float, float, float]:
    """Size a floating name badge to its text and keep it in the viewport."""

    margin = 3.0
    available_width = max(1.0, viewport_width - margin * 2)
    available_height = max(1.0, viewport_height - margin * 2)
    label_width = min(
        max(cell_size - 6.0, text_width + horizontal_padding * 2),
        available_width,
    )
    label_height = min(
        max(16.0, text_height + vertical_padding * 2),
        available_height,
    )
    label_x = min(
        max(margin, center_x - label_width / 2),
        max(margin, viewport_width - margin - label_width),
    )
    preferred_y = center_y - token_radius - label_height - 4.0
    label_y = min(
        max(margin, preferred_y),
        max(margin, viewport_height - margin - label_height),
    )
    return label_x, label_y, label_width, label_height


def status_tooltip_label_rect(
    *,
    anchor_x: float,
    anchor_y: float,
    text_width: float,
    text_height: float,
    horizontal_padding: float,
    vertical_padding: float,
    viewport_width: float,
    viewport_height: float,
) -> tuple[float, float, float, float]:
    """Place a painted status tooltip beside its marker and inside the viewport."""

    margin = 3.0
    offset = 12.0
    available_width = max(1.0, viewport_width - margin * 2)
    available_height = max(1.0, viewport_height - margin * 2)
    label_width = min(text_width + horizontal_padding * 2, available_width)
    label_height = min(text_height + vertical_padding * 2, available_height)
    preferred_x = anchor_x + offset
    preferred_y = anchor_y + offset
    if preferred_x + label_width > viewport_width - margin:
        preferred_x = anchor_x - offset - label_width
    if preferred_y + label_height > viewport_height - margin:
        preferred_y = anchor_y - offset - label_height
    label_x = min(
        max(margin, preferred_x),
        max(margin, viewport_width - margin - label_width),
    )
    label_y = min(
        max(margin, preferred_y),
        max(margin, viewport_height - margin - label_height),
    )
    return label_x, label_y, label_width, label_height


def status_marker_tooltip(
    marker_hits: list[StatusMarkerHit],
    x: float,
    y: float,
) -> str | None:
    """Return the topmost marker tooltip under a battlefield pointer position."""

    hit = next(
        (candidate for candidate in reversed(marker_hits) if candidate.contains(x, y)),
        None,
    )
    return hit.tooltip if hit is not None else None


def _status_list_tooltip(title: str, labels: tuple[str, ...]) -> str:
    display_labels = tuple(
        dict.fromkeys(_status_display_name(label) for label in labels)
    )
    return "\n".join((f"{title}:", *(f"- {label}" for label in display_labels)))


def _status_display_name(label: str) -> str:
    if "_" in label or label.islower():
        return label.replace("_", " ").title()
    return label
