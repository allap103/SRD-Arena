"""Encounter state aggregate and its small public facade.

Turn flow lives in orchestration and turn_lifecycle. This class owns state
construction and derived convenience properties. Focused encounter modules
are called directly instead of being dynamically rebound onto the aggregate.
"""

from __future__ import annotations

from copy import deepcopy

from ..creatures import Creature
from ..effects.condition_rules import EffectiveConditionSet
from ..effects.conditions import AppliedCondition, Condition
from ..equipment import Item
from ..geometry import GeometryConfig, MovementBudget, Position
from ..rolls.dice import roll_dice as _roll_dice
from ..rolls.dice import roll_die as _roll_die
from .actions.eligibility import ActionEligibility
from .actions.options import (
    available_actions as _available_actions_impl,
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
)
from .encounter_models.resolution import CombatEvent
from .encounter_models.state import (
    EncounterCreatureState,
    EncounterStateData,
    RoundState,
    TurnState,
)
from .reactions import REACTION_ENGINE, ReactionEngine
from .rules import COMBAT_RULES, CombatRules
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

    Aggregate data lives in ``EncounterStateData`` while focused modules own
    turn flow, reactions, and rule queries. This facade retains only the small
    public API consumed by the engine.
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

    @property
    def pending_movement(self) -> PendingMovement | None:
        """Return movement suspended by the newest opportunity-attack decision.

        >>> from srd_arena.domain.geometry import Grid, MovementCost
        >>> from srd_arena.domain.encounters.encounter_models.decisions import DecisionFrame
        >>> state = EncounterState("demo", EncounterDefinition("demo", Grid(5, 5)), {})
        >>> movement = PendingMovement("move", "hero", "right", Position(0, 0),
        ...     Position(1, 0), MovementBudget(5), MovementCost(1), "trigger")
        >>> state.interrupts.decision_stack = [DecisionFrame("reaction", "enemy", "reaction", "opportunity",
        ...     request=OpportunityAttackRequest(movement))]
        >>> state.pending_movement is movement
        True
        """
        for decision in reversed(self.interrupts.decision_stack):
            if isinstance(decision.request, OpportunityAttackRequest):
                return decision.request.movement
        return None

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
        state.roll_initiative()
        _initialize_action_selectors_impl(state)
        return state

    def roll_initiative(self) -> None:
        """Roll and order the encounter participants before the first turn."""

        # Resolve the module-level name at call time so tests and simulations can
        # replace encounter.roll_die deterministically.
        _roll_initiative_impl(self, roll_die)

    def current_turn_label(self) -> str:
        """Return the label of the creature whose turn or reaction is active."""

        return _current_turn_label_impl(self)

    def current_decision(self) -> DecisionFrame:
        """Return the unresolved decision at the top of the encounter stack."""

        return _current_decision_impl(self)

    def conditions_for(
        self,
        creature_ref: CreatureRef,
    ) -> tuple[AppliedCondition, ...]:
        """Return stored condition applications for one creature."""

        return _conditions_for_impl(self, creature_ref)

    def has_condition(
        self,
        creature_ref: CreatureRef,
        condition: Condition,
    ) -> bool:
        """Return whether a condition currently affects one creature."""

        return _has_condition_impl(self, creature_ref, condition)

    def effective_conditions_for(
        self,
        creature_ref: CreatureRef,
    ) -> EffectiveConditionSet:
        """Return the effective condition set for one creature."""

        return _effective_conditions_for_impl(self, creature_ref)

    def active_creature(self) -> CreatureRef:
        """Return the creature that owns the current decision."""

        return _active_creature_impl(self)

    def requires_automatic_advance(self) -> bool:
        """Return whether the current controller should act automatically."""

        return _requires_automatic_advance_impl(self)

    def action_eligibility(self, action: EncounterAction) -> ActionEligibility:
        """Evaluate an action against the current encounter decision."""

        return _action_eligibility_impl(self, action)

    def available_actions(self) -> list[EncounterAction]:
        """Return actions advertised for the current external decision."""

        return _available_actions_impl(self)
