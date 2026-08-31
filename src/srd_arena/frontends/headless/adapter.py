"""In-process game interface for non-graphical clients."""

from __future__ import annotations

from dataclasses import dataclass, field

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.engine.api import (
    ActionObservation,
    CommandResult,
    GameCommand,
    GameObservation,
    GameUpdate,
    SelectAction,
    Session,
)


@dataclass(frozen=True)
class EncounterOption:
    """An encounter exposed to a headless controller by stable ID."""

    id: str
    label: str


@dataclass
class HeadlessGameAdapter:
    """Drive one game without depending on an interactive frontend.

    The adapter deliberately provides observations and legal options without
    choosing among them. A scripted controller or ML policy owns that choice.
    """

    catalog: EncounterCatalog
    _session: Session | None = field(default=None, init=False, repr=False)

    def available_encounters(self) -> tuple[EncounterOption, ...]:
        """Return selectable encounters without exposing filesystem paths.

        >>> from unittest.mock import Mock
        >>> catalog = Mock()
        >>> catalog.available_encounters.return_value = (Mock(id="demo", label="Demo"),)
        >>> HeadlessGameAdapter(catalog).available_encounters()
        (EncounterOption(id='demo', label='Demo'),)
        """

        return tuple(
            EncounterOption(id=encounter.id, label=encounter.label)
            for encounter in self.catalog.available_encounters()
        )

    def start_encounter(self, encounter_id: str) -> GameObservation:
        """Start an encounter selected by its advertised stable ID.

        >>> from unittest.mock import Mock
        >>> from srd_arena.engine.api import SceneObservation
        >>> observation = GameObservation(SceneObservation("intro", None, ()), None, None, False)
        >>> catalog, session = Mock(), Mock()
        >>> catalog.available_encounters.return_value = (Mock(id="demo", label="Demo"),)
        >>> catalog.load_encounter.return_value = Mock()
        >>> session = Mock()
        >>> session.observe.return_value = observation
        >>> from unittest.mock import patch
        >>> with patch("srd_arena.frontends.headless.adapter.Session", return_value=session):
        ...     result = HeadlessGameAdapter(catalog).start_encounter("demo")
        >>> result.scene.scene_id
        'intro'
        """

        summary = next(
            (
                encounter
                for encounter in self.catalog.available_encounters()
                if encounter.id == encounter_id
            ),
            None,
        )
        if summary is None:
            raise KeyError(f"Unknown encounter '{encounter_id}'.")
        session = Session(self.catalog.load_encounter(summary.id))
        observation = session.observe()
        self._session = session
        return observation

    def observe(self) -> GameObservation:
        """Return the current structured game observation.

        >>> from unittest.mock import Mock
        >>> from srd_arena.engine.api import SceneObservation
        >>> observation = GameObservation(SceneObservation("intro", None, ()), None, None, False)
        >>> session = Mock()
        >>> session.observe.return_value = observation
        >>> adapter = HeadlessGameAdapter(Mock())
        >>> adapter._session = session
        >>> adapter.observe().scene.scene_id
        'intro'
        """

        return self._require_session().observe()

    def available_actions(self) -> tuple[ActionObservation, ...]:
        """Return implemented, eligible actions at the current decision point.

        >>> from unittest.mock import Mock
        >>> from srd_arena.engine.api import SceneObservation
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
        >>> session = Mock()
        >>> session.observe.return_value = observation
        >>> adapter = HeadlessGameAdapter(Mock())
        >>> adapter._session = session
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
        >>> from srd_arena.engine.api import SceneObservation
        >>> action = ActionObservation("dodge", "Dodge", "action", "hero")
        >>> observation = GameObservation(SceneObservation("fight", None, (action,)), None, None, False)
        >>> session = Mock()
        >>> session.observe.return_value = observation
        >>> adapter = HeadlessGameAdapter(Mock())
        >>> adapter._session = session
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
        >>> session = Mock()
        >>> session.execute.return_value = CommandResult(update=Mock())
        >>> adapter = HeadlessGameAdapter(Mock())
        >>> adapter._session = session
        >>> adapter.select_action("dodge", expected_decision_id="turn:1").accepted
        True
        >>> command = session.execute.call_args.args[0]
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
        """Submit any engine command, including staged targeting.

        >>> from unittest.mock import Mock
        >>> session = Mock()
        >>> expected = CommandResult()
        >>> session.execute.return_value = expected
        >>> adapter = HeadlessGameAdapter(Mock())
        >>> adapter._session = session
        >>> adapter.submit(SelectAction("dodge", "turn:1")) is expected
        True
        """

        return self._require_session().execute(command)

    def advance_until_input_required(self) -> GameUpdate:
        """Advance scripted controllers until external input is required.

        >>> from unittest.mock import Mock
        >>> session = Mock()
        >>> update = Mock()
        >>> session.advance_until_input_required.return_value = update
        >>> adapter = HeadlessGameAdapter(Mock())
        >>> adapter._session = session
        >>> adapter.advance_until_input_required() is update
        True
        """

        return self._require_session().advance_until_input_required()

    def advance_one_automatic_action(self) -> GameUpdate:
        """Resolve one scripted action for step-oriented clients.

        >>> from unittest.mock import Mock
        >>> session = Mock()
        >>> update = Mock()
        >>> session.advance_one_automatic_action.return_value = update
        >>> adapter = HeadlessGameAdapter(Mock())
        >>> adapter._session = session
        >>> adapter.advance_one_automatic_action() is update
        True
        """

        return self._require_session().advance_one_automatic_action()

    def reset(self) -> GameObservation:
        """Reset the active game to its initial observation.

        >>> from unittest.mock import Mock
        >>> from srd_arena.engine.api import SceneObservation
        >>> initial = GameObservation(
        ...     SceneObservation("intro", "Ready?", ()), None, None, False
        ... )
        >>> session = Mock()
        >>> session.reset.return_value = initial
        >>> adapter = HeadlessGameAdapter(Mock())
        >>> adapter._session = session
        >>> adapter.reset().scene.scene_text
        'Ready?'
        """

        return self._require_session().reset()

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("Start an encounter before interacting with the game.")
        return self._session
