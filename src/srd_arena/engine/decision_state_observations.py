"""Detached resource and turn-state collections subject to field disclosure."""

from dataclasses import dataclass

from .observation_models import ResourcePoolObservation, SpellSlotObservation


@dataclass(frozen=True)
class MovementBudgetObservation:
    """Remaining and total movement in feet, not grid cells."""

    remaining_feet: int
    total_feet: int


@dataclass(frozen=True)
class ActionEconomyObservation:
    """Current turn budgets, including the per-caster spell-slot restriction."""

    actions_remaining: int
    bonus_action_available: bool
    reaction_available: bool
    attacks_remaining: int
    attacks_per_attack_action: int
    spell_slot_spent_this_turn: bool


@dataclass(frozen=True)
class ResourceObservation:
    """Exact authorized pools; empty tuples mean known absence, not hidden."""

    spell_slots: tuple[SpellSlotObservation, ...]
    class_resources: tuple[ResourcePoolObservation, ...]
