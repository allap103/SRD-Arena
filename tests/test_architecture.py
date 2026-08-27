from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "srd_arena"


@dataclass(frozen=True)
class DependencyRule:
    package: str
    forbidden: tuple[str, ...]


RULES = (
    DependencyRule(
        package="srd_arena.domain",
        forbidden=(
            "srd_arena.application",
            "srd_arena.content",
            "srd_arena.frontends",
            "srd_arena.infrastructure",
            "srd_arena.engine",
        ),
    ),
    DependencyRule(
        package="srd_arena.content",
        forbidden=(
            "srd_arena.application",
            "srd_arena.frontends",
            "srd_arena.infrastructure",
            "srd_arena.engine",
        ),
    ),
    DependencyRule(
        package="srd_arena.content.spells",
        forbidden=("srd_arena.content.creatures",),
    ),
    DependencyRule(
        package="srd_arena.engine",
        forbidden=(
            "srd_arena.application",
            "srd_arena.content",
            "srd_arena.frontends",
            "srd_arena.infrastructure",
        ),
    ),
    DependencyRule(
        package="srd_arena.application",
        forbidden=(
            "srd_arena.content",
            "srd_arena.frontends",
            "srd_arena.infrastructure",
        ),
    ),
    DependencyRule(
        package="srd_arena.frontends.shared",
        forbidden=(
            "srd_arena.content",
            "srd_arena.domain",
            "srd_arena.infrastructure",
            "srd_arena.engine",
        ),
    ),
    DependencyRule(
        package="srd_arena.infrastructure",
        forbidden=(
            "srd_arena.frontends",
            "srd_arena.engine",
        ),
    ),
    DependencyRule(
        package="srd_arena.frontends.qt",
        forbidden=(
            "srd_arena.content",
            "srd_arena.domain.encounters",
            "srd_arena.infrastructure",
            "srd_arena.engine",
        ),
    ),
    DependencyRule(
        package="srd_arena.frontends.headless",
        forbidden=(
            "srd_arena.content",
            "srd_arena.domain",
            "srd_arena.frontends.qt",
            "srd_arena.infrastructure",
            "srd_arena.engine",
        ),
    ),
    DependencyRule(
        package="srd_arena.domain.geometry",
        forbidden=(
            "srd_arena.domain.encounters",
            "srd_arena.domain.scene",
        ),
    ),
    DependencyRule(
        package="srd_arena.domain.equipment",
        forbidden=("srd_arena.domain.encounters",),
    ),
    DependencyRule(
        package="srd_arena.domain.creatures",
        forbidden=("srd_arena.domain.encounters",),
    ),
    DependencyRule(
        package="srd_arena.domain.spells",
        forbidden=("srd_arena.domain.encounters",),
    ),
)


def test_package_dependencies_follow_architecture() -> None:
    violations: list[str] = []

    for rule in RULES:
        package_dir = PACKAGE_ROOT.joinpath(*rule.package.split(".")[1:])
        for path in sorted(package_dir.rglob("*.py")):
            module = _module_name(path)
            for line, imported_module in _imports(path, module):
                forbidden = next(
                    (
                        prefix
                        for prefix in rule.forbidden
                        if _is_package_or_child(imported_module, prefix)
                    ),
                    None,
                )
                if forbidden is not None:
                    violations.append(
                        f"{path.relative_to(PACKAGE_ROOT.parent)}:{line}: "
                        f"{module} imports forbidden package {imported_module} "
                        f"({forbidden})"
                    )

    assert not violations, "Architecture dependency violations:\n" + "\n".join(
        violations
    )


def test_qt_domain_imports_are_limited_to_pure_geometry() -> None:
    violations: list[str] = []
    package_dir = PACKAGE_ROOT / "frontends" / "qt"
    for path in sorted(package_dir.rglob("*.py")):
        module = _module_name(path)
        for line, imported_module in _imports(path, module):
            if imported_module.startswith("srd_arena.domain") and not (
                imported_module == "srd_arena.domain.geometry"
                or imported_module.startswith("srd_arena.domain.geometry.")
            ):
                violations.append(
                    f"{path.relative_to(PACKAGE_ROOT.parent)}:{line} imports "
                    f"{imported_module}; Qt may import only pure domain geometry."
                )
    assert not violations, "\n".join(violations)


def test_relative_import_resolution() -> None:
    node = ast.ImportFrom(module="creatures", names=[], level=3)

    assert (
        _resolve_from_import(
            "srd_arena.domain.encounters.actions.attack_resolution",
            is_package=False,
            node=node,
        )
        == "srd_arena.domain.creatures"
    )


def test_cross_package_imports_are_absolute() -> None:
    violations: list[str] = []

    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        module = _module_name(path)
        source_package = _top_level_package(module)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level == 0:
                continue
            imported_module = _resolve_from_import(
                module,
                path.name == "__init__.py",
                node,
            )
            if _top_level_package(imported_module) != source_package:
                violations.append(
                    f"{path.relative_to(PACKAGE_ROOT.parent)}:{node.lineno}: "
                    f"{module} imports {imported_module} relatively"
                )

    assert not violations, (
        "Use absolute imports across top-level srd_arena package boundaries:\n"
        + "\n".join(violations)
    )


