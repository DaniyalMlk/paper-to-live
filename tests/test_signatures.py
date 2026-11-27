"""A caller who can call something can name what it takes and returns.

``tests/test_surface.py`` asks whether every import across a module boundary
names something its owner declares. It cannot see a type nobody imports: a
private class in a public signature, or a copy of an alias that only its own
module carries. The sibling libraries each turned up one of these —
``moneyness.adaptive_quad`` took a ``budget: _Budget | None`` that only a
private import could fill, and two of ``holdout``'s public classes declared
their fields with a copy of ``IndexArray`` that the root did not bind.

The root here exports only ``__version__``, so a type is nameable when **some
module of the package declares it**. For every declared function, every public
method and property of every declared class, and every field of a declared
class, each package class the annotations mention and each package alias they
are written in must be declared somewhere, compared by identity.

This package is also the only one in the set whose public signatures take
**other packages' types**: :func:`paper_to_live.funding.screen_for` takes
``tenor`` instruments and :func:`~paper_to_live.funding.build_curve` returns a
``tenor`` curve. A caller of those needs the library's type too, and the place
to get it is the library's own root. So a class or alias from one of the four
libraries this package depends on must be bound at that library's root. The
libraries are built from their main branches in CI, so this check is where a
library dropping or renaming a root export would first show here.

Aliases are read from source, because :func:`typing.get_type_hints` expands
``FloatArray`` into ``numpy.ndarray[...]`` before anything can look at it; and
each name an annotation spells is resolved in the globals of the module that
wrote it, rather than matched by name.
"""

from __future__ import annotations

import ast
import importlib
import importlib.metadata
import inspect
import pkgutil
import re
import sys
import textwrap
import typing
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from types import ModuleType

import paper_to_live

PACKAGE = Path(paper_to_live.__file__).resolve().parent
PREFIX = "paper_to_live."

#: The command line is an entry point wired to ``argparse``, not to callers,
#: and ``__main__`` exists so that ``python -m paper_to_live`` runs it.
NOT_SURFACE = frozenset({"cli", "__main__"})

#: The import names of the libraries this package depends on. Pinned against
#: the installed metadata below, so a new dependency cannot escape the check.
LIBRARIES = ("holdout", "shortfall", "slippage", "tenor")

#: Subscripted names that make a module-level assignment a type expression.
TYPE_CONSTRUCTORS = frozenset(
    {
        "Annotated",
        "Callable",
        "Literal",
        "Mapping",
        "NDArray",
        "Optional",
        "Sequence",
        "Union",
        "dict",
        "frozenset",
        "list",
        "set",
        "tuple",
        "type",
    }
)


# ---------------------------------------------------------------------------
# The probe.


def home_of(module_name: str) -> str | None:
    """Which checked package a module belongs to, if any."""
    top = module_name.split(".")[0]
    if top == "paper_to_live" or top in LIBRARIES:
        return top
    return None


def classes_in(hint: object) -> set[type]:
    """Every class from a checked package mentioned anywhere inside a hint.

    ``typing.get_args(Callable[[A], B])`` is ``([A], B)``: a callback's
    parameters arrive as a plain list, which a walk recursing only through
    ``get_args`` would never enter.
    """
    if isinstance(hint, list | tuple):
        return set().union(*(classes_in(item) for item in hint))
    found: set[type] = set()
    for candidate in (hint, typing.get_origin(hint)):
        if isinstance(candidate, type) and home_of(candidate.__module__):
            found.add(candidate)
    for argument in typing.get_args(hint):
        found |= classes_in(argument)
    return found


def _subscripted_name(node: ast.expr) -> str | None:
    """``list`` for ``list[...]``, ``NDArray`` for ``npt.NDArray[...]``."""
    if not isinstance(node, ast.Subscript):
        return None
    value = node.value
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        return value.attr
    return None


