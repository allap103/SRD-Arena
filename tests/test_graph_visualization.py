from pathlib import Path

import pytest
from visualization.scene_graph import (
    build_scene_graph,
    load_scenes_from_game_dir,
    render_scene_graph,
)

nx = pytest.importorskip("networkx")

FIXTURE_GAME_DIR = Path(__file__).parent / "fixtures" / "graph_game"


def test_build_scene_graph_keeps_multiple_choices_to_same_target() -> None:
    scenes = load_scenes_from_game_dir(FIXTURE_GAME_DIR)

    graph = build_scene_graph(scenes)

    assert isinstance(graph, nx.MultiDiGraph)
    assert graph.number_of_edges("start", "shared_target") == 2


def test_build_scene_graph_marks_missing_target_nodes() -> None:
    scenes = load_scenes_from_game_dir(FIXTURE_GAME_DIR)

    graph = build_scene_graph(scenes)

    assert graph.nodes["missing_target"]["exists"] is False


def test_render_scene_graph_writes_png(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")

    output = tmp_path / "scene_graph.png"

    rendered_path = render_scene_graph(
        FIXTURE_GAME_DIR,
        output,
        start_scene_id="start",
    )

    assert rendered_path == output
    assert output.exists()
    assert output.stat().st_size > 0
