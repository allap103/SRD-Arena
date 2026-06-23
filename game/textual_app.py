from textual.app import App, ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Button, Static

from .engine import GAME_DIR, Game
from .session import (
    EXIT_CHOICE_TEXT,
    LOAD_CHOICE_TEXT,
    SAVE_CHOICE_TEXT,
    GameSession,
    TurnResult,
)

SYSTEM_CHOICE_COUNT = 3


class CyoaTextualApp(App[None]):
    CSS = """
    #app-shell {
        layout: horizontal;
        height: 100%;
        width: 100%;
    }

    #main-content {
        layout: vertical;
        height: 100%;
        width: 1fr;
    }

    #sidebar {
        width: 20;
        height: 100%;
        border: round $primary;
        padding: 1;
    }

    .panel {
        border: round $primary;
        margin: 0 1 1 1;
        padding: 1 2;
    }

    #last-action-panel {
        height: auto;
    }

    #scene-panel {
        height: 1fr;
        min-height: 5;
    }

    #choices-panel {
        height: auto;
        max-height: 50%;
    }

    #scene-text,
    #last-action-text {
        width: 100%;
    }

    .choice-button,
    .sidebar-button,
    .system-button {
        width: 100%;
        margin-bottom: 1;
        content-align: left middle;
    }

    .menu-view {
        height: 1fr;
    }
    """

    def __init__(self, game: Game | None = None):
        super().__init__()
        self.game = game or Game(GAME_DIR)
        self.session: GameSession = self.game.create_session()
        self._items_by_id = {item.id: item for item in self.game.items}
        self._choice_list_version = 0
        self._system_choice_start = 0

    def compose(self) -> ComposeResult:
        main_content = Container(
            self._compose_last_action_panel(),
            self._compose_scene_panel(),
            self._compose_choices_panel(),
            id="main-content",
        )

        sidebar = Container(
            self._compose_menu_root(),
            self._compose_inventory_menu(),
            self._compose_attributes_menu(),
            self._compose_system_menu(),
            id="sidebar",
        )
        sidebar.border_title = "Menu"

        yield Container(main_content, sidebar, id="app-shell")

    def _compose_menu_root(self) -> Container:
        return Container(
            Button("Attributes", id="attributes-button", classes="sidebar-button"),
            Button(
                "\U0001f392 Inventory",
                id="inventory-button",
                classes="sidebar-button",
            ),
            Button("\u2699 System", id="system-button", classes="sidebar-button"),
            id="menu-root",
            classes="menu-view",
        )

    def _compose_inventory_menu(self) -> Container:
        return Container(
            Button("\u2190 Back", id="inventory-back-button", classes="sidebar-button"),
            Static("", id="inventory-detail"),
            id="inventory-menu",
            classes="menu-view",
        )

    def _compose_attributes_menu(self) -> Container:
        return Container(
            Button("\u2190 Back", id="attributes-back-button", classes="sidebar-button"),
            Static("", id="attributes-detail"),
            id="attributes-menu",
            classes="menu-view",
        )

    def _compose_system_menu(self) -> Container:
        return Container(
            Button("\u2190 Back", id="system-back-button", classes="sidebar-button"),
            Button(SAVE_CHOICE_TEXT, id="save-button", classes="system-button"),
            Button(LOAD_CHOICE_TEXT, id="load-button", classes="system-button"),
            Button(EXIT_CHOICE_TEXT, id="exit-button", classes="system-button"),
            id="system-menu",
            classes="menu-view",
        )

    def _compose_last_action_panel(self) -> Container:
        panel = Container(
            Static("", id="last-action-text"),
            id="last-action-panel",
            classes="panel",
        )
        panel.border_title = "Last Action"
        return panel

    def _compose_scene_panel(self) -> Container:
        panel = Container(
            Static("", id="scene-text"),
            id="scene-panel",
            classes="panel",
        )
        panel.border_title = "Scene"
        return panel

    def _compose_choices_panel(self) -> VerticalScroll:
        choices_panel = VerticalScroll(id="choice-list", classes="panel")
        choices_panel.border_title = "Choices"
        return choices_panel

    def on_mount(self) -> None:
        self.query_one("#last-action-panel", Container).display = False
        self.show_menu_root()
        self.refresh_scene()

    def refresh_scene(self) -> None:
        self._choice_list_version += 1
        scene_view = self.session.get_scene_view()
        self.query_one("#scene-text", Static).update(scene_view.scene_text or "")

        story_choices = scene_view.choices[:-SYSTEM_CHOICE_COUNT]
        self._system_choice_start = len(story_choices)

        choice_list = self.query_one("#choice-list", VerticalScroll)
        choice_list.remove_children()
        for index, choice_text in enumerate(story_choices):
            choice_list.mount(
                Button(
                    choice_text,
                    id=f"choice-{self._choice_list_version}-{index}",
                    classes="choice-button",
                )
            )

    def write_messages(self, messages: list[tuple[str, str]]) -> None:
        last_action_panel = self.query_one("#last-action-panel", Container)
        last_action_text = self.query_one("#last-action-text", Static)
        if not messages:
            last_action_panel.display = False
            last_action_text.update("")
            return

        last_action_text.update("\n".join(message for _, message in messages))
        last_action_panel.display = True

    def apply_turn_result(self, result: TurnResult) -> None:
        self.write_messages(result.messages)
        if result.should_exit:
            self.exit()
            return
        self.refresh_scene()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "attributes-button":
            self.show_attributes()
            return
        if button_id == "inventory-button":
            self.show_inventory()
            return
        if button_id == "system-button":
            self.show_system_menu()
            return
        if button_id in {
            "attributes-back-button",
            "inventory-back-button",
            "system-back-button",
        }:
            self.show_menu_root()
            return
        if button_id == "save-button":
            self.apply_turn_result(self.session.choose(self._system_choice_start))
            return
        if button_id == "load-button":
            self.apply_turn_result(self.session.choose(self._system_choice_start + 1))
            return
        if button_id == "exit-button":
            self.apply_turn_result(self.session.choose(self._system_choice_start + 2))
            return
        if not button_id.startswith("choice-"):
            return

        choice_index = int(button_id.rsplit("-", maxsplit=1)[1])
        result = self.session.choose(choice_index)
        self.apply_turn_result(result)

    def show_menu_root(self) -> None:
        self.show_sidebar_view("menu-root")

    def show_system_menu(self) -> None:
        self.show_sidebar_view("system-menu")

    def show_sidebar_view(self, view_id: str) -> None:
        for candidate_id in (
            "menu-root",
            "inventory-menu",
            "attributes-menu",
            "system-menu",
        ):
            self.query_one(f"#{candidate_id}", Container).display = (
                candidate_id == view_id
            )

    def show_inventory(self) -> None:
        items = self.session.player.inventory.items
        inventory_text = (
            "Inventory is empty."
            if not items
            else "\n".join(self.display_item_name(item_id) for item_id in items)
        )
        self.query_one("#inventory-detail", Static).update(inventory_text)
        self.show_sidebar_view("inventory-menu")

    def display_item_name(self, item_id: str) -> str:
        item = self._items_by_id.get(item_id)
        return item.name if item else item_id

    def show_attributes(self) -> None:
        player = self.session.player
        attributes = player.attributes
        attributes_text = "\n".join(
            [
                f"Name: {player.name}",
                f"HP: {player.get_health()}/{player.get_max_health()}",
                f"AC: {player.get_armor_class()}",
                f"Level: {attributes.level}",
                f"STR: {attributes.strength}",
                f"DEX: {attributes.dexterity}",
                f"CON: {attributes.constitution}",
                f"WIS: {attributes.wisdom}",
                f"INT: {attributes.intelligence}",
                f"CHA: {attributes.charisma}",
                f"PB: +{attributes.proficiency_bonus}",
            ]
        )
        self.query_one("#attributes-detail", Static).update(attributes_text)
        self.show_sidebar_view("attributes-menu")


def run_textual_app(game: Game | None = None) -> None:
    app = CyoaTextualApp(game=game)
    app.run()