def _is_type_expression(node: ast.expr) -> bool:
    if _subscripted_name(node) in TYPE_CONSTRUCTORS:
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        # ``int | str`` and ``float | None`` are types; ``1 | 2`` is a number.
        return all(_is_type_operand(side) for side in (node.left, node.right))
    return False


def _is_type_operand(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return node.value is None
    return isinstance(node, ast.Name | ast.Attribute) or _is_type_expression(node)


def aliases_in(source: str) -> frozenset[str]:
    """The module-level names a source file binds to a type expression."""
    found: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if "TypeAlias" in ast.unparse(node.annotation):
                found.add(node.target.id)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and _is_type_expression(node.value):
                found.add(target.id)
        elif type(node).__name__ == "TypeAlias":  # ``type X = ...``, 3.12 and later
            found.add(node.name.id)  # type: ignore[attr-defined]
    return frozenset(found)


def names_in_annotation(node: ast.expr) -> frozenset[str]:
    """Every bare name an annotation spells, including inside a string."""
    found: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            found.add(child.id)
        elif isinstance(child, ast.Constant) and isinstance(child.value, str):
            try:
                inner = ast.parse(child.value, mode="eval")
            except SyntaxError:
                continue
            found |= names_in_annotation(inner.body)
    return frozenset(found)


def public_annotations(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.expr]:
    """The annotations of a function's public parameters and its return."""
    arguments = function.args
    parameters = [
        *arguments.posonlyargs,
        *arguments.args,
        *arguments.kwonlyargs,
        *(a for a in (arguments.vararg, arguments.kwarg) if a is not None),
    ]
    found = [
        parameter.annotation
        for parameter in parameters
        if parameter.annotation is not None and not parameter.arg.startswith("_")
    ]
    if function.returns is not None:
        found.append(function.returns)
    return found


def field_annotations(cls: ast.ClassDef) -> list[ast.expr]:
    """The annotations of a class body's public fields."""
    return [
        node.annotation
        for node in cls.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and not node.target.id.startswith("_")
    ]


def aliases_spelled(
    annotations: list[ast.expr],
    scope: Mapping[str, object],
    aliases: Mapping[int, str],
) -> dict[str, object]:
    """The known aliases some annotations spell, resolved where they were written.

    ``scope`` is the namespace of the module that wrote the annotations and
    ``aliases`` maps the identity of each known alias to its qualified name. A
    spelled name the scope does not bind, or binds to something that is not a
    known alias, contributes nothing.
    """
    found: dict[str, object] = {}
    for annotation in annotations:
        for name in names_in_annotation(annotation):
            if name in scope:
                qualified = aliases.get(id(scope[name]))
                if qualified is not None:
                    found[qualified] = scope[name]
    return found


def nameable(obj: object, home: str, roots: Mapping[str, ModuleType]) -> bool:
    """Whether a caller can import ``obj`` from where its package says it lives.

    For this package that is any module's declaration; for a library it is the
    library's root.
    """
    if home == "paper_to_live":
        return id(obj) in declared_objects()
    root = roots[home]
    names = getattr(root, "__all__", ())
    return any(getattr(root, name, None) is obj for name in names)


# ---------------------------------------------------------------------------
# What the probe is pointed at.


def submodules() -> dict[str, ModuleType]:
    return {
        info.name: importlib.import_module(f"{PREFIX}{info.name}")
        for info in pkgutil.iter_modules([str(PACKAGE)])
        if info.name not in NOT_SURFACE
    }


def declared() -> dict[str, object]:
    """Every name some module declares, qualified by that module."""
    return {
        f"{module.__name__}.{name}": getattr(module, name)
        for module in submodules().values()
        for name in getattr(module, "__all__", ())
    }


def declared_objects() -> set[int]:
    return {id(obj) for obj in declared().values()}


def library_roots() -> dict[str, ModuleType]:
    return {name: importlib.import_module(name) for name in LIBRARIES}


def _module_sources(package: ModuleType) -> Iterator[tuple[ModuleType, str]]:
    directory = Path(typing.cast(str, package.__file__)).resolve().parent
    for info in pkgutil.walk_packages([str(directory)], prefix=f"{package.__name__}."):
        if info.name.rsplit(".", 1)[-1] in NOT_SURFACE or info.ispkg:
            continue
        module = importlib.import_module(info.name)
        path = Path(typing.cast(str, module.__file__))
        yield module, path.read_text(encoding="utf-8")


def known_aliases() -> dict[int, str]:
    """Each public alias of this package or a library, keyed by identity."""
    found: dict[int, str] = {}
    for package in (paper_to_live, *library_roots().values()):
        for module, source in _module_sources(package):
            for name in aliases_in(source):
                if not name.startswith("_") and hasattr(module, name):
                    found[id(getattr(module, name))] = f"{module.__name__}.{name}"
    return found


def reachable_callables() -> Iterator[tuple[str, Callable[..., object]]]:
    """Each declared function, and each public method or property of each class."""
    for label, obj in sorted(declared().items()):
        if inspect.isfunction(obj):
            yield label, obj
        elif inspect.isclass(obj) and obj.__module__.startswith(PREFIX):
            seen: set[str] = set()
            for klass in obj.__mro__:
                if not klass.__module__.startswith(PREFIX):
                    continue
                for attribute, value in vars(klass).items():
                    if attribute in seen:
                        continue
                    seen.add(attribute)
                    if attribute.startswith("_") and attribute != "__init__":
                        continue
                    member = value
                    if isinstance(member, classmethod | staticmethod):
                        member = member.__func__
                    if isinstance(member, property):
                        member = member.fget
                    if inspect.isfunction(member):
                        yield f"{label}.{attribute}", member


def reachable_classes() -> Iterator[tuple[str, type]]:
    for label, obj in sorted(declared().items()):
        if inspect.isclass(obj) and obj.__module__.startswith(PREFIX):
            yield label, obj


def _function_node(
    function: Callable[..., object],
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    # A dataclass's generated ``__init__`` has no source; its fields are covered
    # through the class body instead.
    try:
        source = textwrap.dedent(inspect.getsource(function))
    except (OSError, TypeError):
        return None
    node = ast.parse(source).body[0]
    return node if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) else None


def unnameable_classes() -> dict[str, list[str]]:
    """Reachable signatures and fields written in a class a caller cannot import."""
    roots = library_roots()
    missing: dict[str, set[str]] = {}

    def note(label: str, hints: list[object]) -> None:
        for kind in set().union(*(classes_in(hint) for hint in hints)):
            home = home_of(kind.__module__)
            if home is not None and not nameable(kind, home, roots):
                qualified = f"{kind.__module__}.{kind.__qualname__}"
                missing.setdefault(qualified, set()).add(label)

    for label, function in reachable_callables():
        hints = typing.get_type_hints(function)
        note(label, [hint for name, hint in hints.items() if not name.startswith("_")])
    for label, cls in reachable_classes():
        hints = typing.get_type_hints(cls)
        fields = [h for f, h in hints.items() if not f.startswith("_")]
        note(f"{label} (fields)", fields)
    return {kind: sorted(labels) for kind, labels in sorted(missing.items())}


def spelled_aliases() -> dict[str, tuple[object, set[str]]]:
    """Each known alias a reachable signature or field spells, and where."""
    aliases = known_aliases()
    found: dict[str, tuple[object, set[str]]] = {}

    def note(
        label: str, annotations: list[ast.expr], scope: Mapping[str, object]
    ) -> None:
        for qualified, value in aliases_spelled(annotations, scope, aliases).items():
            found.setdefault(qualified, (value, set()))[1].add(label)

    for label, function in reachable_callables():
        node = _function_node(function)
        if node is not None:
            note(label, public_annotations(node), function.__globals__)
    for label, cls in reachable_classes():
        statement = ast.parse(textwrap.dedent(inspect.getsource(cls))).body[0]
        if isinstance(statement, ast.ClassDef):
            scope = vars(sys.modules[cls.__module__])
            note(f"{label} (fields)", field_annotations(statement), scope)
    return found


def unnameable_aliases() -> dict[str, list[str]]:
    roots = library_roots()
    missing: dict[str, list[str]] = {}
    for qualified, (value, labels) in sorted(spelled_aliases().items()):
        home = home_of(qualified)
        if home is not None and not nameable(value, home, roots):
            missing[qualified] = sorted(labels)
    return missing


# ---------------------------------------------------------------------------
# The checks.


def test_the_libraries_checked_are_the_ones_depended_on() -> None:
    """A dependency added to ``pyproject.toml`` joins the check, or this fails."""
    requires = importlib.metadata.requires("paper-to-live") or []
    depended = {
        re.split(r"[<>=!~ ;\[]", requirement, maxsplit=1)[0].lower()
        for requirement in requires
        if "extra ==" not in requirement
    } - {"numpy"}
    distributions = importlib.metadata.packages_distributions()
    checked = {distributions[name][0].lower() for name in LIBRARIES}
    assert checked == depended


def test_the_survey_is_worth_checking() -> None:
    # Every check below passes over an empty walk, so the walk is asserted
    # first. The floors sit under what is there (26 declared names, 31
    # callables and 10 classes when this was written).
    assert len(declared()) > 20
    assert sum(1 for _ in reachable_callables()) > 25
    assert sum(1 for _ in reachable_classes()) > 7
    assert "paper_to_live.types.FloatArray" in set(known_aliases().values())


def test_the_survey_reaches_into_the_libraries() -> None:
    """The library rule is exercised, not passing because it met no library type.

    ``screen_for`` takes three ``tenor`` instruments and ``build_curve``
    returns a ``tenor`` curve; the walk is shown to find all four.
    """
    found: set[str] = set()
    for _, function in reachable_callables():
        for hint in typing.get_type_hints(function).values():
            found |= {kind.__name__ for kind in classes_in(hint)
                      if not kind.__module__.startswith(PREFIX)}
    assert {"Deposit", "Future", "Swap", "Bootstrapped"} <= found


def test_the_alias_survey_resolves_real_spellings() -> None:
    """Both halves of the alias rule meet a real spelling: one of this
    package's aliases, and ``tenor``'s ``Instrument`` union, which
    ``screen_for`` returns a tuple of."""
    spelled = set(spelled_aliases())
    assert "paper_to_live.types.FloatArray" in spelled
    assert "tenor.instruments.Instrument" in spelled


def test_a_class_in_a_reachable_signature_can_be_imported() -> None:
    unnameable = unnameable_classes()
    assert not unnameable, (
        f"reachable signatures written in classes a caller cannot import: {unnameable}"
    )


def test_an_alias_a_reachable_signature_is_written_in_can_be_imported() -> None:
    unnameable = unnameable_aliases()
    assert not unnameable, (
        f"reachable signatures written in aliases a caller cannot import: {unnameable}"
    )


# ---------------------------------------------------------------------------
# The probe's own rules, against inputs written for each, since the package
# does not exercise every branch.


def test_only_this_package_and_its_libraries_have_a_home() -> None:
    assert home_of("paper_to_live.funding") == "paper_to_live"
    assert home_of("tenor.instruments") == "tenor"
    assert home_of("tenorish") is None
    assert home_of("numpy") is None
    assert home_of("datetime") is None


def test_classes_are_found_inside_every_kind_of_hint() -> None:
    from paper_to_live.types import Settings

    hints: list[object] = [
        Settings,
        list[Settings],
        Settings | None,
        dict[str, tuple[int, Settings]],
        Callable[[Settings], float],
        Callable[[Callable[[Settings], float]], float],
        type[Settings],
    ]
    for hint in hints:
        assert classes_in(hint) == {Settings}, hint


def test_classes_outside_the_checked_packages_are_not_found() -> None:
    import datetime

    assert classes_in(list[int] | dict[str, float] | None) == set()
    assert classes_in(Path) == set()
    assert classes_in(datetime.date) == set()


def test_a_library_class_is_nameable_only_from_the_root() -> None:
    """A library type is imported from the library's root, not a submodule."""

    class Hidden:
        pass

    class Exported:
        pass

    root = ModuleType("fake")
    root.__all__ = ["Exported"]  # type: ignore[attr-defined]
    root.Exported = Exported  # type: ignore[attr-defined]
    root.Hidden = Hidden  # type: ignore[attr-defined]  # bound, never declared
    roots = {"fake": root}
    assert nameable(Exported, "fake", roots)
    assert not nameable(Hidden, "fake", roots)
    # An equal-looking class under the declared name is not the one meant.
    root.Exported = type("Exported", (), {})  # type: ignore[attr-defined]
    assert not nameable(Exported, "fake", roots)


def test_aliases_are_the_assignments_that_read_as_types() -> None:
    source = textwrap.dedent(
        """
        from typing import Literal, TypeAlias
        Vector = list[float]
        Side = Literal["long", "short"]
        Either = int | str
        Maybe = float | None
        Explicit: TypeAlias = "dict[str, float]"
        Arrays = npt.NDArray[np.float64]
        """
    )
    assert aliases_in(source) == {
        "Vector", "Side", "Either", "Maybe", "Explicit", "Arrays",
    }


def test_values_are_not_aliases() -> None:
    source = textwrap.dedent(
        """
        PERIODS_PER_YEAR = 252.0
        NAME = "paper-to-live"
        DEFAULT = make_default()
        Same = Vector
        FLAGS = 1 | 2
        CHOICES = ("a", "b")
        LOOKUP = mapping["key"]
        count: int = 3
        """
    )
    assert aliases_in(source) == set()


def test_annotation_names_include_those_inside_a_string() -> None:
    node = ast.parse("x: 'FloatArray | None'").body[0]
    assert isinstance(node, ast.AnnAssign)
    assert names_in_annotation(node.annotation) == {"FloatArray"}
    node = ast.parse("x: 'not a [type'").body[0]
    assert isinstance(node, ast.AnnAssign)
    assert names_in_annotation(node.annotation) == set()


def test_public_annotations_skip_private_parameters_and_keep_the_return() -> None:
    node = ast.parse(
        "def f(a: A, /, b: B, *args: C, _c: Hidden, d: D = 1, **kw: E) -> R: ..."
    ).body[0]
    assert isinstance(node, ast.FunctionDef)
    spelled = {ast.unparse(annotation) for annotation in public_annotations(node)}
    assert spelled == {"A", "B", "C", "D", "E", "R"}


def test_field_annotations_skip_private_fields_and_methods() -> None:
    node = ast.parse(
        "class C:\n    a: A\n    _b: Hidden\n    c = 1\n    def m(self) -> R: ...\n"
    ).body[0]
    assert isinstance(node, ast.ClassDef)
    assert [ast.unparse(a) for a in field_annotations(node)] == ["A"]


def test_a_spelled_name_resolves_in_the_scope_that_wrote_it() -> None:
    """Two scopes spell ``Prices``; only the one binding the alias reports it."""
    alias = list[float]
    aliases = {id(alias): "paper_to_live.types.Prices"}
    node = ast.parse("def f(p: Prices) -> 'list[Prices]': ...").body[0]
    assert isinstance(node, ast.FunctionDef)
    annotations = public_annotations(node)
    assert aliases_spelled(annotations, {"Prices": alias}, aliases) == {
        "paper_to_live.types.Prices": alias
    }
    assert aliases_spelled(annotations, {"Prices": int}, aliases) == {}
    assert aliases_spelled(annotations, {}, aliases) == {}
