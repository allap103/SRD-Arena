from __future__ import annotations

from typing import cast

from srd_arena.application.commands import (
    AimAction,
    CancelTargeting,
    ChangeTarget,
    CommandFailure,
    CommandResult,
    ConfirmTargeting,
    GameCommand,
    GameUpdate,
    SelectAction,
    SetResourceAllocation,
)
from srd_arena.application.game import RunningGame
from srd_arena.application.observations import (
    ActionObservation,
    DecisionObservation,
    EncounterObservation,
    GameObservation,
    GridObservation,
    SceneObservation,
)
from srd_arena.frontends.gui.presenter import GamePresenter


class _RunningGameStub:
    def __init__(self, observation: GameObservation) -> None:
        self.current_observation = observation
        self.command_result = _accepted_update(observation)
        self.automatic_update = _update(observation)
        self.commands: list[GameCommand] = []
        self.observe_count = 0

    def observe(self) -> GameObservation:
        self.observe_count += 1
        return self.current_observation

    def execute(self, command: GameCommand) -> CommandResult:
        self.commands.append(command)
        return self.command_result

    def advance_one_automatic_action(self) -> GameUpdate:
        return self.automatic_update

    def advance_until_input_required(self) -> GameUpdate:
        return self.automatic_update


def test_presenter_constructs_commands_with_the_current_decision() -> None:
    initial = _observation("decision-1")
    updated = _observation("decision-2")
    stub = _RunningGameStub(initial)
    stub.command_result = _accepted_update(updated)
    presenter = GamePresenter(cast(RunningGame, stub))

    presenter.select_action("attack")
    presenter.aim_action("fireball", 3.5, 4.5)
    presenter.change_target(
        "goblin",
        remove=True,
        source_trigger_id="eldritch_blast",
    )
    presenter.set_resource_allocation("goblin", 20)
    presenter.confirm_targeting()
    presenter.cancel_targeting()

    assert stub.commands == [
        SelectAction("attack", "decision-1"),
        AimAction("fireball", 3.5, 4.5, "decision-2"),
        ChangeTarget("goblin", True, "decision-2", "eldritch_blast"),
        SetResourceAllocation("goblin", 20, "decision-2"),
        ConfirmTargeting("decision-2"),
        CancelTargeting("decision-2"),
    ]
    assert presenter.observation == updated


def test_presenter_refreshes_after_a_rejected_command() -> None:
    initial = _observation("decision-1")
    refreshed = _observation("decision-2")
    stub = _RunningGameStub(initial)
    presenter = GamePresenter(cast(RunningGame, stub))
    stub.current_observation = refreshed
    stub.command_result = CommandResult(
        failure=CommandFailure("stale_decision", "The decision changed.")
    )

    update = presenter.select_action("attack")

    assert update is None
    assert presenter.observation == refreshed
    assert stub.observe_count == 2


def test_presenter_retains_single_automatic_action_observation() -> None:
    initial = _observation("decision-1")
    advanced = _observation("decision-2")
    stub = _RunningGameStub(initial)
    stub.automatic_update = _update(advanced)
    presenter = GamePresenter(cast(RunningGame, stub))

    update = presenter.advance_one_automatic_action()

    assert update.observation == advanced
    assert presenter.observation == advanced


def test_presenter_retains_full_automatic_advance_observation() -> None:
    initial = _observation("decision-1")
    advanced = _observation("decision-2")
    stub = _RunningGameStub(initial)
    stub.automatic_update = _update(advanced)
    presenter = GamePresenter(cast(RunningGame, stub))

    update = presenter.advance_until_input_required()

    assert update.observation == advanced
    assert presenter.observation == advanced


def test_presenter_owns_staged_targeting_mode() -> None:
    target_action = ActionObservation(
        id="add-goblin",
        label="Add Goblin",
        kind="toggle_spell_target",
        creature_ref="actor",
        source_trigger_id="eldritch_blast",
        target_ref="goblin",
    )
    initial = _observation("decision-1", actions=(target_action,))
    stub = _RunningGameStub(initial)
    presenter = GamePresenter(cast(RunningGame, stub))

    selection = presenter.select_action(target_action.id)

    assert selection is not None
    assert selection.selected_action == target_action
    assert presenter.pending_target_mode is not None
    assert presenter.pending_target_mode.kind == "toggle_spell_target"
    assert presenter.pending_target_mode.source_trigger_id == "eldritch_blast"

    presenter.clear_target_mode()

    assert presenter.pending_target_mode is None


def _observation(
    decision_id: str,
    *,
    actions: tuple[ActionObservation, ...] = (),
) -> GameObservation:
    return GameObservation(
        scene=SceneObservation(
            scene_id="arena",
            scene_text=None,
            action_details=actions,
        ),
        encounter=EncounterObservation(
            encounter_id="arena",
            grid=GridObservation(width=10, height=10),
            round_number=1,
            decision=DecisionObservation(
                id=decision_id,
                kind="turn",
                creature_ref="actor",
            ),
            creatures=(),
            initiative=(),
            ongoing_effects=(),
            team_ids=(),
            targeting=None,
        ),
        transition=None,
        requires_automatic_advance=False,
    )


def _accepted_update(observation: GameObservation) -> CommandResult:
    return CommandResult(update=_update(observation))


def _update(observation: GameObservation) -> GameUpdate:
    return GameUpdate(
        observation=observation,
        messages=(),
        events=(),
        selected_action_id=None,
        selected_choice_text=None,
        scene_changed=False,
        should_exit=False,
    )
