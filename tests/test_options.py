"""Every documented option, and whether anything outside its module chooses it.

An optional parameter with a default is a claim: that the caller may choose,
and that choosing works. A parameter no call site anywhere ever supplies has
never had that claim tested. The code that reads it runs, so coverage is
satisfied, but it only ever runs with the one value the author happened to
pick. Several defects across this family of repositories were exactly that
shape, so the question is asked mechanically here rather than remembered.

The gate walks the package with :mod:`ast` and collects two kinds of option:
every parameter with a default on a public function or method, and every field
with a default on a type a caller constructs.

Two rules in here differ from the version of this probe that runs in the
sibling libraries, and both differences were found by this package rather than
reasoned out. They are written down at length because the first draft of this
file reported three options and no problems, which was wrong on both counts.

**A type the caller passes in is not a result, even when a result mentions it.**
The sibling probe classifies a type as a result if it is named in the return
annotation of any public callable, and then closes that set over the fields of
those types: a type reached from a result is also a result, so a result's own
sub-objects are not read as bags of options. That closure is right in general
and badly wrong here. :func:`run` returns a ``Pipeline``, ``Pipeline`` carries
``settings: Settings``, and so ``Settings`` -- this package's entire
configuration surface, the thing every caller constructs -- became a result
and all ten of its fields became invisible. A result that records the inputs
that produced it is a good pattern and a common one, which is what makes this
hole worth closing rather than special-casing. The rule added is that a type
named directly in a *parameter* annotation of a public callable is an input,
and the closure may not claim an input. ``Settings`` appears as a parameter in
nine places across six modules; nothing has to be listed for it to be found.

**Forwarding a field onward is not choosing it.** The sibling probe counts
supply by parameter *name*, anywhere in the tree. ``selection.run_selection``
calls ``crossover_sweep(settings.days, fast=settings.fast, slow=settings.slow,
...)``, so the names ``fast`` and ``slow`` appear as keywords and the loose
probe reported ``Settings.fast`` and ``Settings.slow`` as exercised. They were
not: that call passes the defaults onward, and no call site in this repository
has ever constructed a ``Settings`` with either field set. Forwarding a default
is the opposite of choosing a value, and it is the likeliest way for a
configuration field to look exercised while never having been. So supply is
resolved against the owner: a field of a type counts only at a call
constructing that type, and a parameter of a function only at a call to that
function, positionally or by keyword.

Supply is counted positionally as well as by keyword, because
``f(bars, Estimator.PARKINSON)`` chooses an option exactly as ``estimator=``
does.

There is no exemption mechanism, and adding one is the first thing that will be
wanted the next time this fails. It is the wrong thing: an option nobody can be
bothered to choose once in a test is an option to delete.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "paper_to_live"
SEARCH = ("src", "tests", "docs")


@dataclass(frozen=True)
class Option:
    """One defaulted parameter or field, and where it is declared."""

    owner: str
    name: str
    module: Path

    def __str__(self) -> str:
        return f"{self.owner}({self.name}=)"


@dataclass(frozen=True)
class Signature:
    """A callable's positional parameter names, for resolving positional calls."""

    names: tuple[str, ...]


def _sources(*directories: str) -> list[Path]:
    found: list[Path] = []
    for directory in directories:
        base = ROOT / directory
        if base.exists():
            found.extend(
                sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)
            )
    return found


