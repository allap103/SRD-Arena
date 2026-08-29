"""Report executable-example coverage for concrete public callables."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ExclusionReason = Literal[
    "protocol",
    "abstract",
    "property_setter",
    "private_owner",
    "qt_bound_callable",
    "qt_widget_method",
    "qt_override",
]

QT_EVENT_OVERRIDES = frozenset(
    {
        "closeEvent",
        "eventFilter",
        "keyPressEvent",
        "leaveEvent",
        "mouseMoveEvent",
        "mousePressEvent",
        "mouseReleaseEvent",
        "paintEvent",
        "resizeEvent",
        "wheelEvent",
    }
)


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _annotation_names(node: ast.expr | None) -> set[str]:
    """Return simple and qualified names appearing in one annotation."""

    if node is None:
        return set()
    return {
        child.id if isinstance(child, ast.Name) else child.attr
        for child in ast.walk(node)
        if isinstance(child, (ast.Name, ast.Attribute))
    }


@dataclass(frozen=True)
class DoctestAuditEntry:
    """Identify one public callable and its executable-example status."""

    path: Path
    qualified_name: str
    line: int
    has_doctest: bool
    exclusion: ExclusionReason | None = None


@dataclass(frozen=True)
class DoctestAudit:
    """Summarize covered, missing, and policy-excluded public callables."""

    entries: tuple[DoctestAuditEntry, ...]

    @property
    def eligible(self) -> tuple[DoctestAuditEntry, ...]:
        """Return concrete callables to which the doctest policy applies.

        >>> included = DoctestAuditEntry(Path("demo.py"), "run", 1, True)
        >>> excluded = DoctestAuditEntry(
        ...     Path("demo.py"), "Port.read", 2, False, "protocol"
        ... )
        >>> audit = DoctestAudit((included, excluded))
        >>> tuple(entry.qualified_name for entry in audit.eligible)
        ('run',)
        """

        return tuple(entry for entry in self.entries if entry.exclusion is None)

    @property
    def missing(self) -> tuple[DoctestAuditEntry, ...]:
        """Return eligible callables without an executable example.

        >>> missing = DoctestAuditEntry(Path("demo.py"), "run", 1, False)
        >>> DoctestAudit((missing,)).missing == (missing,)
        True
        """

        return tuple(entry for entry in self.eligible if not entry.has_doctest)

    @property
    def coverage_percent(self) -> float:
        """Return doctested eligible callables as a percentage.

        >>> entries = (
        ...     DoctestAuditEntry(Path("demo.py"), "first", 1, True),
        ...     DoctestAuditEntry(Path("demo.py"), "second", 2, False),
        ... )
        >>> DoctestAudit(entries).coverage_percent
        50.0
        """

        eligible = self.eligible
        if not eligible:
            return 100.0
        covered = sum(entry.has_doctest for entry in eligible)
        return covered / len(eligible) * 100


class _CallableCollector(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: list[DoctestAuditEntry] = []
        self._classes: list[tuple[str, bool, bool, bool]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        base_names = {_decorator_name(base) for base in node.bases}
        inherited_private = any(item[2] for item in self._classes)
        inherited_qt = any(item[3] for item in self._classes)
        self._classes.append(
            (
                node.name,
                "Protocol" in base_names,
                inherited_private or node.name.startswith("_"),
                inherited_qt or any(name.startswith("Q") for name in base_names),
            )
        )
        for child in node.body:
            self.visit(child)
        self._classes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record_callable(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record_callable(node)

    def _record_callable(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if node.name.startswith("_"):
            return
        owners = tuple(name for name, *_flags in self._classes)
        exclusion = self._exclusion(node)
        self.entries.append(
            DoctestAuditEntry(
                path=self.path,
                qualified_name=".".join((*owners, node.name)),
                line=node.lineno,
                has_doctest=">>>" in (ast.get_docstring(node) or ""),
                exclusion=exclusion,
            )
        )

    def _exclusion(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> ExclusionReason | None:
        if any(is_protocol for _name, is_protocol, _private, _qt in self._classes):
            return "protocol"
        if any(is_private for _name, _protocol, is_private, _qt in self._classes):
            return "private_owner"
        decorator_names = {_decorator_name(item) for item in node.decorator_list}
        if "abstractmethod" in decorator_names:
            return "abstract"
        if "setter" in decorator_names:
            return "property_setter"
        if any(is_qt for _name, _protocol, _private, is_qt in self._classes):
            return "qt_widget_method"
        annotations = (
            *(argument.annotation for argument in node.args.posonlyargs),
            *(argument.annotation for argument in node.args.args),
            *(argument.annotation for argument in node.args.kwonlyargs),
            node.args.vararg.annotation if node.args.vararg is not None else None,
            node.args.kwarg.annotation if node.args.kwarg is not None else None,
            node.returns,
        )
        if (
            "frontends" in self.path.parts
            and "gui" in self.path.parts
            and any(
                name.startswith("Q")
                for annotation in annotations
                for name in _annotation_names(annotation)
            )
        ):
            return "qt_bound_callable"
        if (
            "frontends" in self.path.parts
            and "gui" in self.path.parts
            and node.name in QT_EVENT_OVERRIDES
        ):
            return "qt_override"
        return None


def audit_source_tree(root: Path) -> DoctestAudit:
    """Inspect every Python file below a source-package root.

    The returned paths are relative to ``root`` so reports remain stable across
    machines and checkout locations.
    """

    entries: list[DoctestAuditEntry] = []
    for path in sorted(root.rglob("*.py")):
        relative_path = path.relative_to(root)
        collector = _CallableCollector(relative_path)
        collector.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        entries.extend(collector.entries)
    return DoctestAudit(tuple(entries))


def render_audit(audit: DoctestAudit) -> str:
    """Render coverage and missing callables as a compact text report.

    >>> entry = DoctestAuditEntry(Path("demo.py"), "run", 3, False)
    >>> print(render_audit(DoctestAudit((entry,))))
    Doctest coverage: 0/1 (0.0%)
    Policy exclusions: 0
    Missing executable examples:
    - demo.py:3 run
    """

    eligible = audit.eligible
    covered = len(eligible) - len(audit.missing)
    excluded = len(audit.entries) - len(eligible)
    lines = [
        f"Doctest coverage: {covered}/{len(eligible)} ({audit.coverage_percent:.1f}%)",
        f"Policy exclusions: {excluded}",
    ]
    if audit.missing:
        lines.append("Missing executable examples:")
        lines.extend(
            f"- {entry.path}:{entry.line} {entry.qualified_name}"
            for entry in audit.missing
        )
    else:
        lines.append("No executable examples are missing.")
    return "\n".join(lines)


def main() -> int:
    """Run the doctest audit for the installed SRD Arena source package."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fail-under",
        type=float,
        help="Return a failing exit code below this coverage percentage.",
    )
    args = parser.parse_args()
    audit = audit_source_tree(Path(__file__).resolve().parents[1])
    print(render_audit(audit))
    if args.fail_under is not None and audit.coverage_percent < args.fail_under:
        return 1
    return 0
