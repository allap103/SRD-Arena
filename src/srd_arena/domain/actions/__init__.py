"""Domain actions grouped by rules-facing action type."""

from .eligibility import ActionEligibility, evaluate_action
from .pipeline import ActionExecutionContext, ActionPipeline

__all__ = [
    "ActionEligibility",
    "ActionExecutionContext",
    "ActionPipeline",
    "evaluate_action",
]