def _names_in(annotation: ast.expr | None, into: set[str]) -> None:
    """Every bare name in an annotation, however it is wrapped."""
    if annotation is None:
        return
    for node in ast.walk(annotation):
        if isinstance(node, ast.Name):
            into.add(node.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # A quoted forward reference, which is how a classmethod names its
            # own class before the class exists.
            into.add(node.value.strip().strip("\"'"))
        elif isinstance(node, ast.Attribute):
            into.add(node.attr)


def _survey() -> tuple[list[Option], dict[str, Signature], set[str], set[str]]:
    """Declared options, signatures, the types returned, and the types taken in."""
    options: list[Option] = []
    signatures: dict[str, Signature] = {}
    returned: set[str] = set()
    taken: set[str] = set()
    annotations: dict[str, set[str]] = {}
    fields: dict[str, list[tuple[str, bool]]] = {}
    declared_in: dict[str, Path] = {}

    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf8"), str(path))

        def walk(node: ast.AST, prefix: str = "", module: Path = path) -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                    if child.name.startswith("_"):
                        continue
                    _names_in(child.returns, returned)
                    arguments = child.args
                    for argument in [
                        *arguments.posonlyargs,
                        *arguments.args,
                        *arguments.kwonlyargs,
                    ]:
                        _names_in(argument.annotation, taken)
                    names = [a.arg for a in [*arguments.posonlyargs, *arguments.args]]
                    if names and names[0] in ("self", "cls"):
                        names = names[1:]
                    signatures[child.name] = Signature(tuple(names))
                    required = len(names) - len(arguments.defaults)
                    for name in names[required:]:
                        if not name.startswith("_"):
                            options.append(Option(prefix + child.name, name, module))
                    for argument, default in zip(
                        arguments.kwonlyargs, arguments.kw_defaults, strict=True
                    ):
                        if default is not None and not argument.arg.startswith("_"):
                            options.append(
                                Option(prefix + child.name, argument.arg, module)
                            )
                elif isinstance(child, ast.ClassDef):
                    if child.name.startswith("_"):
                        continue
                    declared_in[child.name] = module
                    own: list[tuple[str, bool]] = []
                    mentioned: set[str] = set()
                    for statement in child.body:
                        if isinstance(statement, ast.AnnAssign) and isinstance(
                            statement.target, ast.Name
                        ):
                            own.append(
                                (statement.target.id, statement.value is not None)
                            )
                            _names_in(statement.annotation, mentioned)
                    annotations[child.name] = mentioned
                    fields[child.name] = own
                    own_names = tuple(n for n, _ in own)
                    signatures.setdefault(child.name, Signature(own_names))
                    walk(child, child.name + ".")

        walk(tree)

    # A type handed back inside something handed back is handed back too: a
    # result's own fields can name types that are never a return annotation of
    # their own, and without this closure their defaults would be read as
    # offers.
    frontier = set(returned)
    while frontier:
        reached: set[str] = set()
        for name in frontier:
            for mentioned_type in annotations.get(name, set()):
                if mentioned_type not in returned:
                    reached.add(mentioned_type)
        returned |= reached
        frontier = reached

    # One subtraction, applied after the closure, rather than a guard inside it.
    # A first version had both and they turned out to be redundant -- each kept
    # Settings out on its own, so removing either changed nothing and neither
    # could be tested. This is the whole rule: a type the caller passes in is
    # an input, whatever a result also says about it.
    results = returned - taken
    for name, own in fields.items():
        if name in results:
            continue  # A type the package returns: its defaults are slots, not offers.
        for field, has_default in own:
            if has_default and not field.startswith("_"):
                options.append(Option(name, field, declared_in[name]))

    return options, signatures, results, taken


def _callee(node: ast.Call) -> str | None:
    called = node.func
    if isinstance(called, ast.Name):
        return called.id
    if isinstance(called, ast.Attribute):
        return called.attr
    return None


def _supplied(signatures: dict[str, Signature]) -> dict[tuple[str, str], set[Path]]:
    """Which (owner, option) pairs a call site supplies, and the files that do it.

    Keyed by owner as well as name, so forwarding ``fast=settings.fast`` to
    another function does not register as choosing ``Settings.fast``.
    """
    places: dict[tuple[str, str], set[Path]] = defaultdict(set)
    for path in _sources(*SEARCH):
        tree = ast.parse(path.read_text(encoding="utf8"), str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            owner = _callee(node)
            if owner is None:
                continue
            for keyword in node.keywords:
                if keyword.arg is not None:
                    places[(owner, keyword.arg)].add(path)
            signature = signatures.get(owner)
            if signature is None:
                continue
            for index, _ in enumerate(node.args):
                if index < len(signature.names):
                    places[(owner, signature.names[index])].add(path)
    return places


OPTIONS, SIGNATURES, RESULTS, TAKEN = _survey()
SUPPLIED = _supplied(SIGNATURES)


def _unexercised(
    options: list[Option] | None = None,
    supplied: dict[tuple[str, str], set[Path]] | None = None,
) -> list[str]:
    """Options nothing outside the declaring module ever supplies.

    Both arguments default to the real survey. They are parameters so the rule
    itself can be tested against a map built for the purpose: mutating the
    package to check that the gate notices is unreliable here, because several
    tests choose the same option and removing one leaves the others.
    """
    options = OPTIONS if options is None else options
    supplied = SUPPLIED if supplied is None else supplied
    found: set[str] = set()
    for option in options:
        # A method's options are declared as "Class.method"; supply is resolved
        # against the attribute name the call site uses.
        owner = option.owner.rsplit(".", 1)[-1]
        places = supplied.get((owner, option.name), set())
        # An assignment inside the declaring module is usually the default being
        # written down rather than a caller choosing, so it does not count alone.
        if not places or places == {option.module}:
            found.add(str(option))
    return sorted(found)


class TestTheSurveyItself:
    def test_it_surveyed_the_source_it_claims_to_have_surveyed(self) -> None:
        # "Nothing is unexercised" passes trivially over an empty survey, so the
        # survey is asserted before the claim is made.
        assert len(_sources(*SEARCH)) > 18
        assert len(OPTIONS) > 11
        assert len(SIGNATURES) > 30
        named = {str(option) for option in OPTIONS}
        for certainly_an_option in (
            "Settings(fast=)",
            "Settings(slow=)",
            "Settings(days=)",
            "Settings(trend=)",
            "run(settings=)",
        ):
            assert certainly_an_option in named

    def test_the_configuration_type_is_not_mistaken_for_a_result(self) -> None:
        # The hole this closes. run() returns a Pipeline, Pipeline carries
        # settings: Settings, so the closure over a result's fields reached
        # Settings and treated all ten of its fields as slots a caller never
        # picks. It is the opposite: Settings is the only thing a caller of this
        # package configures.
        assert "Settings" in TAKEN
        assert "Settings" not in RESULTS
        named = {str(option) for option in OPTIONS}
        assert len([o for o in named if o.startswith("Settings(")]) == 10

    def test_a_result_type_is_still_not_treated_as_a_bag_of_options(self) -> None:
        # The closure has to keep doing its job for types that really are only
        # ever handed back. Nobody chooses a reconstruction's tolerance or an
        # instrument's fields; the stage that produced them filled them in.
        for genuinely_returned in ("Reconstruction", "Instrument", "Order"):
            assert genuinely_returned in RESULTS
        named = {str(option) for option in OPTIONS}
        prefixes = ("Reconstruction(", "Instrument(", "Order(")
        assert not [o for o in named if o.startswith(prefixes)]

    def test_forwarding_a_field_onward_does_not_count_as_choosing_it(self) -> None:
        # run_selection calls crossover_sweep(..., fast=settings.fast,
        # slow=settings.slow), which passes the defaults through. A probe keyed
        # on the parameter name alone read that as Settings.fast being chosen,
        # and it is the reverse: a forward is the default travelling, not a
        # caller picking. Supply is keyed on the owner, so the two are distinct.
        forwards = SUPPLIED[("crossover_sweep", "fast")]
        assert any(path.name == "selection.py" for path in forwards)
        # The same name under two owners, which is the whole distinction: the
        # forward in selection.py and the choice in the suite are different
        # keys, so the forward can no longer stand in for the choice.
        chosen = SUPPLIED[("Settings", "fast")]
        assert any(path.name.startswith("test_") for path in chosen)
        assert not any(path.name == "selection.py" for path in chosen)

    def test_a_positional_argument_counts_as_choosing(self) -> None:
        # risk_adjusted_capital(result, multiple) is called positionally, so a
        # keyword-only probe would report its second parameter unexercised.
        assert SIGNATURES["risk_adjusted_capital"].names == ("result", "multiple")
        assert ("risk_adjusted_capital", "multiple") in SUPPLIED


class TestTheRuleItself:
    """The predicate, exercised against maps built for the purpose.

    Mutating the package to check the gate notices does not work here: four
    tests choose ``Settings.fast``, so deleting one leaves three and the gate
    stays green for the right reason. So the rule is fed its inputs directly.
    """

    DECLARED = Path("/pkg/types.py")

    def _option(self, owner: str, name: str) -> Option:
        return Option(owner, name, self.DECLARED)

    def test_an_option_nothing_supplies_is_reported(self) -> None:
        option = self._option("Settings", "fast")
        assert _unexercised([option], {}) == ["Settings(fast=)"]

    def test_an_option_supplied_from_elsewhere_is_not_reported(self) -> None:
        option = self._option("Settings", "fast")
        supplied = {("Settings", "fast"): {Path("/pkg/tests/test_selection.py")}}
        assert _unexercised([option], supplied) == []

    def test_supply_only_from_the_declaring_module_does_not_count(self) -> None:
        # Writing the default down next to the declaration is not a caller
        # choosing it.
        option = self._option("Settings", "fast")
        assert _unexercised([option], {("Settings", "fast"): {self.DECLARED}}) == [
            "Settings(fast=)"
        ]

    def test_supply_under_a_different_owner_does_not_count(self) -> None:
        # The forwarding case, as a rule rather than as an observation about
        # this package: crossover_sweep(fast=settings.fast) must not satisfy
        # Settings(fast=).
        option = self._option("Settings", "fast")
        forwarded = {("crossover_sweep", "fast"): {Path("/pkg/selection.py")}}
        assert _unexercised([option], forwarded) == ["Settings(fast=)"]

    def test_a_method_option_resolves_on_the_attribute_name(self) -> None:
        option = self._option("Pipeline.as_dict", "indent")
        assert _unexercised([option], {}) == ["Pipeline.as_dict(indent=)"]
        supplied = {("as_dict", "indent"): {Path("/pkg/tests/test_pipeline.py")}}
        assert _unexercised([option], supplied) == []


class TestEveryOptionIsChosenSomewhere:
    def test_none_is_left_only_ever_at_its_default(self) -> None:
        assert _unexercised() == []
