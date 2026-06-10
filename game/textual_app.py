from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Button, Label, Static

from .engine import GAME_DIR, Game
from .session import GameSession


class CyoaTextualApp(App[None]):
    def __init__(self, game: Game | None = None):
        super().__init__()
        self.game = game or Game(GAME_DIR)
        self.session: GameSession = self.game.create_session()
        self._choice_list_version = 0

    def compose(self) -> ComposeResult:
        yield Static("", id="scene-text")
        yield Container(id="choice-list")

    def on_mount(self) -> None:
        self.refresh_scene()

    def refresh_scene(self) -> None:
        self._choice_list_version += 1
        scene_view = self.session.get_scene_view()
        self.query_one("#scene-text", Static).update(scene_view.scene_text or "")

        choice_list = self.query_one("#choice-list", Container)
        choice_list.remove_children()
        for index, choice_text in enumerate(scene_view.choices):
            choice_list.mount(
                Button(
                    choice_text,
                    id=f"choice-{self._choice_list_version}-{index}",
                    classes="choice-button",
                )
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if not button_id.startswith("choice-"):
            return

        choice_index = int(button_id.rsplit("-", maxsplit=1)[1])
        self.session.choose(choice_index)
        self.refresh_scene()


def run_textual_app() -> None:
    app = CyoaTextualApp()
    app.run()
