from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

GAME_PACKAGE = Path(__file__).parents[1] / "app" / "game"


@dataclass(frozen=True)
class DependencyRule:
    package: str
    forbidden: tuple[str, ...]


RULES = (
    DependencyRule(
        package="game.domain",
        forbidden=(
            "game.content",
            "game.frontends",
            "game.infrastructure",
            "game.runtime",
        ),
    ),
    DependencyRule(
        package="game.content",
        forbidden=(
            "game.frontends",
            "game.runtime",
        ),
    ),
    DependencyRule(
        package="game.runtime",
        forbidden=(
            "game.frontends.cli",
            "game.frontends.qt",
        ),
    ),
)


def test_package_dependencies_follow_architecture() -> None:
    violations: list[str] = []

    for rule in RULES:
        package_dir = GAME_PACKAGE.joinpath(*rule.package.split(".")[1:])
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
                        f"{path.relative_to(GAME_PACKAGE.parent)}:{line}: "
                        f"{module} imports forbidden package {imported_module} "
                        f"({forbidden})"
                    )

    assert not violations, "Architecture dependency violations:\n" + "\n".join(violations)


def test_relative_import_resolution() -> None:
    node = ast.ImportFrom(module="creature", names=[], level=2)

    assert (
        _resolve_from_import(
            "game.domain.combat.attacks",
            is_package=False,
            node=node,
        )
        == "game.domain.creature"
    )


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
    relative = path.relative_to(GAME_PACKAGE.parent).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _is_package_or_child(module: str, package: str) -> bool:
    return module == package or module.startswith(f"{package}.")
