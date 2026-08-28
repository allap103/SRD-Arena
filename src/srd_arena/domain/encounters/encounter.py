"""Encounter state facade and its stable service bindings.

Turn flow lives in orchestration and turn_lifecycle. This class owns state
construction, compatibility views over structured state containers, and the
explicit bindings to focused encounter services.
"""

from __future__ import annotations

from copy import deepcopy

from ..creatures import Creature
from ..equipment import Item
from ..geometry import GeometryConfig, MovementBudget, Position
from ..rolls.dice import roll_dice as _roll_dice
from ..rolls.dice import roll_die as _roll_die
from .actions.execution import resolve_grapple_action as _resolve_grapple_action_impl
from .actions.features import resolve_feature_action as _resolve_feature_action_impl
from .actions.items import resolve_utilize_action as _resolve_utilize_action_impl
from .actions.options import (
    available_actions as _available_actions_impl,
)
from .actions.options import (
    available_feature_actions as _available_feature_actions_impl,
)
from .actions.options import (
    available_spell_actions as _available_spell_actions_impl,
)
from .actions.options import (
    feature_action_available as _feature_action_available_impl,
)
from .actions.options import (
    spell_action_cost as _spell_action_cost_impl,
)
from .actions.options import (
    spell_action_targets as _spell_action_targets_impl,
)
from .actions.options import (
    spell_area as _spell_area_impl,
)
from .actions.options import (
    spell_area_targets as _spell_area_targets_impl,
)
from .actions.options import (
    spell_cast_block_reason_for as _spell_cast_block_reason_impl,
)
from .actions.options import (
    spell_range_squares_for as _spell_range_squares_impl,
)
from .actions.options import (
    spell_target_context as _spell_target_context_impl,
)
from .actions.options import (
    spell_targets_self_only_for as _spell_targets_self_only_impl,
)
from .actions.options import (
    spend_spell_resources as _spend_spell_resources_impl,
)
from .actions.options import (
    targets_in_area as _targets_in_area_impl,
)
from .actions.spellcasting import resolve_spell_action as _resolve_spell_action_impl
from .conditions import (
    apply_condition as _apply_condition_impl,
)
from .conditions import (
    apply_grapple as _apply_grapple_impl,
)
from .conditions import (
    condition_replaces as _condition_replaces_impl,
)
from .conditions import (
    condition_sources_for as _condition_sources_for_impl,
)
from .conditions import (
    grappled_sources_for as _grappled_sources_for_impl,
)
from .conditions import (
    grappling_targets_for as _grappling_targets_for_impl,
)
from .conditions import (
    is_grappled as _is_grappled_impl,
)
from .conditions import (
    movement_cost_for as _movement_cost_for_impl,
)
from .conditions import (
    remove_condition as _remove_condition_impl,
)
from .conditions import (
    remove_condition_from_source as _remove_condition_from_source_impl,
)
from .conditions import (
    remove_relationships_for_creature as _remove_relationships_for_creature_impl,
)
from .creature_control import (
    available_creature_actions as _available_creature_actions_impl,
)
from .creature_control import (
    creature_action_candidates as _creature_action_candidates_impl,
)
from .creature_control import (
    execute_creature_action as _execute_creature_action_impl,
)
from .definitions import EncounterBehavior, EncounterDefinition
from .encounter_models.actions import (
    ActionCost,
    CreatureRef,
    EncounterAction,
)
from .encounter_models.decisions import (
    DecisionFrame,
    InterruptState,
    OpportunityAttackRequest,
    PendingMovement,
    PendingSpellCast,
)
from .encounter_models.resolution import CombatEvent
from .encounter_models.state import (
    EncounterCreatureState,
    EncounterStateData,
    RoundState,
    TurnState,
)
from .ongoing_effects import start_ongoing_effect as _start_ongoing_effect_impl
from .participants import (
    creature_controller as _creature_controller_impl,
)
from .participants import (
    creature_for_ref as _creature_for_ref_impl,
)
from .participants import (
    creature_team_id as _creature_team_id_impl,
)
from .participants import (
    creatures_are_opponents as _creatures_are_opponents_impl,
)
from .reactions import REACTION_ENGINE, ReactionEngine
from .rules import COMBAT_RULES, CombatRules
from .state_combat import (
    active_status_effects as _active_status_effects_impl,
)
from .state_combat import (
    attack_roll_mode_for as _attack_roll_mode_for_impl,
)
from .state_combat import (
    automatic_critical_provider_ids_for as _automatic_critical_provider_ids_for_impl,
)
from .state_combat import (
    automatic_save_failure_provider_ids_for,
)
from .state_initialization import (
    initialize_action_selectors as _initialize_action_selectors_impl,
)
from .state_initialization import (
    roll_initiative as _roll_initiative_impl,
)
from .state_queries import (
    action_eligibility as _action_eligibility_impl,
)
from .state_queries import (
    active_creature as _active_creature_impl,
)
from .state_queries import (
    conditions_for as _conditions_for_impl,
)
from .state_queries import (
    current_decision as _current_decision_impl,
)
from .state_queries import (
    current_turn_label as _current_turn_label_impl,
)
from .state_queries import (
    effective_conditions_for as _effective_conditions_for_impl,
)
from .state_queries import (
    has_condition as _has_condition_impl,
)
from .state_queries import (
    requires_automatic_advance as _requires_automatic_advance_impl,
)
from .state_runtime import (
    apply_encounter_effects as _apply_effects_impl,
)
from .state_runtime import (
    consume_action as _consume_action_impl,
)
from .state_runtime import (
    create_event as _event_impl,
)
from .state_runtime import (
    creature_label as _creature_label_impl,
)
from .state_runtime import (
    creature_position as _creature_position_impl,
)
from .state_runtime import (
    creature_size as _creature_size_impl,
)
from .state_runtime import (
    living_creature_refs as _living_creature_refs_impl,
)
from .state_runtime import (
    merge_progress as _merge_progress_impl,
)
from .state_runtime import (
    next_action_id as _next_action_id_impl,
)
from .state_runtime import (
    next_frame_id as _next_frame_id_impl,
)
from .state_runtime import (
    next_runtime_origin_id as _next_runtime_origin_id_impl,
)
from .state_runtime import (
    position_is_free as _position_is_free_impl,
)
from .turn_lifecycle import TURN_LIFECYCLE, TurnLifecycle

