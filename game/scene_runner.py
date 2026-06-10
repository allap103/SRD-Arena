from .game_logging import CHANNEL_CHOICE, CHANNEL_SCENE, CHANNEL_SYSTEM, get_game_logger
from .session import GameSession, TurnResult

SCENE_LOGGER = get_game_logger(CHANNEL_SCENE)
CHOICE_LOGGER = get_game_logger(CHANNEL_CHOICE)
SYSTEM_LOGGER = get_game_logger(CHANNEL_SYSTEM)


class SceneRunner:
    def display(self, session: GameSession) -> None:
        scene_view = session.get_scene_view()
        SCENE_LOGGER.info(scene_view.scene_text)
        for i, choice in enumerate(scene_view.choices):
            CHOICE_LOGGER.info(f"{i + 1}. {choice}")

    def render_turn_result(self, result: TurnResult) -> None:
        for channel, message in result.messages:
            if channel == "scene":
                SCENE_LOGGER.info(message)
            elif channel == "choice":
                CHOICE_LOGGER.info(message)
            else:
                SYSTEM_LOGGER.info(message)

    def run(self, session: GameSession) -> str | None:
        self.display(session)
        choice = input("Input a number: ")
        CHOICE_LOGGER.info(f"You chose: {choice}")
        try:
            result = session.choose(int(choice) - 1)
            self.render_turn_result(result)
            return result.next_scene_id
        except IndexError:
            CHOICE_LOGGER.info("Invalid choice. Please try again.")
            return self.run(session)
        except ValueError:
            CHOICE_LOGGER.info("Invalid input. Please enter a valid number.")
            return self.run(session)
