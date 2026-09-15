"""Launch the GUI as a spectator of a saved model playing its encounter."""

import argparse
import sys
from pathlib import Path

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.training.checkpoint import load_checkpoint
from srd_arena.training.playback import ModelPlayback


def main() -> None:
    """Load the saved policy and show paced model/scripted actions in the GUI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--mode", choices=("sample", "greedy"), default="sample")
    parser.add_argument("--sampling-seed", type=int, default=123)
    parser.add_argument("--delay-ms", type=int, default=500)
    parser.add_argument("--paused", action="store_true")
    args = parser.parse_args()
    if not 20 <= args.delay_ms <= 10000 or args.sampling_seed < 0:
        parser.error("Delay must be 20-10000 ms and sampling seed must be nonnegative")
    try:
        checkpoint = load_checkpoint(args.run_dir, device_name=args.device)
        driver = ModelPlayback(
            checkpoint, sampling_seed=args.sampling_seed, mode=args.mode
        )
        catalog = EncounterCatalog()
        summary = next(
            e
            for e in catalog.available_encounters()
            if e.id == checkpoint.config.encounter
        )
    except (OSError, ValueError, RuntimeError, KeyError, StopIteration) as exc:
        parser.exit(1, f"Unable to watch model: {exc}\n")

    from PySide6.QtWidgets import QApplication

    from srd_arena.frontends.gui.theme import apply_fantasy_theme
    from srd_arena.frontends.gui.watch import WatchWindow

    instance = QApplication.instance()
    app = instance if isinstance(instance, QApplication) else QApplication(sys.argv)
    apply_fantasy_theme(app)
    window = WatchWindow(
        driver,
        image_root=catalog.image_root,
        presentation_config=summary.presentation,
        delay_ms=args.delay_ms,
        paused=args.paused,
    )
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
