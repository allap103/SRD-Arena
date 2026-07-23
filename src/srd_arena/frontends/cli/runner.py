from ...runtime.models import TurnResult
from ...runtime.session import Session
from ...infrastructure.logging import (
    CHANNEL_CHOICE,
    CHANNEL_SCENE,
    CHANNEL_SYSTEM,
    get_game_logger,
)
from .combat import render_encounter_text

SCENE_LOGGER = get_game_logger(CHANNEL_SCENE)
CHOICE_LOGGER = get_game_logger(CHANNEL_CHOICE)
SYSTEM_LOGGER = get_game_logger(CHANNEL_SYSTEM)


class CliRunner:
    def display(self, session: Session) -> None:
        scene_view = session.get_scene_view()
        scene_text = scene_view.scene_text
        if scene_text is None and session.encounter_state is not None:
            scene_text = render_encounter_text(session.encounter_state, session.player)
        if scene_text is not None:
            SCENE_LOGGER.info(scene_text)
        for index, choice in enumerate(scene_view.choices):
            CHOICE_LOGGER.info(f"{index + 1}. {choice}")

    def render_turn_result(self, result: TurnResult) -> None:
        for channel, message in result.messages:
            if channel == "scene":
                SCENE_LOGGER.info(message)
            elif channel == "choice":
                CHOICE_LOGGER.info(message)
            else:
                SYSTEM_LOGGER.info(message)

    def run(self, session: Session) -> bool:
        self.display(session)
        choice = input("Input a number: ")
        CHOICE_LOGGER.info(f"You chose: {choice}")
        try:
            result = session.choose(int(choice) - 1)
            self.render_turn_result(result)
            return not result.should_exit
        except IndexError:
            CHOICE_LOGGER.info("Invalid choice. Please try again.")
            return self.run(session)
        except ValueError:
            CHOICE_LOGGER.info("Invalid input. Please enter a valid number.")
            return self.run(session)
