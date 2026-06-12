from pathlib import Path

import pytest

from game.loaders import load_scene

nx = pytest.importorskip("networkx")

from visualization.scene_graph import build_scene_graph, render_scene_graph


def test_build_scene_graph_keeps_multiple_choices_to_same_target() -> None:
    scene = load_scene("sample_game/scenes/scene_2")
    scene.choices.append(scene.choices[0])

    graph = build_scene_graph({scene.id: scene})

    assert isinstance(graph, nx.MultiDiGraph)
    assert graph.number_of_edges("scene_2", "scene_1") == 2


def test_build_scene_graph_marks_missing_target_nodes() -> None:
    scene = load_scene("sample_game/scenes/scene_2")
    scene.choices[0].next_scene = "missing_scene"

    graph = build_scene_graph({scene.id: scene})

    assert graph.nodes["missing_scene"]["exists"] is False


def test_render_scene_graph_writes_png(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")

    output = tmp_path / "scene_graph.png"

    rendered_path = render_scene_graph("sample_game", output)

    assert rendered_path == output
    assert output.exists()
    assert output.stat().st_size > 0
