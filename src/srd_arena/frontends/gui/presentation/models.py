"""Define read-only presentation projections consumed by the GUI adapter."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from srd_arena.engine.api import ActionObservation


@dataclass(frozen=True)
class SpellSlotTrackView:
    """Report remaining and maximum uses for one spell-slot level."""

    level: int
    remaining: int
    maximum: int


@dataclass(frozen=True)
class InitiativeTrackEntryView:
    """Describe one combatant's position in the displayed initiative order."""

    creature_ref: str
    name: str
    total: int
    is_active: bool = False


@dataclass(frozen=True)
class ResourceSummaryView:
    """Collect the active creature resources a frontend should summarize."""

    current_health: int
    max_health: int
    action_status: str
    bonus_action_status: str
    reaction_status: str
    attacks_available: int
    conditions: tuple[str, ...]
    spell_slots: tuple[SpellSlotTrackView, ...]
    movement_remaining: int
    movement_total: int
    movement_remaining_feet: int
    movement_total_feet: int
    initiative: tuple[InitiativeTrackEntryView, ...] = ()

    def __post_init__(self) -> None:
        """Detach every sequence from mutable projection-builder storage."""

        object.__setattr__(self, "conditions", tuple(self.conditions))
        object.__setattr__(self, "spell_slots", tuple(self.spell_slots))
        object.__setattr__(self, "initiative", tuple(self.initiative))

    def as_text(self) -> str:
        """Render the compact textual resource summary used by simple clients.

        >>> summary = ResourceSummaryView(8, 10, "Available", "Spent", "Available",
        ...     1, ("prone",), (), 4, 6, 20, 30)
        >>> summary.as_text().splitlines()[:5]
        ['Health: 8/10', 'Action: Available', 'Bonus Action: Spent', 'Reaction: Available', 'Conditions: Prone']
        """
        condition_text = (
            ", ".join(condition.capitalize() for condition in self.conditions)
            if self.conditions
            else "None"
        )
        return "\n".join(
            [
                f"Health: {self.current_health}/{self.max_health}",
                f"Action: {self.action_status}",
                f"Bonus Action: {self.bonus_action_status}",
                f"Reaction: {self.reaction_status}",
                f"Conditions: {condition_text}",
                *[
                    f"{slot.level}: {'□' * slot.remaining}{'■' * (slot.maximum - slot.remaining)}"
                    for slot in self.spell_slots
                ],
                f"Movement: {self.movement_remaining_feet}/{self.movement_total_feet} ft",
            ]
        )


@dataclass(frozen=True)
class GridPositionView:
    """Expose a creature's grid coordinates without leaking domain geometry."""

    x: int
    y: int


@dataclass(frozen=True)
class BattlefieldCreatureView:
    """Contain the read-only creature data needed to draw one battlefield token."""

    creature_ref: str
    creature_id: str
    name: str
    label: str
    token_image: str | None
    team_color: str
    position: GridPositionView
    health: int
    conditions: tuple[str, ...] = ()
    is_concentrating: bool = False
    buffs: tuple[str, ...] = ()
    debuffs: tuple[str, ...] = ()
    is_active: bool = False

    def __post_init__(self) -> None:
        """Detach displayed status labels from mutable builder storage."""

        object.__setattr__(self, "conditions", tuple(self.conditions))
        object.__setattr__(self, "buffs", tuple(self.buffs))
        object.__setattr__(self, "debuffs", tuple(self.debuffs))


@dataclass(frozen=True)
class BattlefieldView:
    """Contain the complete GUI snapshot of the combat grid."""

    width: int
    height: int
    creatures: tuple[BattlefieldCreatureView, ...]
    summary_text: str
    background_image: str | None = None
    grid_color: str = "#d3d3d3"
    grid_opacity: float = 1.0

    def __post_init__(self) -> None:
        """Detach the token sequence from mutable projection-builder storage."""

        object.__setattr__(self, "creatures", tuple(self.creatures))


@dataclass(frozen=True)
class EncounterView:
    """Group battlefield state and advertised actions for an encounter screen."""

    narrative_text: str | None
    battlefield: BattlefieldView
    resources: ResourceSummaryView
    movement_actions: Mapping[str, ActionObservation]
    non_movement_actions: tuple[ActionObservation, ...]
    feature_actions: tuple[ActionObservation, ...]
    end_turn_action: ActionObservation | None
    action_pane_title: str
    completion_message: str | None = None
    restart_action: ActionObservation | None = None

    def __post_init__(self) -> None:
        """Detach advertised actions from mutable projection-builder storage."""

        object.__setattr__(
            self,
            "movement_actions",
            MappingProxyType(dict(self.movement_actions)),
        )
        object.__setattr__(
            self,
            "non_movement_actions",
            tuple(self.non_movement_actions),
        )
        object.__setattr__(self, "feature_actions", tuple(self.feature_actions))


@dataclass(frozen=True)
class SessionPresentation:
    """Describe the current scene in the form consumed by any frontend."""

    scene_id: str
    story_actions: tuple[ActionObservation, ...]
    system_actions: tuple[ActionObservation, ...]
    encounter: EncounterView | None = None

    def __post_init__(self) -> None:
        """Detach scene action sequences from mutable projection-builder storage."""

        object.__setattr__(self, "story_actions", tuple(self.story_actions))
        object.__setattr__(self, "system_actions", tuple(self.system_actions))
