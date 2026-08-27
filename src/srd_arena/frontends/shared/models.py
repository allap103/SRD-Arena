"""Frontend-neutral presentation models."""

from __future__ import annotations

from dataclasses import dataclass

from srd_arena.application.api import ActionObservation


@dataclass(frozen=True)
class SpellSlotTrackView:
    level: int
    remaining: int
    maximum: int


@dataclass(frozen=True)
class InitiativeTrackEntryView:
    creature_ref: str
    name: str
    total: int
    is_active: bool = False


@dataclass
class ResourceSummaryView:
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

    def as_text(self) -> str:
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


@dataclass
class GridPositionView:
    x: int
    y: int


@dataclass
class BattlefieldCreatureView:
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


@dataclass
class BattlefieldView:
    width: int
    height: int
    creatures: list[BattlefieldCreatureView]
    summary_text: str
    background_image: str | None = None
    grid_color: str = "#d3d3d3"
    grid_opacity: float = 1.0


@dataclass
class EncounterView:
    narrative_text: str | None
    battlefield: BattlefieldView
    resources: ResourceSummaryView
    movement_actions: dict[str, ActionObservation]
    non_movement_actions: list[ActionObservation]
    feature_actions: list[ActionObservation]
    end_turn_action: ActionObservation | None
    action_pane_title: str
    transition_message: str | None = None
    transition_action: ActionObservation | None = None


@dataclass
class SessionPresentation:
    scene_id: str
    story_text: str | None
    story_actions: list[ActionObservation]
    system_actions: list[ActionObservation]
    encounter: EncounterView | None = None
