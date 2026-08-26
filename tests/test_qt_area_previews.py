from pathlib import Path

from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.frontends.qt.app import GameWindow
from srd_arena.frontends.qt.ui.encounter import BattlefieldWidget
from srd_arena.frontends.shared.session import BattlefieldView
from srd_arena.runtime.scenario import Scenario


SCENARIOS_ROOT = Path(__file__).parents[1] / "content" / "scenarios"


def test_slow_pending_area_preview_is_an_eight_square_cube(monkeypatch) -> None:
    def _tempo_archmage_first(self: EncounterState) -> None:
        self.initiative_entries = []
        self.initiative_order = [
            "tempo_archmage",
            *(ref for ref in self.creatures if ref != "tempo_archmage"),
        ]

    monkeypatch.setattr(EncounterState, "_roll_initiative", _tempo_archmage_first)
    session = Scenario(SCENARIOS_ROOT / "slow_showcase").create_session()
    scene = session.get_scene_view()
    slow_action = next(action for action in scene.action_details if action.label == "Cast Slow")

    window = GameWindow.__new__(GameWindow)
    window.session = session
    window._pending_target_mode = window._target_mode_for_action(slow_action)
    overlay = window._pending_area_overlay(scene.action_details)

    assert overlay is not None
    assert overlay["shape"] == "cube"

    preview = BattlefieldWidget._preview_area_overlay(
        overlay,
        (10.5, 6.5),
        BattlefieldView(
            width=22,
            height=14,
            creatures=[],
            summary_text="",
        ),
    )

    assert preview is not None
    assert preview["shape"] == "cube"
    assert preview["origin"] == {"x": 10, "y": 6}
    assert len(preview["cells"]) == 64
    assert {
        (cell["x"], cell["y"])
        for cell in preview["cells"]
    } == {(x, y) for y in range(3, 11) for x in range(7, 15)}
