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
            "srd_arena.content",
            "srd_arena.frontends",
            "srd_arena.infrastructure",
            "srd_arena.runtime",
        ),
    ),
    DependencyRule(
        package="srd_arena.content",
        forbidden=(
            "srd_arena.frontends",
            "srd_arena.runtime",
        ),
    ),
    DependencyRule(
        package="srd_arena.runtime",
        forbidden=(
            "srd_arena.frontends.cli",
            "srd_arena.frontends.qt",
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


def test_relative_import_resolution() -> None:
    node = ast.ImportFrom(module="creatures", names=[], level=2)

    assert (
        _resolve_from_import(
            "srd_arena.domain.actions.attack_resolution",
            is_package=False,
            node=node,
        )
        == "srd_arena.domain.creatures"
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


def test_encounter_state_has_no_imported_method_aliases() -> None:
    encounter_path = (
        PACKAGE_ROOT / "domain" / "encounters" / "encounter.py"
    )
    tree = ast.parse(encounter_path.read_text(encoding="utf-8"))
    encounter_state = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "EncounterState"
    )
    aliases = [
        target.id
        for statement in encounter_state.body
        if isinstance(statement, ast.Assign)
        and (
            (
                isinstance(statement.value, ast.Name)
                and statement.value.id.startswith("_")
            )
            or (
                isinstance(statement.value, ast.Call)
                and isinstance(statement.value.func, ast.Name)
                and statement.value.func.id == "staticmethod"
                and statement.value.args
                and isinstance(statement.value.args[0], ast.Name)
                and statement.value.args[0].id.startswith("_")
            )
        )
        for target in statement.targets
        if isinstance(target, ast.Name)
    ]

    assert aliases == []


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


def _is_package_or_child(module: str, package: str) -> bool:
    return module == package or module.startswith(f"{package}.")
