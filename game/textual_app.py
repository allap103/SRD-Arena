from textual.app import App, ComposeResult
from textual.containers import Container, Grid, VerticalScroll
from textual.widgets import Button, Static

from .engine import GAME_DIR, Game
from .session import (
    ActionView,
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

    #encounter-panel {
        display: none;
        layout: vertical;
        height: auto;
        margin: 0 1 1 1;
        padding: 0;
    }

    #encounter-economy {
        height: auto;
        border: round $accent;
        margin: 0 0 1 0;
        padding: 1 2;
    }

    #battlefield-panel {
        height: auto;
        min-height: 10;
        margin: 0 0 1 0;
    }

    #encounter-controls {
        layout: horizontal;
        height: auto;
    }

    #movement-panel,
    #encounter-actions-shell {
        border: round $primary;
        padding: 1;
    }

    #movement-panel {
        width: 19;
        margin-right: 1;
    }

    #movement-grid {
        grid-size: 3 3;
        grid-gutter: 1 1;
        height: auto;
    }

    .move-button {
        min-width: 3;
        width: 100%;
        height: 3;
        content-align: center middle;
    }

    #movement-center {
        content-align: center middle;
        width: 100%;
        height: 3;
    }

    #encounter-actions-shell {
        layout: vertical;
        width: 1fr;
    }

    #encounter-actions-header {
        layout: horizontal;
        height: auto;
        margin-bottom: 1;
    }

    #encounter-actions-title {
        width: 1fr;
        content-align: left middle;
    }

    #end-turn-button {
        width: 16;
        content-align: center middle;
    }

    #encounter-action-list {
        max-height: 16;
    }

    #scene-text,
    #last-action-text,
    #encounter-economy-text,
    #battlefield-text {
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
        self._encounter_list_version = 0
        self._system_choice_start = 0
        self._encounter_action_details: list[ActionView] = []

    def compose(self) -> ComposeResult:
        main_content = Container(
            self._compose_last_action_panel(),
            self._compose_scene_panel(),
            self._compose_choices_panel(),
            self._compose_encounter_panel(),
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

    def _compose_battlefield_panel(self) -> Container:
        panel = Container(
            Static("", id="battlefield-text"),
            id="battlefield-panel",
            classes="panel",
        )
        panel.border_title = "Battlefield"
        return panel

    def _compose_encounter_panel(self) -> Container:
        panel = Container(
            Container(
                Static("", id="encounter-economy-text"),
                id="encounter-economy",
            ),
            self._compose_battlefield_panel(),
            Container(
                self._compose_movement_panel(),
                self._compose_encounter_actions_shell(),
                id="encounter-controls",
            ),
            id="encounter-panel",
        )
        return panel

    def _compose_movement_panel(self) -> Container:
        panel = Container(
            Grid(
                Button("", id="move-up-left", classes="move-button"),
                Button("", id="move-up", classes="move-button"),
                Button("", id="move-up-right", classes="move-button"),
                Button("", id="move-left", classes="move-button"),
                Static("Move", id="movement-center"),
                Button("", id="move-right", classes="move-button"),
                Button("", id="move-down-left", classes="move-button"),
                Button("", id="move-down", classes="move-button"),
                Button("", id="move-down-right", classes="move-button"),
                id="movement-grid",
            ),
            id="movement-panel",
        )
        panel.border_title = "Movement"
        return panel

    def _compose_encounter_actions_shell(self) -> Container:
        panel = Container(
            Container(
                Static("Actions", id="encounter-actions-title"),
                Button("End Turn", id="end-turn-button"),
                id="encounter-actions-header",
            ),
            VerticalScroll(id="encounter-action-list"),
            id="encounter-actions-shell",
        )
        panel.border_title = "Combat"
        return panel

    def on_mount(self) -> None:
        self.query_one("#last-action-panel", Container).display = False
        self.show_menu_root()
        self.refresh_scene()

    def refresh_scene(self) -> None:
        self._choice_list_version += 1
        scene_view = self.session.get_scene_view()

        story_choices = scene_view.choices[:-SYSTEM_CHOICE_COUNT]
        self._system_choice_start = len(story_choices)
        self._encounter_action_details = scene_view.action_details[:-SYSTEM_CHOICE_COUNT]

        choice_list = self.query_one("#choice-list", VerticalScroll)
        encounter_panel = self.query_one("#encounter-panel", Container)
        battlefield_panel = self.query_one("#battlefield-panel", Container)
        scene_panel = self.query_one("#scene-panel", Container)
        last_action_panel = self.query_one("#last-action-panel", Container)

        if self.session.encounter_state is None:
            self.query_one("#scene-text", Static).update(scene_view.scene_text or "")
            encounter_panel.display = False
            battlefield_panel.display = False
            scene_panel.display = True
            if not self.query_one("#last-action-text", Static).renderable:
                last_action_panel.display = False
            choice_list.display = True
            choice_list.border_title = "Choices"
            choice_list.remove_children()
            for index, choice_text in enumerate(story_choices):
                choice_list.mount(
                    Button(
                        choice_text,
                        id=f"choice-{self._choice_list_version}-{index}",
                        classes="choice-button",
                    )
                )
            return

        scene_panel.display = False
        last_action_panel.display = False
        choice_list.display = False
        encounter_panel.display = True
        battlefield_panel.display = True
        self._refresh_encounter_controls()

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
        if button_id.startswith("encounter-action-"):
            choice_index = int(button_id.rsplit("-", maxsplit=1)[1])
            self.apply_turn_result(self.session.choose(choice_index))
            return
        if button_id == "end-turn-button":
            end_turn_index = self._find_encounter_action_index("wait", "pass")
            if end_turn_index is not None:
                self.apply_turn_result(self.session.choose(end_turn_index))
            return
        if button_id.startswith("move-"):
            direction = button_id.removeprefix("move-")
            move_index = self._find_encounter_move_index(direction)
            if move_index is not None:
                self.apply_turn_result(self.session.choose(move_index))
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

    def _refresh_encounter_controls(self) -> None:
        self._encounter_list_version += 1
        combat_state = self.session.encounter_state.export_state(self.session.player)
        economy_text = self._format_action_economy(combat_state)
        self.query_one("#encounter-economy-text", Static).update(economy_text)
        self.query_one("#battlefield-text", Static).update(
            self.session.encounter_state.render(self.session.player)
        )

        movement_actions = {
            action.kind == "move" and str(action.value) or "": action
            for action in self._encounter_action_details
            if action.kind == "move"
        }
        arrow_labels = {
            "up-left": "↖",
            "up": "↑",
            "up-right": "↗",
            "left": "←",
            "right": "→",
            "down-left": "↙",
            "down": "↓",
            "down-right": "↘",
        }
        for direction, arrow in arrow_labels.items():
            button = self.query_one(f"#move-{direction}", Button)
            action = movement_actions.get(direction)
            button.label = arrow
            button.disabled = action is None

        action_list = self.query_one("#encounter-action-list", VerticalScroll)
        action_list.remove_children()
        non_movement_actions = [
            action
            for action in self._encounter_action_details
            if action.kind not in {"move", "wait", "pass"}
        ]
        for action in non_movement_actions:
            action_list.mount(
                Button(
                    action.label,
                    id=f"encounter-action-{self._encounter_list_version}-{action.index}",
                    classes="choice-button",
                )
            )

        corner_action = self._find_encounter_action("wait") or self._find_encounter_action("pass")
        end_turn_button = self.query_one("#end-turn-button", Button)
        if corner_action is None:
            end_turn_button.label = "End Turn"
            end_turn_button.disabled = True
        else:
            end_turn_button.label = "Pass Reaction" if corner_action.kind == "pass" else "End Turn"
            end_turn_button.disabled = False

        title = "Reactions" if combat_state["decision"]["kind"] == "reaction" else "Actions"
        self.query_one("#encounter-actions-title", Static).update(title)

    def _format_action_economy(self, combat_state: dict[str, object]) -> str:
        player_state = combat_state["player"]
        decision = combat_state["decision"]
        movement_remaining = player_state["movement_remaining"]
        normal_turn = decision["actor_ref"] == "player" and decision["kind"] == "turn"
        action_status = "Ready" if normal_turn else "Waiting"
        bonus_status = "Not implemented"
        reaction_status = "Ready" if player_state["reaction_available"] else "Spent"
        return "\n".join(
            [
                f"Action: {action_status}",
                f"Bonus Action: {bonus_status}",
                f"Reaction: {reaction_status}",
                f"Movement: {movement_remaining} squares",
            ]
        )

    def _find_encounter_move_index(self, direction: str) -> int | None:
        action = next(
            (
                action
                for action in self._encounter_action_details
                if action.kind == "move" and action.label.lower() == f"move {direction}"
            ),
            None,
        )
        return action.index if action is not None else None

    def _find_encounter_action(self, *kinds: str) -> ActionView | None:
        return next(
            (action for action in self._encounter_action_details if action.kind in kinds),
            None,
        )

    def _find_encounter_action_index(self, *kinds: str) -> int | None:
        action = self._find_encounter_action(*kinds)
        return action.index if action is not None else None


def run_textual_app(game: Game | None = None) -> None:
    app = CyoaTextualApp(game=game)
    app.run()
