from __future__ import annotations


def clear_layout(layout) -> None:
    """Remove every widget and nested layout from a Qt layout."""

    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            clear_layout(child_layout)
