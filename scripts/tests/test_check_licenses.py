"""Tests for scripts/check-licenses.py.

The semantics ARE the product here, so these tests pin them directly rather than
going through the collectors. Every case below corresponds to a decision recorded in
docs/superpowers/specs/2026-09-07-license-compliance-design.md section 7.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_CHECKER = Path(__file__).resolve().parent.parent / "check-licenses.py"


def _load() -> ModuleType:
    # The script's filename contains a hyphen, so it cannot be imported by name.
    spec = importlib.util.spec_from_file_location("check_licenses", _CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_licenses"] = module
    spec.loader.exec_module(module)
    return module


cl = _load()


def test_a_plain_allowed_id_passes() -> None:
    allowed, reason = cl.evaluate("MIT")
    assert allowed is True
    assert reason == ""


def test_a_forbidden_id_fails() -> None:
    allowed, reason = cl.evaluate("SSPL-1.0")
    assert allowed is False
    assert reason


def test_and_requires_every_operand_to_be_allowed() -> None:
    # THE regression test for this whole design. `license-checker --onlyAllow` uses
    # String.indexOf, so it passes this expression because "Apache-2.0" is a substring.
    # AND means the consumer must comply with BOTH; one forbidden operand poisons it.
    allowed, _ = cl.evaluate("(Apache-2.0 AND SSPL-1.0)")
    assert allowed is False


def test_and_passes_when_both_operands_are_allowed() -> None:
    allowed, _ = cl.evaluate("(Apache-2.0 AND BSD-3-Clause)")
    assert allowed is True


def test_or_passes_on_a_single_allowed_operand() -> None:
    assert cl.evaluate("(MIT OR CC0-1.0)")[0] is True


def test_or_without_parentheses_parses() -> None:
    # Real signal from `grpcio`'s metadata; the SPDX grammar does not require parens.
    assert cl.evaluate("Apache-2.0 OR BSD-2-Clause")[0] is True


def test_or_fails_when_no_operand_is_allowed() -> None:
    assert cl.evaluate("GPL-3.0-only OR AGPL-3.0-only")[0] is False


def test_and_binds_tighter_than_or() -> None:
    # SPDX precedence, and the reason _or() and _and() are two functions rather than one
    # loop over {OR, AND}. Both expressions below are unparenthesised, so only precedence
    # decides them - and the two possible parses disagree, which is what makes this a real
    # test rather than a restatement of the AND and OR cases above.
    #
    #   MIT OR (Apache-2.0 AND SSPL-1.0)  -> True OR False  -> allowed    <- correct
    #   (MIT OR Apache-2.0) AND SSPL-1.0  -> True AND False -> denied     <- wrong
    #
    # A merged loop would evaluate strictly left to right, produce the second parse, and
    # start rejecting legitimately dual-licensed packages. Nothing else in this file would
    # notice.
    assert cl.evaluate("MIT OR Apache-2.0 AND SSPL-1.0")[0] is True

    # The mirror image, parenthesised: an allowed operand ANDed with a group in which
    # NOTHING is allowed must fail. This is the direction that matters for safety - it
    # pins that a forbidden group cannot be laundered by an allowed sibling.
    assert cl.evaluate("MIT AND (SSPL-1.0 OR GPL-3.0-only)")[0] is False


def test_with_applied_to_a_group_is_rejected() -> None:
    # `WITH` takes a license IDENTIFIER on its left, never a parenthesised expression -
    # this is invalid SPDX. It is also the exact shape in which a careless parser leaks a
    # bare GPL: if _with() were "simplified" to accept a WITH suffix after the paren
    # branch, the group below would evaluate to True on MIT's account while the reader
    # sees GPL-2.0-only pass through a Classpath exception it was never paired with.
    #
    # Fail-closed does the work here: the expression is refused as unparseable rather than
    # decided. That is the right answer for invalid SPDX - never a guess.
    allowed, reason = cl.evaluate("(GPL-2.0-only OR MIT) WITH Classpath-exception-2.0")
    assert allowed is False
    assert "unrecognis" in reason.lower() or "unparse" in reason.lower()


def test_with_is_atomic_and_allowed_as_a_pair() -> None:
    assert cl.evaluate("GPL-2.0-only WITH Classpath-exception-2.0")[0] is True


def test_bare_gpl_is_denied_even_though_the_with_pair_is_allowed() -> None:
    # The reason WITH must never be decomposed: splitting the pair above would make
    # this pass, which is exactly what the policy forbids.
    assert cl.evaluate("GPL-2.0-only")[0] is False


def test_with_an_unknown_exception_is_denied() -> None:
    assert cl.evaluate("GPL-2.0-only WITH Some-Other-Exception")[0] is False


def test_spdx_ids_compare_case_insensitively() -> None:
    assert cl.evaluate("mit")[0] is True
    assert cl.evaluate("APACHE-2.0")[0] is True


def test_a_trailing_plus_means_or_later() -> None:
    # The policy itself is written as "LGPL 2.1+", so a dependency spelling it that
    # way must not be blocked by the policy's own notation.
    assert cl.evaluate("LGPL-2.1+")[0] is True


def test_known_free_text_spellings_normalise() -> None:
    assert cl.evaluate("3-Clause BSD License")[0] is True  # protobuf
    assert cl.evaluate("Apache License 2.0")[0] is True  # legacy metadata
    assert cl.evaluate("ISC License")[0] is True
    assert cl.evaluate("Mozilla Public License 2.0 (MPL 2.0)")[0] is True  # Trove


def test_an_unrecognised_spelling_fails_closed() -> None:
    allowed, reason = cl.evaluate("Totally Made Up License v9")
    assert allowed is False
    assert "unrecognis" in reason.lower() or "unparse" in reason.lower()


def test_an_empty_signal_fails_closed() -> None:
    assert cl.evaluate("")[0] is False


def test_an_unbalanced_expression_fails_closed_rather_than_raising() -> None:
    allowed, reason = cl.evaluate("(MIT OR Apache-2.0")
    assert allowed is False
    assert reason


def test_the_four_policy_additions_are_present() -> None:
    # Section 5.3 of the spec. Each was added on evidence from this repo's own tree;
    # removing one should break a test, not silently start failing the real run.
    for spdx in ("BlueOak-1.0.0", "PSF-2.0", "Python-2.0", "Unlicense", "MPL-2.0"):
        assert cl.evaluate(spdx)[0] is True, spdx


def test_npm_license_field_variants_normalise_to_one_signal() -> None:
    # npm packages declare a license three different ways across the registry's history.
    assert cl._npm_signal({"license": "MIT"}) == ("MIT", "package.json:license")
    assert cl._npm_signal({"license": {"type": "MIT"}}) == ("MIT", "package.json:license")
    # The legacy array form meant "the consumer may choose", i.e. OR.
    assert cl._npm_signal({"licenses": [{"type": "MIT"}, {"type": "Apache-2.0"}]}) == (
        "MIT OR Apache-2.0",
        "package.json:licenses[]",
    )


def test_npm_undeclared_license_yields_an_empty_signal() -> None:
    # Empty rather than a guess: evaluate() turns it into a violation with
    # "no license declared", which is what a human needs to see.
    assert cl._npm_signal({})[0] == ""


def test_npm_collector_refuses_an_empty_or_half_installed_tree(tmp_path: Path) -> None:
    # A checker that silently checks nothing is worse than no checker: an empty
    # node_modules (or a half-installed one, well short of a real `npm ci`) must fail
    # loudly rather than report a clean, empty result.
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    with pytest.raises(cl.CollectorError):
        cl.collect_npm(tmp_path)


def test_python_source_precedence_prefers_the_spdx_expression() -> None:
    # httpcore carries BOTH a PEP 639 License-Expression and the vaguer "BSD License"
    # Trove classifier. The precise one must win: the classifier cannot distinguish
    # 2-Clause from 3-Clause.
    meta = {
        "name": "httpcore",
        "version": "1.0.0",
        "license_expression": "BSD-3-Clause",
        "license": "",
        "classifiers": ["License :: OSI Approved :: BSD License"],
    }
    assert cl._python_signal(meta) == ("BSD-3-Clause", "License-Expression")


def test_python_falls_back_to_the_legacy_license_field() -> None:
    meta = {
        "name": "protobuf",
        "version": "7.36.1",
        "license_expression": "",
        "license": "3-Clause BSD License",
        "classifiers": [],
    }
    assert cl._python_signal(meta) == ("3-Clause BSD License", "License")


def test_python_falls_back_to_a_trove_classifier_last() -> None:
    meta = {
        "name": "certifi",
        "version": "2026.1.1",
        "license_expression": "",
        "license": "",
        "classifiers": ["License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)"],
    }
    assert cl._python_signal(meta) == ("Mozilla Public License 2.0 (MPL 2.0)", "Classifier")


def test_python_multiline_legacy_license_text_is_not_used_as_a_signal() -> None:
    # Some packages paste their entire license TEXT into the License field. That is not a
    # signal, and treating its first line as one would be a guess.
    meta = {
        "name": "whatever",
        "version": "1.0",
        "license_expression": "",
        "license": "Copyright (c) 2026\n\nPermission is hereby granted, free of charge...",
        "classifiers": [],
    }
    assert cl._python_signal(meta)[0] == ""


def test_python_legacy_non_answer_falls_back_to_the_classifier() -> None:
    # The real `python-dateutil` shape, and the reason _LEGACY_NON_ANSWERS exists. Its
    # legacy License field says "Dual License": grammatically a license name, naming no
    # license - it is a pointer to the two classifiers beside it. Short and single-line, so
    # neither half of the pasted-text guard catches it, and without the non-answer set
    # evaluate() fails it closed as an unparseable two-token expression. That would red the
    # license gate on a package BOTH of whose licenses are on the allow-list.
    #
    # This distribution reaches this repository only on the Python 3.10 floor, via
    # openapi-python-client 0.28.4 - which is exactly why the workflow pins the floor.
    meta = {
        "name": "python-dateutil",
        "version": "2.9.0.post0",
        "license_expression": "",
        "license": "Dual License",
        "classifiers": [
            "License :: OSI Approved :: BSD License",
            "License :: OSI Approved :: Apache Software License",
        ],
    }
    # The FIRST classifier wins, and `source` says the answer came from a classifier rather
    # than from the legacy field - which is what a reviewer needs in order to judge it.
    assert cl._python_signal(meta) == ("BSD License", "Classifier")
    # ...and the whole point: the package passes the gate.
    assert cl.evaluate(cl._python_signal(meta)[0])[0] is True


def test_python_an_unlisted_legacy_non_answer_still_fails_closed() -> None:
    # _LEGACY_NON_ANSWERS is a curated set of OBSERVED values, never a pattern. A legacy
    # field that is unusable in some new way must still surface loudly with its raw text,
    # so a human decides whether it is a fresh non-answer or a license we do not know.
    meta = {
        "name": "hypothetical",
        "version": "1.0",
        "license_expression": "",
        "license": "See LICENSE file",
        "classifiers": ["License :: OSI Approved :: MIT License"],
    }
    assert cl._python_signal(meta) == ("See LICENSE file", "License")
    assert cl.evaluate("See LICENSE file")[0] is False


def test_python_overlong_singleline_legacy_license_falls_back_to_the_classifier() -> None:
    # A single-line legacy License value can STILL be too long to be a plausible license
    # NAME rather than pasted text - the newline check alone would accept it. This pins
    # the length half of the guard independently of the newline half: the string below
    # has no newline at all, so only _MAX_LICENSE_NAME rejects it, and a classifier is
    # present so the assertion also shows the fall-through lands on it rather than on "".
    meta = {
        "name": "whatever",
        "version": "1.0",
        "license_expression": "",
        "license": "A" * (cl._MAX_LICENSE_NAME + 1),
        "classifiers": ["License :: OSI Approved :: MIT License"],
    }
    assert cl._python_signal(meta) == ("MIT License", "Classifier")


def test_python_collector_refuses_an_implausibly_small_distribution_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Mirrors collect_npm's floor guard (test_npm_collector_refuses_an_empty_or_half_installed_tree):
    # a `uv run` that succeeds against a near-empty venv must fail loudly rather than let the
    # checker report a clean bill of health over almost nothing. Faking `uv run`'s stdout
    # rather than actually `uv sync`-ing a throwaway project keeps this test hermetic.
    tiny_dump = '[{"name": "pip", "version": "1.0", "license_expression": "", "license": "MIT", "classifiers": []}]'

    class _FakeCompleted:
        stdout = tiny_dump
        stderr = ""

    def _fake_run(*args: object, **kwargs: object) -> _FakeCompleted:
        return _FakeCompleted()

    monkeypatch.setattr(cl.subprocess, "run", _fake_run)
    with pytest.raises(cl.CollectorError):
        cl.collect_python(tmp_path)


def test_check_separates_violations_from_the_spread() -> None:
    records = [
        cl.Record("npm", "a", "1.0", "MIT", "package.json:license"),
        cl.Record("npm", "b", "2.0", "SSPL-1.0", "package.json:license"),
        cl.Record("python", "c", "3.0", "MIT", "License-Expression"),
    ]
    violations, spread = cl.check(records)
    assert [v.name for v in violations] == ["b"]
    assert spread["MIT"] == 2


def test_an_empty_inventory_is_an_error_not_a_pass(capsys: pytest.CaptureFixture[str]) -> None:
    # THE guard. ArcadeDB's checker once reported success while inspecting a near-empty
    # aggregator pom, and this repository shipped a testpaths setting that excluded every
    # gRPC test while CI stayed green. A checker that silently checks nothing is worse
    # than no checker: it converts an absence of evidence into a passing gate.
    assert cl.report([], cl.Counter()) == 2
    assert "no dependencies" in capsys.readouterr().err.lower()


def test_report_returns_1_and_names_the_offender(capsys: pytest.CaptureFixture[str]) -> None:
    bad = cl.Record("npm", "evil", "6.6.6", "SSPL-1.0", "package.json:license")
    assert cl.report([bad], cl.Counter({"SSPL-1.0": 1})) == 1
    err = capsys.readouterr().err
    # Everything a reviewer needs to act, without opening the tree.
    for expected in ("evil", "6.6.6", "SSPL-1.0", "package.json:license"):
        assert expected in err


def test_report_returns_0_on_a_clean_inventory(capsys: pytest.CaptureFixture[str]) -> None:
    assert cl.report([], cl.Counter({"MIT": 3})) == 0
    assert "3" in capsys.readouterr().out


def test_help_does_not_crash_under_oo() -> None:
    # Regression test for a real latent crash: `argparse.ArgumentParser(description=
    # __doc__.splitlines()[0])` blows up under `-OO`, which strips docstrings and leaves
    # __doc__ as None. Runs the script as a real subprocess because `-OO` is a Python
    # startup flag, not something togglable from inside an already-running interpreter.
    completed = subprocess.run(
        [sys.executable, "-OO", str(_CHECKER), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "AttributeError" not in completed.stderr
