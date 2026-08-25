"""Stable internal facade for the Opportunity Attack lifecycle."""

from .movement_continuation import resume_movement
from .opportunity_execution import (
    apply_reaction_action,
    opportunity_attack_request,
    resolve_automatic_opportunity_attacks,
)
from .opportunity_offers import queue_opportunity_attack, reaction_actions

__all__ = [
    "apply_reaction_action",
    "opportunity_attack_request",
    "queue_opportunity_attack",
    "reaction_actions",
    "resolve_automatic_opportunity_attacks",
    "resume_movement",
]
