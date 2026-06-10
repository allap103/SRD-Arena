from game.engine import GAME_DIR, Game
from game.game_logging import configure_game_logging

if __name__ == "__main__":
    configure_game_logging()
    game = Game(GAME_DIR)
    game.run()
