"""Multipage local inspector with shared run selection and explicit refresh."""

import argparse
from pathlib import Path

import streamlit as st

from srd_arena.training.inspection_store import clear_caches
from srd_arena.training.inspector_views import combat_aggregate


@st.cache_data(ttl=30, max_entries=8, show_spinner=False)
def discover_runs(root: str) -> list[str]:
    """Avoid rescanning every trace directory on each widget interaction."""
    return sorted({str(p.parent.resolve()) for p in Path(root).rglob("metrics.jsonl")})


def main() -> None:
    """Run only the selected page; keep dataset widgets stable across navigation."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    args, _ = parser.parse_known_args()
    root = args.runs_dir.resolve()
    st.set_page_config(page_title="Arena training inspector", layout="wide")
    with st.sidebar:
        st.header("Arena inspector")
        if st.button("Refresh records"):
            discover_runs.clear()
            clear_caches()
            combat_aggregate.cache_clear()
        runs = discover_runs(str(root))
        if not runs:
            st.info("No training records found.")
            return
        if st.session_state.get("inspector_run") not in runs:
            st.session_state["inspector_run"] = runs[0]
        st.selectbox(
            "Run",
            runs,
            format_func=lambda p: str(Path(p).relative_to(root)),
            key="inspector_run",
        )
        st.caption(
            "Spectator diagnostics. Only the selected page loads and renders its reports."
        )
    st.session_state["inspector_root"] = str(root)
    pages = [
        st.Page("inspector_pages/learning.py", title="Learning curves", default=True),
        st.Page("inspector_pages/table.py", title="Episode table"),
        st.Page("inspector_pages/combat.py", title="Combat totals"),
        st.Page("inspector_pages/episodes.py", title="Episode details"),
        st.Page("inspector_pages/comparisons.py", title="Comparisons"),
        st.Page("inspector_pages/configuration.py", title="Configuration"),
    ]
    try:
        st.navigation(pages).run()
    except (ValueError, OSError, KeyError) as exc:
        st.error(f"Cannot read this report: {exc}")


if __name__ == "__main__":
    main()
