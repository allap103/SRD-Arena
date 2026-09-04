"""Typed, source-aware questions asked by encounter orchestration."""

from .compulsions import active_compelled_turn, compelled_turns
from .damage_riders import attack_hit_damage
from .defenses import (
    apply_damage,
    condition_immunities,
    condition_suppressions,
    damage_immunities,
    damage_resistances,
    damage_vulnerabilities,
    has_condition_save_advantage,
    reset_damage_reductions,
    resolve_damage_reduction,
)
from .health import apply_healing, effective_maximum_health
from .invocations import (
    invocation_prohibitions,
    invocation_start_checks,
    resolve_invocation_start,
)
from .models import (
    InvocationFailureChanceContribution,
    InvocationStartContext,
    InvocationStartQueryResult,
    InvocationStartResult,
    InvocationStartRoll,
    MovementQueryResult,
    NumericOperation,
    NumericRuleContribution,
    NumericRuleResult,
    RollRuleContribution,
    RollRuleResult,
    SenseRuleResult,
    SetRuleResult,
    SourcedEligibilityFailure,
    SourcedRuleContribution,
)
from .movement import movement_step_cost, stand_up_movement_cost
from .numeric import (
    attack_limit,
    effective_armor_class,
    effective_speed,
    movement_budget,
)
from .obstructions import (
    CoverResult,
    cell_has_line_of_effect,
    cells_with_line_of_effect,
    cover_between,
    cover_from_position,
    creature_has_line_of_effect_to_cell,
    grid_ray_cells,
)
from .permissions import (
    TargetingKind,
    action_compatibility,
    reaction_eligibility,
    target_eligibility,
)
from .rolls import roll_modifiers
from .senses import sense_range
from .visibility import creature_can_see_cell, creature_can_see_creature

__all__ = [
    "CoverResult",
    "InvocationFailureChanceContribution",
    "InvocationStartContext",
    "InvocationStartQueryResult",
    "InvocationStartResult",
    "InvocationStartRoll",
    "MovementQueryResult",
    "NumericOperation",
    "NumericRuleContribution",
    "NumericRuleResult",
    "RollRuleContribution",
    "RollRuleResult",
    "SenseRuleResult",
    "SetRuleResult",
    "SourcedEligibilityFailure",
    "SourcedRuleContribution",
    "TargetingKind",
    "action_compatibility",
    "active_compelled_turn",
    "apply_damage",
    "apply_healing",
    "attack_hit_damage",
    "attack_limit",
    "cell_has_line_of_effect",
    "cells_with_line_of_effect",
    "compelled_turns",
    "condition_immunities",
    "condition_suppressions",
    "cover_between",
    "cover_from_position",
    "creature_can_see_cell",
    "creature_can_see_creature",
    "creature_has_line_of_effect_to_cell",
    "damage_immunities",
    "damage_resistances",
    "damage_vulnerabilities",
    "effective_armor_class",
    "effective_maximum_health",
    "effective_speed",
    "grid_ray_cells",
    "has_condition_save_advantage",
    "invocation_prohibitions",
    "invocation_start_checks",
    "movement_budget",
    "movement_step_cost",
    "reaction_eligibility",
    "reset_damage_reductions",
    "resolve_damage_reduction",
    "resolve_invocation_start",
    "roll_modifiers",
    "sense_range",
    "stand_up_movement_cost",
    "target_eligibility",
]
