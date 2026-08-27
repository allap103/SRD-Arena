"""Action requests and costs shared across encounter workflows."""

from __future__ import annotations

from dataclasses import dataclass, field

from ...geometry import MovementCost

CreatureRef = str


@dataclass
class ActionCost:
    """Count movement and turn resources consumed by an encounter action."""

    movement: MovementCost = field(default_factory=lambda: MovementCost(0))
    action: int = 0
    bonus_action: int = 0
    reaction: int = 0

    def __post_init__(self) -> None:
        self.movement = MovementCost(self.movement)


@dataclass
class EncounterAction:
    """Describe one stable, selectable choice at an encounter decision point.

    Actions carry runtime identity, actor, cost, and compact selection data;
    reusable rules mechanics remain on the referenced capability or source.
    """

    label: str
    kind: str
    value: str | int | tuple[float, float] | None = None
    id: str = ""
    creature_ref: CreatureRef | None = None
    source_trigger_id: str | None = None
    preferred_attack_type: str | None = None
    preferred_attack_name: str | None = None
    cost: ActionCost = field(default_factory=ActionCost)
