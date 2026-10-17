"""The command line, its defaults, and its help text."""

from __future__ import annotations

import argparse
import dataclasses
import io
import json
from collections.abc import Iterator
from contextlib import redirect_stdout

import pytest

from paper_to_live.cli import main, parser
from paper_to_live.types import Settings


def command_paths(
    command: argparse.ArgumentParser, prefix: tuple[str, ...] = ()
) -> Iterator[tuple[str, ...]]:
    """Every command path the parser can reach, the root included.

    Recursive, so a subcommand that grows subcommands of its own is swept
    without anybody remembering to come back here.
    """
    yield prefix
    for action in command._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, child in sorted(action.choices.items()):
                yield from command_paths(child, (*prefix, name))


def arguments_of(command: argparse.ArgumentParser) -> Iterator[argparse.Action]:
    for action in command._actions:
        if isinstance(action, argparse._SubParsersAction):
            continue
        if isinstance(action, argparse._HelpAction | argparse._VersionAction):
            continue
        yield action


PATHS = tuple(command_paths(parser()))
IDS = tuple(" ".join(path) or "paper-to-live" for path in PATHS)


def test_the_sweep_found_the_commands() -> None:
    """Guards the guard: a sweep over nothing passes trivially."""
    assert len(PATHS) == 2
    assert () in PATHS
    assert ("run",) in PATHS


@pytest.mark.parametrize("path", PATHS, ids=IDS)
def test_help_renders(path: tuple[str, ...]) -> None:
    """``--help`` is the first thing anybody types and it can raise.

    argparse expands help strings through ``%``-formatting so ``%(default)s``
    works, which turns a literal per cent sign into a conversion specifier.
    Nothing else in a suite notices, because the commands themselves never
    render their help.
    """
    printed = io.StringIO()
    with redirect_stdout(printed), pytest.raises(SystemExit) as exited:
        main([*path, "--help"])
    assert exited.value.code == 0
    assert printed.getvalue().startswith("usage:")


@pytest.mark.parametrize("path", PATHS, ids=IDS)
def test_every_argument_has_help(path: tuple[str, ...]) -> None:
    """An option that prints only its flag name explains nothing."""
    command = parser()
    for name in path:
        for action in command._actions:
            if isinstance(action, argparse._SubParsersAction):
                command = action.choices[name]
                break
    missing = [
        action.dest
        for action in arguments_of(command)
        if not (action.help or "").strip()
    ]
    assert not missing, f"{' '.join(path)}: {missing}"


def test_a_literal_per_cent_sign_would_be_caught() -> None:
    """The sweep above is only a guard if a bad string really fails it."""
    broken = argparse.ArgumentParser(prog="broken")
    broken.add_argument("--cash", help="20% in cash")
    with pytest.raises(TypeError):
        broken.format_help()


def test_defaults_match_the_settings_they_advertise() -> None:
    """Every ``--help`` default is the value the library would have used.

    ``Settings`` has ``slots=True``, so reading a default off the class gives
    the slot descriptor rather than the value: it type checks, it renders in
    ``--help`` as something plausible, and it fails only when the value is
    used. Comparing against an instance is the check that catches it.
    """
    defaults = Settings()
    run_command = parser()._actions[-1].choices["run"]  # type: ignore[attr-defined]
    by_name = {action.dest: action.default for action in arguments_of(run_command)}
    for field in dataclasses.fields(defaults):
        if field.name not in by_name:
            continue
        assert by_name[field.name] == getattr(defaults, field.name), field.name
        assert not isinstance(by_name[field.name], type(Settings.__dict__["days"]))


def test_run_prints_the_table() -> None:
    printed = io.StringIO()
    with redirect_stdout(printed):
        assert main(["run", "--days", "600"]) == 0
    text = printed.getvalue()
    assert "WHERE THE SHARPE RATIO WENT" in text
    assert "Surviving" in text
    assert "CHECKS" in text


def test_no_checks_leaves_the_checks_out() -> None:
    printed = io.StringIO()
    with redirect_stdout(printed):
        main(["run", "--days", "600", "--no-checks"])
    assert "CHECKS" not in printed.getvalue()


def test_json_is_valid_and_carries_every_stage() -> None:
    printed = io.StringIO()
    with redirect_stdout(printed):
        assert main(["run", "--days", "600", "--json"]) == 0
    payload = json.loads(printed.getvalue())
    assert set(payload) == {
        "settings",
        "selection",
        "execution",
        "risk",
        "funding",
        "erosion",
    }
    # Nothing non-finite may reach a payload: a NaN survives `json.dumps` by
    # default and is not valid JSON, so a consumer fails on it rather than here.
    json.dumps(payload, allow_nan=False)


def test_an_impossible_setting_is_a_message_not_a_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A user error exits 2 with a line they can act on."""
    assert main(["run", "--days", "10"]) == 2
    captured = capsys.readouterr()
    assert "paper-to-live:" in captured.err
    assert "Traceback" not in captured.err


def test_no_command_prints_help() -> None:
    printed = io.StringIO()
    with redirect_stdout(printed):
        assert main([]) == 0
    assert printed.getvalue().startswith("usage:")
