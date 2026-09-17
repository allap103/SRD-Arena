"""Local GUI spell-draft edits; these are never submitted to the engine."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ChangeTarget:
    """Add or remove a creature from an active staged target selection."""

    target_ref: str
    remove: bool
    expected_decision_id: str
    source_trigger_id: str | None = None


@dataclass(frozen=True)
class SetResourceAllocation:
    """Assign an amount from a shared action resource to one target."""

    target_ref: str
    amount: int
    expected_decision_id: str


@dataclass(frozen=True)
class ConfirmTargeting:
    """Confirm the targets and allocations staged for the current decision."""

    expected_decision_id: str


@dataclass(frozen=True)
class CancelTargeting:
    """Cancel the target selection staged for the current decision."""

    expected_decision_id: str


DraftCommand = ChangeTarget | SetResourceAllocation | ConfirmTargeting | CancelTargeting
