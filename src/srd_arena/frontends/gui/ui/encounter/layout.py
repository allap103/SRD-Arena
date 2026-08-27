from __future__ import annotations

from PySide6.QtWidgets import QLayout


def clear_layout(layout: QLayout) -> None:
    """Remove every widget and nested layout from a Qt layout."""

    while layout.count():
        item = layout.takeAt(0)
        if item is None:
            continue
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            clear_layout(child_layout)
