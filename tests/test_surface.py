"""What each module declares is what crosses a module boundary.

The package root exports ``__version__`` and nothing else, on purpose: this is a
pipeline with a command line, not a library, and its own documentation site and
tests import from the modules. That makes a module's ``__all__`` the only
statement anywhere of what may be imported from it — and the two modules every
other one depends on made no statement at all.

``types`` holds ``Settings``, which every stage takes and ``run(Settings())``
needs; ``selection`` holds ``run_selection`` and ``SelectionResult``, which
``execution`` and ``pipeline`` both import. Neither carried an ``__all__``.
Thirty-seven names imported across a module boundary in ``src``, ``tests`` and
``docs`` were names their owner did not declare, every one from those two.

So the checks here are the ones a version-only root calls for. Each module
declares; its declaration holds every public name its source defines; no name
has two owners; the root is pinned, with its reason, so widening it is a
decision rather than drift; and — the consumer-side rule, which is the one the
defect needed — **every name imported from another module of this package is
one that module declares**.

Definitions and imports are both read with :mod:`ast` rather than from the
imported modules. ``FloatArray`` and ``PERIODS_PER_YEAR`` are a type alias and
a bare float, which carry no ``__module__`` an attribute sweep could attribute
to ``types``.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from collections import Counter
from pathlib import Path
from types import ModuleType

import paper_to_live

REPOSITORY = Path(__file__).resolve().parent.parent
SOURCE = REPOSITORY / "src" / "paper_to_live"

#: Modules that are not part of the importable surface. ``__main__`` exists so
#: that ``python -m paper_to_live`` runs the command line.
NOT_SURFACE = frozenset({"__main__"})

#: The root's whole surface. A pipeline with a command line rather than a
#: library: callers import from the module that owns a name, and the root adding
#: re-exports would be a design change, made here on purpose or not at all.
ROOT = frozenset({"__version__"})

#: Where cross-module imports are looked for. ``docs`` is included because the
#: site generator is the one consumer outside the package that is not a test.
CONSUMERS = ("src", "tests", "docs")

#: Source written to exercise :func:`public_names_in`, not to be a module.
PROBE_SOURCE = '''
"""A docstring, which defines nothing."""

from __future__ import annotations

import math                      # an import is not a definition
from typing import TypeAlias

ALIAS: TypeAlias = float         # an annotated alias: no __module__ to sweep by
RATE = 252.0                     # a bare float: likewise
PAIR_ONE = PAIR_TWO = 3          # one statement, two names
_PRIVATE = 4                     # underscore: not public
__all__ = ["RATE"]               # the declaration is never a definition


def public_function() -> None:
    """A function."""
    local_name = 5               # a name in a body is not top level


async def public_coroutine() -> None:
    """An async function, which this package has none of."""


class PublicClass:
    """A class."""

    attribute = 6                # a class attribute is not a module name
'''

#: Source written to exercise :func:`package_imports_in`.
IMPORT_PROBE = """
from __future__ import annotations

import numpy as np
from paper_to_live.types import Settings
from paper_to_live import __version__
from .selection import run_selection, SelectionResult as Result
from . import report
from .. import elsewhere
"""


def public_names_in(source: str) -> frozenset[str]:
    """The public top-level names a piece of module source defines."""
    found: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
        else:
            continue
        found.update(name for name in names if not name.startswith("_"))
    return frozenset(found)


def package_imports_in(source: str, *, inside: bool) -> list[tuple[str, str]]:
    """Every ``(module, name)`` a piece of source imports from this package.

    ``inside`` says whether the source is a module of the package, which is the
    only place a one-dot relative import refers to it. A bare ``from . import``
    names a module, not a declared name, and a two-dot import leaves the
    package, so neither is returned.
    """
    found: list[tuple[str, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if node.level == 1 and inside:
            module = node.module
        elif node.level == 0 and node.module.startswith("paper_to_live."):
            module = node.module.removeprefix("paper_to_live.")
        else:
            continue
        found.extend((module, alias.name) for alias in node.names)
    return found


def submodules() -> dict[str, ModuleType]:
    """Every importable submodule of the package, bar the entry point."""
    return {
        info.name: importlib.import_module(f"paper_to_live.{info.name}")
        for info in pkgutil.iter_modules(paper_to_live.__path__)
        if info.name not in NOT_SURFACE
    }


def declared() -> dict[str, frozenset[str]]:
    """Each module's own declaration of what it makes public."""
    return {
        name: frozenset(module.__all__)
        for name, module in submodules().items()
        if getattr(module, "__all__", None) is not None
    }


