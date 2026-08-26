"""In-process game interface for non-graphical clients."""

from __future__ import annotations

from dataclasses import dataclass, field

from srd_arena.application.commands import (
    CommandResult,
    GameCommand,
    GameUpdate,
    SelectAction,
)
from srd_arena.application.game import RunningGame
from srd_arena.application.observations import ActionObservation, GameObservation
from srd_arena.application.startup import GameStartup


@dataclass(frozen=True)
class ScenarioOption:
    """A scenario exposed to a headless controller by stable ID."""

    id: str
    label: str


@dataclass
class HeadlessGameAdapter:
    """Drive one game without depending on an interactive frontend.

    The adapter deliberately provides observations and legal options without
    choosing among them. A scripted controller or ML policy owns that choice.
    """

    startup: GameStartup
    _game: RunningGame | None = field(default=None, init=False, repr=False)

    def available_scenarios(self) -> tuple[ScenarioOption, ...]:
        """Return selectable scenarios without exposing filesystem paths."""

        return tuple(
            ScenarioOption(id=scenario.id, label=scenario.label)
            for scenario in self.startup.available_scenarios()
        )

    def start_scenario(
        self,
        scenario_id: str,
        *,
        automatic_action_limit: int | None = None,
    ) -> GameObservation:
        """Start a scenario selected by its advertised stable ID."""

        summary = next(
            (
                scenario
                for scenario in self.startup.available_scenarios()
                if scenario.id == scenario_id
            ),
            None,
        )
        if summary is None:
            raise KeyError(f"Unknown scenario '{scenario_id}'.")
        game = self.startup.start_scenario(
            summary.id,
            automatic_action_limit=automatic_action_limit,
        )
        observation = game.observe()
        self._game = game
        return observation

    def observe(self) -> GameObservation:
        """Return the current structured game observation."""

        return self._require_game().observe()

    def available_actions(self) -> tuple[ActionObservation, ...]:
        """Return the legal actions at the current decision point."""

        return tuple(
            action
            for action in self.observe().scene.action_details
            if action.enabled and action.availability == "available"
        )

    def available_action_ids(self) -> tuple[str, ...]:
        """Return stable IDs suitable for an action mask or model choice."""

        return tuple(action.id for action in self.available_actions())

    def select_action(
        self,
        action_id: str,
        *,
        expected_decision_id: str | None,
    ) -> CommandResult:
        """Submit one advertised action against the observed decision."""

        return self.submit(
            SelectAction(
                action_id=action_id,
                expected_decision_id=expected_decision_id,
            )
        )

    def submit(self, command: GameCommand) -> CommandResult:
        """Submit any application command, including staged targeting."""

        return self._require_game().execute(command)

    def advance_automatic(self) -> GameUpdate:
        """Advance scripted controllers until external input is required."""

        return self._require_game().advance_automatic()

    def reset(self) -> GameObservation:
        """Reset the active game to its initial observation."""

        return self._require_game().reset()

    def _require_game(self) -> RunningGame:
        if self._game is None:
            raise RuntimeError("Start a scenario before interacting with the game.")
        return self._game
