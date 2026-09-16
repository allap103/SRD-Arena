"""Launch the optional local combat inspector."""

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path


def main() -> None:
    """Run Streamlit bound to localhost without enabling usage telemetry."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()
    if importlib.util.find_spec("streamlit") is None:
        parser.exit(1, "Install the observability extra to use the inspector.\n")
    if not 1 <= args.port <= 65535:
        parser.exit(1, "Port must be between 1 and 65535.\n")
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(Path(__file__).with_name("inspector.py")),
                "--server.address",
                "127.0.0.1",
                "--server.port",
                str(args.port),
                "--browser.gatherUsageStats",
                "false",
                "--server.headless",
                "true",
                "--",
                "--runs-dir",
                str(args.runs_dir.resolve()),
            ],
            check=False,
        )
    except KeyboardInterrupt:
        return
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
