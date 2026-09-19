"""Bounded tables and linear-time chart preparation for the local inspector."""

from collections import deque
from math import ceil
from pathlib import Path
from typing import Any

import streamlit as st


def selected_run() -> Path:
    """Read the run selector shared by every page in the entrypoint."""
    return Path(st.session_state["inspector_run"])


def paginated(rows: list[dict[str, Any]], *, key: str) -> None:
    """Send at most one page of exact table rows to the browser."""
    if not rows:
        st.info("No records in this selection.")
        return
    size = st.selectbox("Rows per page", [50, 100, 250], key=key + "_size")
    pages = ceil(len(rows) / size)
    page = st.number_input(
        "Table page", min_value=1, max_value=pages, value=1, key=f"{key}_{pages}_{size}"
    )
    start = (page - 1) * size
    st.caption(f"Rows {start + 1}-{min(start + size, len(rows))} of {len(rows):,}")
    st.dataframe(rows[start : start + size], hide_index=True)


def chart_data(
    rows: list[dict[str, Any]], fields: list[str], window: int, maximum: int = 1000
) -> dict[str, list[Any]]:
    """Smooth in linear time, then uniformly sample a bounded display payload."""
    available = [
        f for f in fields if any(isinstance(r.get(f), (int, float)) for r in rows)
    ]
    if not rows or not available:
        return {}
    if window < 1 or maximum < 2:
        raise ValueError(
            "Positive smoothing window and at least two display points required"
        )
    count = min(len(rows), maximum)
    indexes = sorted(
        {round(i * (len(rows) - 1) / max(1, count - 1)) for i in range(count)}
    )
    data: dict[str, list[Any]] = {"episode": [rows[i]["episode"] for i in indexes]}
    selected = set(indexes)
    for field in available:
        queue: deque[float | None] = deque()
        total, valid = 0.0, 0
        values = []
        for i, row in enumerate(rows):
            raw = row.get(field)
            value = float(raw) if isinstance(raw, (int, float)) else None
            queue.append(value)
            if value is not None:
                total += value
                valid += 1
            if len(queue) > window:
                removed = queue.popleft()
                if removed is not None:
                    total -= removed
                    valid -= 1
            if i in selected:
                values.append(total / valid if valid else None)
        data[field] = values
    return data


def chart(rows: list[dict[str, Any]], fields: list[str], window: int) -> None:
    """Render only the requested scalar series, capped at 1,000 points."""
    data = chart_data(rows, fields, window)
    if data:
        st.line_chart(data, x="episode", y=[k for k in data if k != "episode"])
