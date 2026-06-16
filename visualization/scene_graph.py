from __future__ import annotations

import argparse
from pathlib import Path
import tomllib

from game.loaders import load_scene
from game.models.scene import Scene


def resolve_scenes_dir(game_dir: str | Path) -> Path:
    game_path = Path(game_dir)
    config_path = game_path / "config.toml"
    if not config_path.exists():
        return game_path / "scenes"

    with open(config_path, "rb") as config_file:
        config = tomllib.load(config_file)

    scenes_subdir = config.get("directories", {}).get("scenes", "scenes")
    return game_path / scenes_subdir


def load_scenes_from_game_dir(game_dir: str | Path) -> dict[str, Scene]:
    scenes_dir = resolve_scenes_dir(game_dir)
    return {
        scene.id: scene for scene in (load_scene(path) for path in scenes_dir.glob("*"))
    }


def build_scene_graph(scenes: dict[str, Scene]):
    import networkx as nx

    graph = nx.MultiDiGraph()
    known_scene_ids = set(scenes)

    for scene_id, scene in scenes.items():
        graph.add_node(
            scene_id,
            text=scene.text,
            type=scene.type,
            exists=True,
        )

        for index, choice in enumerate(scene.choices):
            if choice.next_scene is None:
                continue

            if (
                choice.next_scene not in known_scene_ids
                and choice.next_scene not in graph
            ):
                graph.add_node(
                    choice.next_scene,
                    text=None,
                    type="missing",
                    exists=False,
                )

            graph.add_edge(
                scene_id,
                choice.next_scene,
                key=index,
                choice_text=choice.choice_text,
                message=choice.message,
                requirements=choice.requirements,
                test=choice.test,
            )

    return graph


def render_scene_graph(
    game_dir: str | Path,
    output_path: str | Path,
    start_scene_id: str = "welcome",
) -> Path:
    import matplotlib

    matplotlib.use("Agg")

    import matplotlib.pyplot as plt
    import networkx as nx

    scenes = load_scenes_from_game_dir(game_dir)
    graph = build_scene_graph(scenes)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    positions = nx.kamada_kawai_layout(graph) if graph.number_of_nodes() > 1 else None

    fig_width = max(8, graph.number_of_nodes() * 1.2)
    fig_height = max(6, graph.number_of_nodes() * 0.9)
    figure, axis = plt.subplots(figsize=(fig_width, fig_height))

    terminal_nodes = {node for node in graph.nodes if graph.out_degree(node) == 0}
    missing_nodes = {
        node for node, data in graph.nodes(data=True) if not data.get("exists", True)
    }

    def node_style(node_id: str) -> dict[str, str | float]:
        if node_id == start_scene_id:
            return {"facecolor": "#bbf7d0", "edgecolor": "#166534", "linewidth": 2.0}
        if node_id in missing_nodes:
            return {"facecolor": "#fecaca", "edgecolor": "#991b1b", "linewidth": 1.8}
        if node_id in terminal_nodes:
            return {"facecolor": "#fde68a", "edgecolor": "#92400e", "linewidth": 1.8}
        return {"facecolor": "#dbeafe", "edgecolor": "#1e3a8a", "linewidth": 1.6}

    for node_id in graph.nodes:
        x_pos, y_pos = positions[node_id]
        style = node_style(node_id)
        axis.text(
            x_pos,
            y_pos,
            node_id,
            ha="center",
            va="center",
            fontsize=10,
            fontweight="bold",
            zorder=3,
            bbox={
                "boxstyle": "round,pad=0.5,rounding_size=0.12",
                "facecolor": style["facecolor"],
                "edgecolor": style["edgecolor"],
                "linewidth": style["linewidth"],
            },
        )

    edge_connection_radii: dict[tuple[str, str, int], float] = {}
    parallel_edge_counts: dict[tuple[str, str], int] = {}
    for source, target, key in graph.edges(keys=True):
        pair = (source, target)
        edge_index = parallel_edge_counts.get(pair, 0)
        parallel_edge_counts[pair] = edge_index + 1
        edge_connection_radii[(source, target, key)] = 0.18 * (edge_index + 1)

    nx.draw_networkx_edges(
        graph,
        positions,
        edge_color="#64748b",
        width=1.8,
        arrows=True,
        arrowsize=28,
        arrowstyle="-|>",
        min_source_margin=34,
        min_target_margin=40,
        connectionstyle="arc3,rad=0.18",
        ax=axis,
    )

    edge_labels = {}
    edge_label_positions = {}
    for source, target, key, data in graph.edges(keys=True, data=True):
        label = data["choice_text"]
        if len(label) > 28:
            label = f"{label[:25]}..."
        edge_labels[(source, target, key)] = label
        edge_label_positions[(source, target, key)] = 0.4 if source == target else 0.5

    for source, target, key in graph.edges(keys=True):
        nx.draw_networkx_edge_labels(
            graph,
            positions,
            edge_labels={(source, target, key): edge_labels[(source, target, key)]},
            font_size=8,
            rotate=False,
            label_pos=edge_label_positions[(source, target, key)],
            connectionstyle=f"arc3,rad={edge_connection_radii[(source, target, key)]}",
            bbox={"alpha": 0.85, "edgecolor": "none", "facecolor": "white", "pad": 0.2},
            ax=axis,
        )

    axis.set_title(f"Scene Graph for {Path(game_dir).name}")
    axis.axis("off")
    figure.tight_layout()
    figure.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render a game scene graph to an image file."
    )
    parser.add_argument(
        "game_dir", help="Path to the game directory containing a scenes folder."
    )
    parser.add_argument(
        "-o",
        "--output",
        default="scene_graph.png",
        help="Output image path. Defaults to scene_graph.png.",
    )
    parser.add_argument(
        "--start-scene",
        default="welcome",
        help="Scene id to highlight as the starting scene. Defaults to welcome.",
    )
    args = parser.parse_args()

    output = render_scene_graph(
        game_dir=args.game_dir,
        output_path=args.output,
        start_scene_id=args.start_scene,
    )
    print(output)


if __name__ == "__main__":
    main()
