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
            "srd_arena.engine",
            "srd_arena.encounters",
        ),
    ),
    DependencyRule(
        package="srd_arena.content",
        forbidden=(
            "srd_arena.frontends",
            "srd_arena.infrastructure",
            "srd_arena.engine",
            "srd_arena.encounters",
        ),
    ),
    DependencyRule(
        package="srd_arena.content.spells",
        forbidden=("srd_arena.content.creatures",),
    ),
    DependencyRule(
        package="srd_arena.engine",
        forbidden=(
            "srd_arena.content",
            "srd_arena.frontends",
            "srd_arena.infrastructure",
            "srd_arena.encounters",
        ),
    ),
    DependencyRule(
        package="srd_arena.frontends.gui.presentation",
        forbidden=(
            "srd_arena.domain",
            "srd_arena.infrastructure",
        ),
    ),
    DependencyRule(
        package="srd_arena.frontends.gui",
        forbidden=(
            "srd_arena.domain.encounters",
            "srd_arena.infrastructure",
        ),
    ),
    DependencyRule(
        package="srd_arena.frontends.headless",
        forbidden=(
            "srd_arena.domain",
            "srd_arena.frontends.gui",
            "srd_arena.infrastructure",
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


def test_gui_domain_imports_are_limited_to_pure_geometry() -> None:
    violations: list[str] = []
    package_dir = PACKAGE_ROOT / "frontends" / "gui"
    for path in sorted(package_dir.rglob("*.py")):
        module = _module_name(path)
        for line, imported_module in _imports(path, module):
            if imported_module.startswith("srd_arena.domain") and not (
                imported_module == "srd_arena.domain.geometry"
                or imported_module.startswith("srd_arena.domain.geometry.")
            ):
                violations.append(
                    f"{path.relative_to(PACKAGE_ROOT.parent)}:{line} imports "
                    f"{imported_module}; GUI may import only pure domain geometry."
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
        source_package = _import_boundary(module)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level == 0:
                continue
            imported_module = _resolve_from_import(
                module,
                path.name == "__init__.py",
                node,
            )
            if _import_boundary(imported_module) != source_package:
                violations.append(
                    f"{path.relative_to(PACKAGE_ROOT.parent)}:{node.lineno}: "
                    f"{module} imports {imported_module} relatively"
                )

    assert not violations, (
        "Use absolute imports across top-level and domain-concept boundaries:\n"
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


def test_spell_building_does_not_import_its_package_facade() -> None:
    """Keep spell construction below the public package entry point."""

    violations: list[str] = []
    building_dir = PACKAGE_ROOT / "content" / "spells" / "building"
    for path in sorted(building_dir.rglob("*.py")):
        module = _module_name(path)
        for line, imported_module in _imports(path, module):
            if imported_module == "srd_arena.content.spells":
                violations.append(f"{path.name}:{line} imports the spell facade")

    assert not violations, (
        "Spell-building modules must import concrete sibling modules directly; "
        "the package facade imports the builder and would create a cycle:\n"
        + "\n".join(violations)
    )


def test_encounter_runtime_import_graph_is_acyclic() -> None:
    """Reject executable dependency cycles hidden by deferred local imports."""

    encounter_dir = PACKAGE_ROOT / "domain" / "encounters"
    modules = {_module_name(path): path for path in sorted(encounter_dir.rglob("*.py"))}
    dependencies: dict[str, set[str]] = {module: set() for module in modules}
    for module, path in modules.items():
        for _line, imported_module in _runtime_imports(path, module):
            candidates = (
                candidate
                for candidate in modules
                if imported_module == candidate
                or imported_module.startswith(f"{candidate}.")
            )
            dependency = max(candidates, key=len, default=None)
            if dependency is not None and dependency != module:
                dependencies[module].add(dependency)

    cycle = _dependency_cycle(dependencies)

    assert cycle is None, "Runtime import cycle: " + " -> ".join(cycle or ())


def test_rule_queries_do_not_depend_on_the_encounter_aggregate() -> None:
    """Keep reusable typed rule queries behind their focused data contexts."""

    query_dir = PACKAGE_ROOT / "domain" / "encounters" / "rule_queries"
    aggregate_module = "srd_arena.domain.encounters.encounter"
    violations = [
        f"{path.name}:{line} imports {aggregate_module}"
        for path in sorted(query_dir.glob("*.py"))
        for line, imported_module in _imports(path, _module_name(path))
        if imported_module == aggregate_module
    ]

    assert not violations, "\n".join(violations)


def test_gui_interaction_planning_stays_independent_of_pyside6() -> None:
    encounter_ui = PACKAGE_ROOT / "frontends" / "gui" / "ui" / "encounter"
    violations: list[str] = []

    for name in ("action_menus.py", "movement.py", "targeting.py"):
        path = encounter_ui / name
        module = _module_name(path)
        for line, imported_module in _imports(path, module):
            if imported_module == "PySide6" or imported_module.startswith("PySide6."):
                violations.append(f"{path.name}:{line} imports {imported_module}")

    assert not violations, (
        "Interaction planning must stay Qt-independent:\n" + "\n".join(violations)
    )


def test_gui_presenter_stays_independent_of_pyside6() -> None:
    path = PACKAGE_ROOT / "frontends" / "gui" / "presenter.py"
    module = _module_name(path)

    assert not [
        imported_module
        for _line, imported_module in _imports(path, module)
        if imported_module == "PySide6" or imported_module.startswith("PySide6.")
    ]


def test_driving_adapters_use_only_public_engine_and_encounter_content_apis() -> None:
    violations: list[str] = []

    paths = [
        *sorted((PACKAGE_ROOT / "frontends").rglob("*.py")),
        PACKAGE_ROOT / "main.py",
    ]
    for path in paths:
        module = _module_name(path)
        for line, imported_module in _imports(path, module):
            private_engine = (
                imported_module.startswith("srd_arena.engine.")
                and imported_module != "srd_arena.engine.api"
            )
            private_encounter_content = (
                imported_module == "srd_arena.content"
                or imported_module.startswith("srd_arena.content.")
            ) and imported_module != "srd_arena.content.encounters"
            if private_engine or private_encounter_content:
                violations.append(
                    f"{path.relative_to(PACKAGE_ROOT.parent)}:{line} imports "
                    f"{imported_module}"
                )

    assert not violations, (
        "Driving adapters must use public engine and encounter-content APIs:\n"
        + "\n".join(violations)
    )


def test_engine_api_exports_only_engine_owned_contracts() -> None:
    from srd_arena.engine import api

    assert api.__all__
    assert len(api.__all__) == len(set(api.__all__))
    assert all(hasattr(api, name) for name in api.__all__)
    assert "Session" in api.__all__
    assert not {"SessionRead", "EncounterState"} & set(api.__all__)
    assert all(
        exported.__doc__
        for name in api.__all__
        if isinstance(exported := getattr(api, name), type)
    )


def test_domain_models_are_imported_from_their_owning_package() -> None:
    violations: list[str] = []
    search_roots = (PACKAGE_ROOT, Path(__file__).parent)

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


def test_package_roots_remain_descriptive_namespaces() -> None:
    """Prevent convenience re-exports from hiding contract ownership."""

    for path in (
        PACKAGE_ROOT / "__init__.py",
        PACKAGE_ROOT / "domain" / "__init__.py",
        PACKAGE_ROOT / "engine" / "__init__.py",
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assert (
            len(tree.body) == 1
            and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, ast.Constant)
            and isinstance(tree.body[0].value.value, str)
        ), f"{path.relative_to(PACKAGE_ROOT.parent)} must remain namespace-only."


def test_obsolete_encounter_service_packages_stay_removed() -> None:
    """Keep encounter definitions and loading beside related concepts."""

    assert not list((PACKAGE_ROOT / "encounters").glob("*.py"))
    assert not list((PACKAGE_ROOT / "infrastructure").glob("*.py"))


def test_removed_stateless_service_facades_stay_removed() -> None:
    """Keep rule and lifecycle dependencies visible as focused functions."""

    removed_facades = (
        PACKAGE_ROOT / "domain" / "encounters" / "rules.py",
        PACKAGE_ROOT / "domain" / "encounters" / "reactions.py",
        PACKAGE_ROOT
        / "domain"
        / "encounters"
        / "reaction_runtime"
        / "opportunity_attacks.py",
    )

    assert not [path for path in removed_facades if path.exists()]


def test_engine_projection_helpers_do_not_import_concrete_session() -> None:
    boundary_modules = (
        "action_observations.py",
        "interactions.py",
        "observations.py",
    )
    violations: list[str] = []

    for name in boundary_modules:
        path = PACKAGE_ROOT / "engine" / name
        module = _module_name(path)
        for line, imported_module in _imports(path, module):
            if imported_module == "srd_arena.engine.session":
                violations.append(f"{name}:{line} imports concrete Session")

    assert not violations, (
        "Engine projection helpers must use the GameEngine protocol:\n"
        + "\n".join(violations)
    )


def test_public_engine_api_exposes_the_session_facade() -> None:
    from srd_arena.engine import api

    assert {
        "observe",
        "execute",
        "advance_one_automatic_action",
        "advance_until_input_required",
        "reset",
    } <= set(vars(api.Session))


def test_engine_does_not_define_presentation_views() -> None:
    violations: list[str] = []

    for path in sorted((PACKAGE_ROOT / "engine").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.endswith("View"):
                violations.append(f"{path.name}:{node.lineno}: {node.name}")

    assert not violations, (
        "Engine observations are the client read model; GUI presentation "
        "views must stay in the frontend:\n" + "\n".join(violations)
    )


def test_engine_action_options_do_not_expose_domain_action_payloads() -> None:
    path = PACKAGE_ROOT / "engine" / "queries.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    action_option = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ActionOption"
    )
    fields = {
        node.target.id
        for node in action_option.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }

    assert "action" not in fields
    assert "value" not in fields


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


class _RuntimeImportCollector(ast.NodeVisitor):
    """Collect imports while omitting branches used only for static typing."""

    def __init__(self, module: str, is_package: bool) -> None:
        self.module = module
        self.is_package = is_package
        self.imports: list[tuple[int, str]] = []

    def visit_If(self, node: ast.If) -> None:
        if _is_type_checking_guard(node.test):
            for statement in node.orelse:
                self.visit(statement)
            return
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        self.imports.extend((node.lineno, alias.name) for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        resolved = _resolve_from_import(self.module, self.is_package, node)
        if resolved:
            self.imports.append((node.lineno, resolved))


def _runtime_imports(path: Path, module: str) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    collector = _RuntimeImportCollector(module, path.name == "__init__.py")
    collector.visit(tree)
    return collector.imports


def _is_type_checking_guard(node: ast.expr) -> bool:
    return (isinstance(node, ast.Name) and node.id == "TYPE_CHECKING") or (
        isinstance(node, ast.Attribute) and node.attr == "TYPE_CHECKING"
    )


def _dependency_cycle(
    dependencies: dict[str, set[str]],
) -> tuple[str, ...] | None:
    visited: set[str] = set()
    active: list[str] = []
    active_indices: dict[str, int] = {}

    def visit(module: str) -> tuple[str, ...] | None:
        if module in active_indices:
            start = active_indices[module]
            return (*active[start:], module)
        if module in visited:
            return None
        active_indices[module] = len(active)
        active.append(module)
        for dependency in sorted(dependencies[module]):
            if cycle := visit(dependency):
                return cycle
        active.pop()
        active_indices.pop(module)
        visited.add(module)
        return None

    for module in sorted(dependencies):
        if cycle := visit(module):
            return cycle
    return None


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


def _import_boundary(module: str) -> str:
    """Identify the package boundary across which imports must be absolute."""

    parts = module.split(".")
    if len(parts) >= 3 and parts[1] == "domain":
        return ".".join(parts[:3])
    return ".".join(parts[:2])


def _is_package_or_child(module: str, package: str) -> bool:
    return module == package or module.startswith(f"{package}.")