# Keep these module-level names for tests and helpers that monkeypatch
# `srd_arena.domain.encounters.encounter.roll_die` / `roll_dice`.
roll_die = _roll_die
roll_dice = _roll_dice
__all__ = [
    "ActionCost",
    "CombatEvent",
    "EncounterAction",
    "EncounterState",
    "roll_dice",
    "roll_die",
]


class EncounterState(EncounterStateData):
    """Own one running encounter and expose its stable orchestration facade.

    Aggregate data lives in ``EncounterStateData`` while focused services own
    turn flow, reactions, and rule queries. This facade binds those services to
    the state instance and retains the public API consumed by the engine.
    """

    # Engines are stateless rule/orchestration collaborators.
    @property
    def reaction_engine(self) -> ReactionEngine:
        """Return the stateless reaction-orchestration service.

        >>> from srd_arena.domain.geometry import Grid
        >>> state = EncounterState("demo", EncounterDefinition("demo", Grid(5, 5)), {})
        >>> isinstance(state.reaction_engine, ReactionEngine)
        True
        """
        return REACTION_ENGINE

    @property
    def turn_lifecycle(self) -> TurnLifecycle:
        """Return the stateless turn-lifecycle service.

        >>> from srd_arena.domain.geometry import Grid
        >>> state = EncounterState("demo", EncounterDefinition("demo", Grid(5, 5)), {})
        >>> isinstance(state.turn_lifecycle, TurnLifecycle)
        True
        """
        return TURN_LIFECYCLE

    @property
    def combat_rules(self) -> CombatRules:
        """Return the stateless combat-rule query service.

        >>> from srd_arena.domain.geometry import Grid
        >>> state = EncounterState("demo", EncounterDefinition("demo", Grid(5, 5)), {})
        >>> isinstance(state.combat_rules, CombatRules)
        True
        """
        return COMBAT_RULES

    # Compatibility views expose structured interrupt, round, turn, and
    # active-creature state through the established EncounterState API.
    @property
    def decision_stack(self) -> list[DecisionFrame]:
        """Expose the interrupt state's nested decision frames.

        >>> from srd_arena.domain.geometry import Grid
        >>> state = EncounterState("demo", EncounterDefinition("demo", Grid(5, 5)), {})
        >>> frame = DecisionFrame("reaction-1", "hero", "reaction", "counterspell")
        >>> state.decision_stack = [frame]
        >>> state.decision_stack[-1].reason
        'counterspell'
        """
        return self.interrupts.decision_stack

    @decision_stack.setter
    def decision_stack(self, value: list[DecisionFrame]) -> None:
        self.interrupts.decision_stack = value

    @property
    def pending_movement(self) -> PendingMovement | None:
        """Return movement suspended by the newest opportunity-attack decision.

        >>> from srd_arena.domain.geometry import Grid, MovementCost
        >>> state = EncounterState("demo", EncounterDefinition("demo", Grid(5, 5)), {})
        >>> movement = PendingMovement("move", "hero", "right", Position(0, 0),
        ...     Position(1, 0), MovementBudget(5), MovementCost(1), "trigger")
        >>> state.decision_stack = [DecisionFrame("reaction", "enemy", "reaction", "opportunity",
        ...     request=OpportunityAttackRequest(movement))]
        >>> state.pending_movement is movement
        True
        """
        for decision in reversed(self.decision_stack):
            if isinstance(decision.request, OpportunityAttackRequest):
                return decision.request.movement
        return None

    @property
    def pending_spell_cast(self) -> PendingSpellCast | None:
        """Expose spell targeting staged before invocation begins.

        >>> from srd_arena.domain.geometry import Grid
        >>> state = EncounterState("demo", EncounterDefinition("demo", Grid(5, 5)), {})
        >>> pending = PendingSpellCast(EncounterAction("Cast", "spell"), "fireball", [], 1)
        >>> state.pending_spell_cast = pending
        >>> state.pending_spell_cast.spell_id if state.pending_spell_cast else None
        'fireball'
        """
        return self.interrupts.pending_spell_cast

    @pending_spell_cast.setter
    def pending_spell_cast(self, value: PendingSpellCast | None) -> None:
        self.interrupts.pending_spell_cast = value

    @property
    def turn_index(self) -> int:
        """Expose the current index within initiative order.

        >>> from srd_arena.domain.geometry import Grid
        >>> state = EncounterState("demo", EncounterDefinition("demo", Grid(5, 5)), {})
        >>> state.turn_index = 2
        >>> state.turn_index
        2
        """
        return self.turn.index

    @turn_index.setter
    def turn_index(self, value: int) -> None:
        self.turn.index = value

    @property
    def round_number(self) -> int:
        """Expose the current one-based encounter round.

        >>> from srd_arena.domain.geometry import Grid
        >>> state = EncounterState("demo", EncounterDefinition("demo", Grid(5, 5)), {})
        >>> state.round_number = 3
        >>> state.round_number
        3
        """
        return self.round.number

    @round_number.setter
    def round_number(self, value: int) -> None:
        self.round.number = value

    @property
    def active_creature_state(self) -> EncounterCreatureState:
        """Return state for the creature owning the current decision.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.geometry import Grid
        >>> active = Mock()
        >>> state = EncounterState("demo", EncounterDefinition("demo", Grid(5, 5)),
        ...     {"hero": active}, initiative_order=["hero"])
        >>> state.active_creature_state is active
        True
        """
        return self.creatures[self.current_decision().creature_ref]

    @property
    def active_position(self) -> Position:
        """Return the current decision owner's grid position.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.geometry import Grid
        >>> active = Mock(position=Position(2, 3))
        >>> state = EncounterState("demo", EncounterDefinition("demo", Grid(5, 5)),
        ...     {"hero": active}, initiative_order=["hero"])
        >>> state.active_position
        Position(x=2, y=3)
        """
        return self.active_creature_state.position

    @property
    def active_movement_remaining(self) -> MovementBudget | None:
        """Expose the current decision owner's remaining movement budget.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.geometry import Grid
        >>> active = Mock(movement_remaining=MovementBudget(4))
        >>> state = EncounterState("demo", EncounterDefinition("demo", Grid(5, 5)),
        ...     {"hero": active}, initiative_order=["hero"])
        >>> state.active_movement_remaining = 3
        >>> state.active_movement_remaining
        3
        """
        return self.active_creature_state.movement_remaining

    @active_movement_remaining.setter
    def active_movement_remaining(self, value: int | None) -> None:
        self.active_creature_state.movement_remaining = (
            MovementBudget(value) if value is not None else None
        )

    @property
    def active_action_available(self) -> bool:
        """Return whether the active creature retains at least one action.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.geometry import Grid
        >>> active = Mock(actions_remaining=1, action_used_this_turn=False)
        >>> state = EncounterState("demo", EncounterDefinition("demo", Grid(5, 5)),
        ...     {"hero": active}, initiative_order=["hero"])
        >>> state.active_action_available
        True
        >>> state.active_action_available = False
        >>> state.active_actions_remaining
        0
        """
        return self.active_creature_state.actions_remaining > 0

    @active_action_available.setter
    def active_action_available(self, value: bool) -> None:
        if value:
            self.active_creature_state.actions_remaining = max(
                1,
                self.active_creature_state.actions_remaining,
            )
        else:
            if self.active_creature_state.actions_remaining > 0:
                self.active_creature_state.action_used_this_turn = True
            self.active_creature_state.actions_remaining = 0

    @property
    def active_actions_remaining(self) -> int:
        """Expose the active creature's remaining ordinary actions.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.geometry import Grid
        >>> active = Mock(actions_remaining=2, action_used_this_turn=False)
        >>> state = EncounterState("demo", EncounterDefinition("demo", Grid(5, 5)),
        ...     {"hero": active}, initiative_order=["hero"])
        >>> state.active_actions_remaining = 1
        >>> (state.active_actions_remaining, active.action_used_this_turn)
        (1, True)
        """
        return self.active_creature_state.actions_remaining

    @active_actions_remaining.setter
    def active_actions_remaining(self, value: int) -> None:
        if value < self.active_creature_state.actions_remaining:
            self.active_creature_state.action_used_this_turn = True
        self.active_creature_state.actions_remaining = max(0, value)

    @property
    def active_magic_actions_remaining(self) -> int:
        """Expose the active creature's remaining Magic actions.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.geometry import Grid
        >>> active = Mock(magic_actions_remaining=1)
        >>> state = EncounterState("demo", EncounterDefinition("demo", Grid(5, 5)),
        ...     {"hero": active}, initiative_order=["hero"])
        >>> state.active_magic_actions_remaining = -1
        >>> state.active_magic_actions_remaining
        0
        """
        return self.active_creature_state.magic_actions_remaining

    @active_magic_actions_remaining.setter
    def active_magic_actions_remaining(self, value: int) -> None:
        self.active_creature_state.magic_actions_remaining = max(0, value)

    @property
    def active_attacks_remaining(self) -> int:
        """Expose attacks remaining within the active Attack action.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.geometry import Grid
        >>> active = Mock(attacks_remaining=2)
        >>> state = EncounterState("demo", EncounterDefinition("demo", Grid(5, 5)),
        ...     {"hero": active}, initiative_order=["hero"])
        >>> state.active_attacks_remaining = 1
        >>> state.active_attacks_remaining
        1
        """
        return self.active_creature_state.attacks_remaining

    @active_attacks_remaining.setter
    def active_attacks_remaining(self, value: int) -> None:
        self.active_creature_state.attacks_remaining = value

    @property
    def active_bonus_action_available(self) -> bool:
        """Expose whether the active creature retains its Bonus Action.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.geometry import Grid
        >>> active = Mock(bonus_action_available=True, bonus_action_used_this_turn=False)
        >>> state = EncounterState("demo", EncounterDefinition("demo", Grid(5, 5)),
        ...     {"hero": active}, initiative_order=["hero"])
        >>> state.active_bonus_action_available = False
        >>> (state.active_bonus_action_available, active.bonus_action_used_this_turn)
        (False, True)
        """
        return self.active_creature_state.bonus_action_available

    @active_bonus_action_available.setter
    def active_bonus_action_available(self, value: bool) -> None:
        if self.active_creature_state.bonus_action_available and not value:
            self.active_creature_state.bonus_action_used_this_turn = True
        self.active_creature_state.bonus_action_available = value

    @property
    def active_reaction_available(self) -> bool:
        """Expose whether the active creature retains its Reaction.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.geometry import Grid
        >>> active = Mock(reaction_available=True)
        >>> state = EncounterState("demo", EncounterDefinition("demo", Grid(5, 5)),
        ...     {"hero": active}, initiative_order=["hero"])
        >>> state.active_reaction_available = False
        >>> state.active_reaction_available
        False
        """
        return self.active_creature_state.reaction_available

    @active_reaction_available.setter
    def active_reaction_available(self, value: bool) -> None:
        self.active_creature_state.reaction_available = value

    @classmethod
    def from_definition(
        cls,
        encounter_id: str,
        definition: EncounterDefinition,
        creature_templates: dict[str, Creature],
        item_templates: dict[str, Item] | None = None,
        geometry_config: GeometryConfig | None = None,
    ) -> EncounterState:
        """Create isolated runtime state from an authored encounter definition.

        Creature templates are copied so an encounter cannot mutate loaded content.

        >>> from srd_arena.domain.creatures import Attributes, Equipment, Inventory
        >>> from srd_arena.domain.encounters.definitions import EncounterParticipant
        >>> from srd_arena.domain.geometry import Grid
        >>> hero = Creature("hero", "Hero", "", Inventory(),
        ...     Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> definition = EncounterDefinition("demo", Grid(5, 5),
        ...     participants=[EncounterParticipant("hero", Position(1, 2), "external")])
        >>> state = EncounterState.from_definition("demo", definition, {"hero": hero})
        >>> (state.creatures["hero"].position, state.creatures["hero"].creature is hero)
        (Position(x=1, y=2), False)
        """
        creatures: dict[CreatureRef, EncounterCreatureState] = {}
        for participant in definition.participants:
            creature = creature_templates[participant.creature_id]
            creatures[participant.creature_id] = EncounterCreatureState(
                creature_id=participant.creature_id,
                creature=deepcopy(creature),
                position=Position(participant.start.x, participant.start.y),
                behavior=deepcopy(
                    participant.behavior or EncounterBehavior(type="wait")
                ),
            )
        state = cls(
            encounter_id=encounter_id,
            definition=definition,
            creatures=creatures,
            round=RoundState(),
            turn=TurnState(),
            interrupts=InterruptState(),
            item_templates=item_templates or {},
            geometry_config=geometry_config or GeometryConfig(),
        )
        state._roll_initiative()
        state._initialize_action_selectors()
        return state

    _initialize_action_selectors = _initialize_action_selectors_impl

    def _roll_initiative(self) -> None:
        # Resolve the module-level name at call time so tests and simulations can
        # still replace encounter.roll_die deterministically.
        _roll_initiative_impl(self, roll_die)

    # Read-only state and combat queries.
    current_turn_label = _current_turn_label_impl
    current_decision = _current_decision_impl
    conditions_for = _conditions_for_impl
    has_condition = _has_condition_impl
    effective_conditions_for = _effective_conditions_for_impl
    _attack_roll_mode_for = _attack_roll_mode_for_impl
    _automatic_critical_provider_ids_for = _automatic_critical_provider_ids_for_impl
    _automatic_save_failure_provider_ids_for = automatic_save_failure_provider_ids_for
    _active_status_effects = _active_status_effects_impl
    active_creature = _active_creature_impl
    requires_automatic_advance = _requires_automatic_advance_impl
    action_eligibility = _action_eligibility_impl

    # Action discovery and action execution entry points.
    available_actions = _available_actions_impl
    _available_feature_actions = _available_feature_actions_impl
    _available_spell_actions = _available_spell_actions_impl
    _feature_action_available = _feature_action_available_impl
    _spell_action_cost = _spell_action_cost_impl
    _spell_cast_block_reason = _spell_cast_block_reason_impl
    _spell_targets_self_only = _spell_targets_self_only_impl
    _spell_range_squares = _spell_range_squares_impl
    _spell_action_targets = _spell_action_targets_impl
    _spell_area_targets = _spell_area_targets_impl
    _spend_spell_resources = _spend_spell_resources_impl
    _spell_area = _spell_area_impl
    _targets_in_area = _targets_in_area_impl
    _available_creature_actions = _available_creature_actions_impl
    _creature_action_candidates = _creature_action_candidates_impl
    _execute_creature_action = _execute_creature_action_impl
    _resolve_utilize_action = _resolve_utilize_action_impl
    _resolve_feature_action = _resolve_feature_action_impl
    _resolve_spell_action = _resolve_spell_action_impl
    _resolve_grapple_action = _resolve_grapple_action_impl

    _spell_target_context = _spell_target_context_impl

    # Effect, condition, participant, and runtime-state services.
    _apply_effects = _apply_effects_impl

    _apply_condition = _apply_condition_impl
    _start_ongoing_effect = _start_ongoing_effect_impl
    _apply_grapple = _apply_grapple_impl
    _remove_condition = _remove_condition_impl
    _remove_condition_from_source = _remove_condition_from_source_impl
    _remove_relationships_for_creature = _remove_relationships_for_creature_impl
    _creature_controller = _creature_controller_impl
    _creature_team_id = _creature_team_id_impl
    _creatures_are_opponents = _creatures_are_opponents_impl

    _consume_action = _consume_action_impl
    _next_action_id = _next_action_id_impl
    _next_runtime_origin_id = _next_runtime_origin_id_impl
    _next_frame_id = _next_frame_id_impl
    _event = _event_impl
    _merge_progress = _merge_progress_impl
    _creature_label = _creature_label_impl
    _living_creature_refs = _living_creature_refs_impl
    _creature_position = _creature_position_impl
    _position_is_free = _position_is_free_impl
    _creature_size = _creature_size_impl

    _condition_sources_for = _condition_sources_for_impl
    _grappled_sources_for = _grappled_sources_for_impl
    _grappling_targets_for = _grappling_targets_for_impl
    _is_grappled = _is_grappled_impl
    _movement_cost_for = _movement_cost_for_impl
    _creature_for_ref = _creature_for_ref_impl
    _condition_replaces = staticmethod(_condition_replaces_impl)
