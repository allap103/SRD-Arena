from __future__ import annotations

from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
import uvicorn

from game.engine import GAME_DIR, Game
from game.save import SAVEGAME_EXAMPLE, SaveGame, create_save, restore_save
from game.session import GameSession


class SavegameApi:
    def __init__(self, game: Game | None = None):
        self.game = game or Game(GAME_DIR)
        self.session: GameSession = self.game.create_session()

    def get_save_payload(self) -> dict:
        return create_save(self.session).model_dump(mode="json")

    def load_save_payload(self, save: SaveGame) -> dict:
        self.session = restore_save(save, self.game.directory)
        return {
            "status": "ok",
            "current_scene_id": self.session.current_scene_id,
            "player_health": self.session.player.get_health(),
        }

    def get_stats_payload(self) -> dict:
        return {
            "current_scene_id": self.session.current_scene_id,
            "player_health": self.session.player.get_health(),
            "player_max_health": self.session.player.get_max_health(),
            "scene_count": len(self.session.scenes),
            "has_active_encounter": self.session.get_encounter_snapshot() is not None,
        }

    def get_options_payload(self) -> dict:
        scene_view = self.session.get_scene_view()
        return {
            "current_scene_id": scene_view.scene_id,
            "actions": [
                {"index": index, "label": choice}
                for index, choice in enumerate(scene_view.choices)
            ],
        }

    def choose_action_payload(self, action_index: int) -> dict:
        try:
            result = self.session.choose(action_index)
        except IndexError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return {
            "current_scene_id": self.session.current_scene_id,
            "selected_index": result.selected_index,
            "selected_action": result.selected_choice_text,
            "messages": [
                {"channel": channel, "message": message}
                for channel, message in result.messages
            ],
            "scene_changed": result.scene_changed,
            "should_exit": result.should_exit,
            "scene_text": result.scene.scene_text,
            "actions": [
                {"index": index, "label": choice}
                for index, choice in enumerate(result.scene.choices)
            ],
        }

    def create_app(self) -> FastAPI:
        app = FastAPI(title="CYOA Savegame API")

        @app.get("/save")
        def get_save() -> dict:
            return self.get_save_payload()

        @app.post("/load")
        def load_game(
            save: SaveGame = Body(
                ...,
                openapi_examples={
                    "sample_game_save": {
                        "summary": "Working savegame for the bundled sample adventure",
                        "value": SAVEGAME_EXAMPLE,
                    }
                },
            )
        ) -> dict:
            return self.load_save_payload(save)

        @app.get("/stats")
        def get_stats() -> dict:
            return self.get_stats_payload()

        @app.get("/actions")
        def get_actions() -> dict:
            return self.get_options_payload()

        @app.post("/actions/{action_index}")
        def choose_action(action_index: int) -> dict:
            return self.choose_action_payload(action_index)

        return app


def run_savegame_api(
    host: str = "127.0.0.1",
    port: int = 8000,
    game_dir: str | Path = GAME_DIR,
) -> None:
    api = SavegameApi(Game(str(game_dir)))
    uvicorn.run(api.create_app(), host=host, port=port)
