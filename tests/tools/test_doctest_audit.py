from pathlib import Path

from srd_arena.tools.doctest_audit import audit_source_tree, render_audit


def test_audit_distinguishes_examples_from_policy_exclusions(tmp_path: Path) -> None:
    gui_package = tmp_path / "frontends" / "gui"
    gui_package.mkdir(parents=True)
    (gui_package / "sample.py").write_text(
        '''
from typing import Protocol

def covered():
    """Show behavior.

    >>> covered()
    1
    """
    return 1

def missing():
    """Lack an executable example."""

def paint_scene(painter: QPainter):
    """Require a live Qt painter."""

class Port(Protocol):
    def read(self): ...

class Widget:
    def paintEvent(self, event):
        pass

class Panel(QWidget):
    def refresh(self):
        pass
''',
        encoding="utf-8",
    )

    audit = audit_source_tree(tmp_path)

    assert audit.coverage_percent == 50.0
    assert [entry.qualified_name for entry in audit.missing] == ["missing"]
    assert {entry.exclusion for entry in audit.entries} == {
        None,
        "protocol",
        "qt_bound_callable",
        "qt_widget_method",
        "qt_override",
    }


def test_render_audit_lists_stable_relative_locations(tmp_path: Path) -> None:
    (tmp_path / "sample.py").write_text(
        'def missing():\n    """No example yet."""\n',
        encoding="utf-8",
    )

    report = render_audit(audit_source_tree(tmp_path))

    assert "Doctest coverage: 0/1 (0.0%)" in report
    assert "sample.py:1 missing" in report