def consumer_files() -> list[Path]:
    """Every Python file that could import from the package."""
    return sorted(
        path
        for directory in CONSUMERS
        for path in (REPOSITORY / directory).rglob("*.py")
        if ".venv" not in path.parts
    )


def test_every_module_declares_something() -> None:
    """No module is exempt from the checks below by declaring nothing.

    Two modules failed this: ``types`` and ``selection``.
    """
    silent = sorted(
        name
        for name, module in submodules().items()
        if getattr(module, "__all__", None) is None
    )
    assert not silent, f"modules carrying no __all__: {silent}"


def test_a_module_declares_every_public_name_it_defines() -> None:
    """``__all__`` is not a curated subset of what the module defines."""
    undeclared: dict[str, list[str]] = {}
    for module, names in declared().items():
        source = (SOURCE / f"{module}.py").read_text(encoding="utf-8")
        missing = sorted(public_names_in(source) - names)
        if missing:
            undeclared[module] = missing
    assert not undeclared, f"defined and absent from the module's __all__: {undeclared}"


def test_every_declared_name_exists() -> None:
    """A declaration lists only names the module has."""
    phantom = {
        module: sorted(
            name for name in names if not hasattr(submodules()[module], name)
        )
        for module, names in declared().items()
    }
    phantom = {module: names for module, names in phantom.items() if names}
    assert not phantom, f"declared but not defined: {phantom}"


def test_no_name_has_two_owners() -> None:
    """One name, one module that declares it."""
    owners = Counter(name for names in declared().values() for name in names)
    shared = sorted(name for name, count in owners.items() if count > 1)
    assert not shared, f"declared public by more than one module: {shared}"


def test_the_root_is_exactly_the_version() -> None:
    """The root's surface is the one decided above, and nothing it drifted to."""
    assert frozenset(paper_to_live.__all__) == ROOT
    assert all(hasattr(paper_to_live, name) for name in ROOT)


def test_every_cross_module_import_names_a_declared_name() -> None:
    """The defect, checked where it shows: at the import that relies on it.

    With a version-only root, ``from paper_to_live.types import Settings`` is
    the way in, and it relied on nothing — ``types`` had not said ``Settings``
    was for importing. Thirty-seven imported names failed this.
    """
    surfaces = declared()
    undeclared: dict[str, list[str]] = {}
    for path in consumer_files():
        inside = SOURCE in path.parents
        for module, name in package_imports_in(
            path.read_text(encoding="utf-8"), inside=inside
        ):
            if name not in surfaces.get(module, frozenset()):
                where = str(path.relative_to(REPOSITORY))
                undeclared.setdefault(f"{module}.{name}", []).append(where)
    assert not undeclared, (
        f"imported from a module that does not declare it: {undeclared}"
    )


def test_the_probes_read_a_surface_worth_checking() -> None:
    """The checks above are not passing because they found nothing.

    Every assertion here is satisfied by an empty set, so a probe that stops
    importing modules or stops reading imports turns the file green. The bounds
    are loose and say nothing about which modules declare — that is what the
    checks above are for, and a probe that failed for their reason would
    report one defect twice.
    """
    modules = declared()
    assert len(modules) >= 5, f"only {len(modules)} modules declared an __all__"
    imports = [
        pair
        for path in consumer_files()
        for pair in package_imports_in(
            path.read_text(encoding="utf-8"), inside=SOURCE in path.parents
        )
    ]
    assert len(imports) >= 60, f"only {len(imports)} cross-module imports were read"
    assert ("types", "Settings") in imports


def test_the_definition_probe_reads_each_kind_and_skips_each_non_definition() -> None:
    """The definition probe, against source written for it."""
    found = public_names_in(PROBE_SOURCE)
    assert found == {
        "ALIAS",
        "RATE",
        "PAIR_ONE",
        "PAIR_TWO",
        "public_function",
        "public_coroutine",
        "PublicClass",
    }, f"the probe read {sorted(found)}"
    for absent in (
        "math",
        "TypeAlias",
        "_PRIVATE",
        "__all__",
        "local_name",
        "attribute",
    ):
        assert absent not in found, f"the probe counted {absent!r} as a definition"


def test_the_import_probe_reads_each_form_and_skips_each_non_import() -> None:
    """The import probe, against source written for it.

    An aliased import is checked under the name the owner exports, not the local
    alias; ``from paper_to_live import __version__`` is the root, which the
    check above covers; ``from . import report`` names a module; and outside
    the package a one-dot import does not refer to it at all.
    """
    assert package_imports_in(IMPORT_PROBE, inside=True) == [
        ("types", "Settings"),
        ("selection", "run_selection"),
        ("selection", "SelectionResult"),
    ]
    assert package_imports_in(IMPORT_PROBE, inside=False) == [("types", "Settings")]