def test_content_is_grouped_by_game_concept() -> None:
    content_dir = PACKAGE_ROOT / "content"
    legacy_layer_packages = (
        "catalogs",
        "builders",
        "loaders",
        "normalization",
        "schemas",
        "translators",
    )

    assert not [
        name
        for name in legacy_layer_packages
        if list((content_dir / name).glob("*.py"))
    ], "Content belongs with its game concept, not in technical-layer packages."

    assert {
        "character_options",
        "common",
        "creatures",
        "encounters",
        "equipment",
        "capabilities",
        "spells",
    } <= {path.name for path in content_dir.iterdir() if path.is_dir()}

    assert not (content_dir / "classes").exists(), (
        "Class content belongs under content.character_options."
    )


def test_encounter_actions_have_no_legacy_peer_package() -> None:
    legacy_actions = PACKAGE_ROOT / "domain" / "actions"

    assert not list(legacy_actions.rglob("*.py")), (
        "Encounter-specific actions belong in srd_arena.domain.encounters.actions."
    )


def test_qt_interaction_planning_stays_independent_of_qt() -> None:
    encounter_ui = PACKAGE_ROOT / "frontends" / "qt" / "ui" / "encounter"
    violations: list[str] = []

    for name in ("action_menus.py", "movement.py", "targeting.py"):
        path = encounter_ui / name
        module = _module_name(path)
        for line, imported_module in _imports(path, module):
            if imported_module == "PySide6" or imported_module.startswith("PySide6."):
                violations.append(f"{path.name}:{line} imports {imported_module}")

    assert not violations, "Interaction planning must stay Qt-independent:\n" + "\n".join(
        violations
    )


def test_qt_window_imports_only_composition_widgets() -> None:
    path = PACKAGE_ROOT / "frontends" / "qt" / "app.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    qt_widget_imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "PySide6.QtWidgets"
        for alias in node.names
    }

    assert qt_widget_imports == {
        "QHBoxLayout",
        "QMainWindow",
        "QWidget",
    }


def test_initiative_rendering_has_one_view_owner() -> None:
    qt_root = PACKAGE_ROOT / "frontends" / "qt"
    non_owners = (
        qt_root / "app.py",
        qt_root / "ui" / "sidebar.py",
        qt_root / "ui" / "encounter" / "panel_renderer.py",
    )

    assert all(
        "initiative_layout" not in path.read_text(encoding="utf-8")
        for path in non_owners
    )


def test_domain_root_is_namespace_only() -> None:
    violations: list[str] = []
    search_roots = (PACKAGE_ROOT, Path(__file__).parent)
    domain_init = ast.parse(
        (PACKAGE_ROOT / "domain" / "__init__.py").read_text(encoding="utf-8")
    )

    assert (
        len(domain_init.body) == 1
        and isinstance(domain_init.body[0], ast.Expr)
        and isinstance(domain_init.body[0].value, ast.Constant)
        and isinstance(domain_init.body[0].value.value, str)
    ), (
        "srd_arena.domain.__init__ must remain a descriptive namespace without re-exports."
    )

    for search_root in search_roots:
        for path in sorted(search_root.rglob("*.py")):
            module = (
                _module_name(path)
                if path.is_relative_to(PACKAGE_ROOT.parent)
                else f"tests.{path.relative_to(search_root).with_suffix('').as_posix().replace('/', '.')}"
            )
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom):
                    continue
                imported_module = _resolve_from_import(
                    module,
                    path.name == "__init__.py",
                    node,
                )
                if imported_module == "srd_arena.domain":
                    imported_names = ", ".join(alias.name for alias in node.names)
                    violations.append(
                        f"{path.relative_to(PACKAGE_ROOT.parent.parent)}:{node.lineno}: "
                        f"import {imported_names} from its owning domain subpackage"
                    )

    assert not violations, "Domain-root imports hide concept ownership:\n" + "\n".join(
        violations
    )


def test_package_and_engine_roots_do_not_reexport_engine_types() -> None:
    assert not (PACKAGE_ROOT / "runtime").exists()
    for path in (
        PACKAGE_ROOT / "__init__.py",
        PACKAGE_ROOT / "engine" / "__init__.py",
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assert (
            len(tree.body) == 1
            and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, ast.Constant)
            and isinstance(tree.body[0].value.value, str)
        ), f"{path.relative_to(PACKAGE_ROOT.parent)} must remain namespace-only."


def _imports(path: Path, module: str) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve_from_import(module, path.name == "__init__.py", node)
            if resolved:
                imports.append((node.lineno, resolved))
    return imports


def _resolve_from_import(
    module: str,
    is_package: bool,
    node: ast.ImportFrom,
) -> str:
    if node.level == 0:
        return node.module or ""

    parts = module.split(".")
    package_parts = parts if is_package else parts[:-1]
    ascend = node.level - 1
    if ascend > len(package_parts):
        return node.module or ""
    base = package_parts[: len(package_parts) - ascend]
    if node.module:
        base.extend(node.module.split("."))
    return ".".join(base)


def _module_name(path: Path) -> str:
    relative = path.relative_to(PACKAGE_ROOT.parent).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _top_level_package(module: str) -> str:
    parts = module.split(".")
    return parts[1] if len(parts) > 1 else ""


def _is_package_or_child(module: str, package: str) -> bool:
    return module == package or module.startswith(f"{package}.")
