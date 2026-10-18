"""Checks on the distribution metadata rather than on the arithmetic.

Everything else in this suite asks whether the figures are right. These ask
whether anybody can install the thing that computes them, and the failures that
stop an install are not the kind unit tests catch: a version written in two
files that drift apart, a licence claimed in metadata but absent from the
artefact, a typing marker that exists in the source tree and never reaches the
wheel. Each is invisible until somebody tries to depend on the package, which
is the worst possible moment to find out — an index will not let a version be
re-uploaded once it has been taken.

This package has one wrinkle the libraries it sits on do not. It declares
bounded requirements on four distributions that are not on any index yet, so
the metadata is *correct* and currently unsatisfiable. That is deliberate — a
`git+https` direct reference is refused on upload, so it cannot be what the
metadata says — but it means the dependency list is worth pinning here, so that
the day the libraries are released, the thing that has to change is visible
rather than discovered.
"""

from __future__ import annotations

import re
import sys
from importlib.metadata import entry_points, metadata, packages_distributions, version
from pathlib import Path

import pytest

import paper_to_live

ROOT = Path(__file__).resolve().parent.parent

#: The name on the index and the name in an import are the same here, unlike
#: in two of the libraries below. Nothing enforces that beyond this constant
#: and the test that compares it against `pyproject.toml`.
DISTRIBUTION = "paper-to-live"

#: The four libraries this demonstration chains together, as the metadata names
#: them. Two of them are not importable under these names: `slippage-tca`
#: imports as `slippage` and `holdout-backtest` as `holdout`, because the short
#: names on the index belong to unrelated projects.
LIBRARIES = ("holdout-backtest", "slippage-tca", "shortfall", "tenor")


def _pyproject() -> dict[str, object]:
    """The declared metadata, or skip when installed without a checkout."""
    if sys.version_info < (3, 11):
        pytest.skip("tomllib is 3.11+")
    import tomllib

    path = ROOT / "pyproject.toml"
    if not path.exists():
        pytest.skip("no checkout to compare against")
    loaded = tomllib.loads(path.read_text())["project"]
    assert isinstance(loaded, dict)
    return loaded


def test_version_is_exported() -> None:
    """The package says what it is without an installed-metadata lookup."""
    assert re.fullmatch(r"\d+\.\d+\.\d+", paper_to_live.__version__)


def test_exported_version_matches_the_installed_distribution() -> None:
    """The attribute and the installed metadata are the same string.

    They live in two different files. Bumping one and forgetting the other is
    the ordinary mistake, and it produces a release whose reported version is a
    lie — which is also the mistake the release workflow's tag guard catches,
    one step later and one step more expensively.
    """
    assert paper_to_live.__version__ == version(DISTRIBUTION)


def test_exported_version_matches_the_source_of_truth() -> None:
    """The attribute agrees with `pyproject.toml` in the checkout.

    The check above compares against what is *installed*, which in an editable
    install is a snapshot taken at install time and can be stale. Reading the
    file is what makes the check bite without a reinstall.
    """
    assert paper_to_live.__version__ == _pyproject()["version"]


def test_the_distribution_name_is_the_one_the_index_will_see() -> None:
    """`pyproject.toml` declares the name this file hard-codes.

    Every metadata lookup here names the distribution, so a rename would leave
    the suite asking about a package that no longer exists and failing with a
    confusing `PackageNotFoundError`. Comparing the two directly turns that into
    a one-line failure that names the problem.
    """
    assert _pyproject()["name"] == DISTRIBUTION


def test_the_import_name_resolves_to_this_distribution() -> None:
    """`import paper_to_live` comes from `paper-to-live`.

    Here the two names are the same modulo the hyphen, which is worth asserting
    precisely because it is *not* true of two of the libraries underneath: a
    reader who has just seen `slippage-tca` import as `slippage` should be able
    to check rather than assume.
    """
    mapping = packages_distributions()
    if "paper_to_live" not in mapping:  # layouts this lookup cannot see
        pytest.skip("top-level module not resolvable from installed metadata")
    assert DISTRIBUTION in mapping["paper_to_live"]


def test_licence_text_is_present() -> None:
    """The licence the metadata claims exists as a file, and says MIT."""
    licence = ROOT / "LICENSE"
    if not licence.exists():
        pytest.skip("no checkout to compare against")
    assert "MIT License" in licence.read_text()


def test_licence_reaches_the_built_distribution() -> None:
    """The installed distribution carries the licence, not just the repository.

    `license-files` in `pyproject.toml` is what does this. Without it the
    metadata goes on claiming MIT while the artefact ships no terms at all.
    """
    fields = metadata(DISTRIBUTION)
    assert fields["License-Expression"] == "MIT"
    assert "LICENSE" in fields.get_all("License-File", [])


def test_the_typing_marker_ships() -> None:
    """`Typing :: Typed` is only true if `py.typed` is inside the package.

    The classifier is a promise to type checkers, made in `pyproject.toml` and
    kept by a file in the package directory, with nothing connecting the two.
    The failure is quiet: in a source checkout a type checker reads the
    annotations off the files and everything looks fine, while a consumer who
    installed the package gets none of them.
    """
    assert (Path(paper_to_live.__file__).parent / "py.typed").is_file()
    assert "Typing :: Typed" in metadata(DISTRIBUTION).get_all("Classifier", [])


def test_the_console_script_reaches_the_cli() -> None:
    """One entry point, pointing at the function that implements it."""
    scripts = {
        entry.name: entry.value
        for entry in entry_points(group="console_scripts")
        if entry.name == DISTRIBUTION
    }
    assert scripts == {DISTRIBUTION: "paper_to_live.cli:main"}


def test_the_entry_point_reports_the_version() -> None:
    """`paper-to-live --version` prints it, and exits zero doing so.

    argparse's version action raises `SystemExit`, so the assertion is on the
    exit code as much as on the text.
    """
    from paper_to_live.cli import main

    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0


def test_every_library_is_a_bounded_requirement() -> None:
    """The four libraries are declared with a range, not a direct reference.

    A `git+https` requirement is refused on upload, so it cannot be what a
    publishable distribution says — which is the reason the CI wheelhouse
    exists at all. Pinning the shape here means a convenience edit that swaps a
    range for a URL fails in the repository rather than at the index.
    """
    declared = _pyproject()["dependencies"]
    assert isinstance(declared, list)
    requirements = {
        re.split(r"[<>=!~\[]", str(line).strip(), maxsplit=1)[0].strip(): str(line)
        for line in declared
    }
    for library in LIBRARIES:
        assert library in requirements, f"{library} is no longer a declared dependency"
        line = requirements[library]
        assert "@" not in line, f"{library} is declared as a direct reference: {line}"
        assert ">=" in line and "<" in line, f"{library} is unbounded: {line}"


def test_each_declared_library_is_installed_and_importable() -> None:
    """What the metadata asks for is what the test environment has.

    The import names differ from two of the distribution names, so this walks
    from the declared requirement to the installed distribution and then to the
    module, which is the path a consumer's install takes. It is also the check
    that will start passing *through the index* rather than through the
    wheelhouse on the day the libraries are released, with nothing here needing
    to change.
    """
    imports = {
        "holdout-backtest": "holdout",
        "slippage-tca": "slippage",
        "shortfall": "shortfall",
        "tenor": "tenor",
    }
    for library in LIBRARIES:
        assert re.fullmatch(r"\d+\.\d+\.\d+", version(library)), library
        mapping = packages_distributions()
        module = imports[library]
        if module not in mapping:
            pytest.skip(f"{module} not resolvable from installed metadata")
        assert library in mapping[module], f"{module} does not come from {library}"
