"""In-process game interface for non-graphical clients."""

from __future__ import annotations

from dataclasses import dataclass, field

from srd_arena.application.api import (
    ActionObservation,
    CommandResult,
    GameCommand,
    GameObservation,
    GameStartup,
    GameUpdate,
    RunningGame,
    SelectAction,
)


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
        """Return selectable scenarios without exposing filesystem paths.

        >>> from unittest.mock import Mock
        >>> startup = Mock()
        >>> startup.available_scenarios.return_value = (Mock(id="demo", label="Demo"),)
        >>> HeadlessGameAdapter(startup).available_scenarios()
        (ScenarioOption(id='demo', label='Demo'),)
        """

        return tuple(
            ScenarioOption(id=scenario.id, label=scenario.label)
            for scenario in self.startup.available_scenarios()
        )

    def start_scenario(
        self,
        scenario_id: str,
        *,
        pace_automatic_actions: bool = False,
    ) -> GameObservation:
        """Start a scenario selected by its advertised stable ID.

        >>> from unittest.mock import Mock
        >>> from srd_arena.application.api import SceneObservation
        >>> observation = GameObservation(SceneObservation("intro", None, ()), None, None, False)
        >>> startup, game = Mock(), Mock()
        >>> startup.available_scenarios.return_value = (Mock(id="demo", label="Demo"),)
        >>> startup.start_scenario.return_value = game
        >>> game.observe.return_value = observation
        >>> HeadlessGameAdapter(startup).start_scenario("demo").scene.scene_id
        'intro'
        """

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
            pace_automatic_actions=pace_automatic_actions,
        )
        observation = game.observe()
        self._game = game
        return observation

    def observe(self) -> GameObservation:
        """Return the current structured game observation.

        >>> from unittest.mock import Mock
        >>> from srd_arena.application.api import SceneObservation
        >>> observation = GameObservation(SceneObservation("intro", None, ()), None, None, False)
        >>> startup, game = Mock(), Mock()
        >>> startup.available_scenarios.return_value = (Mock(id="demo", label="Demo"),)
        >>> startup.start_scenario.return_value = game
        >>> game.observe.return_value = observation
        >>> adapter = HeadlessGameAdapter(startup)
        >>> _ = adapter.start_scenario("demo")
        >>> adapter.observe().scene.scene_id
        'intro'
        """

        return self._require_game().observe()

    def available_actions(self) -> tuple[ActionObservation, ...]:
        """Return implemented, eligible actions at the current decision point.

        >>> from unittest.mock import Mock
        >>> from srd_arena.application.api import SceneObservation
        >>> actions = (
        ...     ActionObservation("dodge", "Dodge", "action", "hero"),
        ...     ActionObservation(
        ...         "dash", "Dash", "action", "hero", availability="unavailable"
        ...     ),
        ...     ActionObservation(
        ...         "help", "Help", "action", "hero", enabled=False
        ...     ),
        ... )
        >>> observation = GameObservation(
        ...     SceneObservation("fight", None, actions), None, None, False
        ... )
        >>> startup, game = Mock(), Mock()
        >>> startup.available_scenarios.return_value = (Mock(id="demo", label="Demo"),)
        >>> startup.start_scenario.return_value = game
        >>> game.observe.return_value = observation
        >>> adapter = HeadlessGameAdapter(startup)
        >>> _ = adapter.start_scenario("demo")
        >>> tuple(action.id for action in adapter.available_actions())
        ('dodge',)
        """

        return tuple(
            action
            for action in self.observe().scene.action_details
            if action.enabled and action.availability == "available"
        )

    def available_action_ids(self) -> tuple[str, ...]:
        """Return stable IDs suitable for an action mask or model choice.

        >>> from unittest.mock import Mock
        >>> from srd_arena.application.api import SceneObservation
        >>> action = ActionObservation("dodge", "Dodge", "action", "hero")
        >>> observation = GameObservation(SceneObservation("fight", None, (action,)), None, None, False)
        >>> startup, game = Mock(), Mock()
        >>> startup.available_scenarios.return_value = (Mock(id="demo", label="Demo"),)
        >>> startup.start_scenario.return_value = game
        >>> game.observe.return_value = observation
        >>> adapter = HeadlessGameAdapter(startup)
        >>> _ = adapter.start_scenario("demo")
        >>> adapter.available_action_ids()
        ('dodge',)
        """

        return tuple(action.id for action in self.available_actions())

    def select_action(
        self,
        action_id: str,
        *,
        expected_decision_id: str | None,
    ) -> CommandResult:
        """Submit one advertised action against the observed decision.

        >>> from unittest.mock import Mock
        >>> startup, game = Mock(), Mock()
        >>> startup.available_scenarios.return_value = (Mock(id="demo", label="Demo"),)
        >>> startup.start_scenario.return_value = game
        >>> game.observe.return_value = Mock()
        >>> game.execute.return_value = CommandResult(update=Mock())
        >>> adapter = HeadlessGameAdapter(startup)
        >>> _ = adapter.start_scenario("demo")
        >>> adapter.select_action("dodge", expected_decision_id="turn:1").accepted
        True
        >>> command = game.execute.call_args.args[0]
        >>> (command.action_id, command.expected_decision_id)
        ('dodge', 'turn:1')
        """

        return self.submit(
            SelectAction(
                action_id=action_id,
                expected_decision_id=expected_decision_id,
            )
        )

    def submit(self, command: GameCommand) -> CommandResult:
        """Submit any application command, including staged targeting.

        >>> from unittest.mock import Mock
        >>> startup, game = Mock(), Mock()
        >>> startup.available_scenarios.return_value = (Mock(id="demo", label="Demo"),)
        >>> startup.start_scenario.return_value = game
        >>> game.observe.return_value = Mock()
        >>> expected = CommandResult()
        >>> game.execute.return_value = expected
        >>> adapter = HeadlessGameAdapter(startup)
        >>> _ = adapter.start_scenario("demo")
        >>> adapter.submit(SelectAction("dodge", "turn:1")) is expected
        True
        """

        return self._require_game().execute(command)

    def advance_automatic(self) -> GameUpdate:
        """Advance scripted controllers until external input is required.

        >>> from unittest.mock import Mock
        >>> startup, game = Mock(), Mock()
        >>> startup.available_scenarios.return_value = (Mock(id="demo", label="Demo"),)
        >>> startup.start_scenario.return_value = game
        >>> game.observe.return_value = Mock()
        >>> update = Mock()
        >>> game.advance_automatic.return_value = update
        >>> adapter = HeadlessGameAdapter(startup)
        >>> _ = adapter.start_scenario("demo")
        >>> adapter.advance_automatic() is update
        True
        """

        return self._require_game().advance_automatic()

    def reset(self) -> GameObservation:
        """Reset the active game to its initial observation.

        >>> from unittest.mock import Mock
        >>> from srd_arena.application.api import SceneObservation
        >>> initial = GameObservation(
        ...     SceneObservation("intro", "Ready?", ()), None, None, False
        ... )
        >>> startup, game = Mock(), Mock()
        >>> startup.available_scenarios.return_value = (Mock(id="demo", label="Demo"),)
        >>> startup.start_scenario.return_value = game
        >>> game.observe.return_value = Mock()
        >>> game.reset.return_value = initial
        >>> adapter = HeadlessGameAdapter(startup)
        >>> _ = adapter.start_scenario("demo")
        >>> adapter.reset().scene.scene_text
        'Ready?'
        """

        return self._require_game().reset()

    def _require_game(self) -> RunningGame:
        if self._game is None:
            raise RuntimeError("Start a scenario before interacting with the game.")
        return self._game
