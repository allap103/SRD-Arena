from __future__ import annotations

from dataclasses import dataclass

from ..domain.creatures import Creature
from ..domain.encounters.encounter import EncounterState
from ..domain.encounters.models import EncounterAction
from ..frontends.shared.models import SceneView, TurnResult
from .scenario import LoadedScenario
from .session import PendingSceneTransition, Session


@dataclass
class Game:
    """Application-level entrypoint for one running game."""

    scenario: LoadedScenario
    session: Session

    @classmethod
    def start(
        cls,
        scenario: LoadedScenario,
        *,
        control_mode: str | None = None,
    ) -> Game:
        game = cls(
            scenario=scenario,
            session=scenario.create_session(
                control_mode=control_mode,
            ),
        )
        game.session.start_encounter()
        return game

    @property
    def player(self) -> Creature:
        return self.session.player

    @property
    def encounter_state(self) -> EncounterState | None:
        return self.session.encounter_state

    @property
    def pending_scene_transition(self) -> PendingSceneTransition | None:
        return self.session.pending_scene_transition

    @property
    def current_scene_id(self) -> str:
        return self.session.current_scene_id

    @property
    def automatic_action_limit(self) -> int | None:
        return self.session.automatic_action_limit

    @automatic_action_limit.setter
    def automatic_action_limit(self, value: int | None) -> None:
        self.session.automatic_action_limit = value

    def view(self) -> SceneView:
        return self.session.get_scene_view()

    def choose(self, choice_index: int) -> TurnResult:
        return self.session.choose(choice_index)

    def perform(self, action: EncounterAction) -> TurnResult:
        return self.session.choose_encounter_action(action)

    def advance_until_input_required(self) -> TurnResult:
        return self.session.advance_until_input_required()

    def reset(self) -> None:
        self.session.reset()
        self.session.start_encounter()
