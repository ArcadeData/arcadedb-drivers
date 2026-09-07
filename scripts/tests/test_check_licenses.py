"""Tests for scripts/check-licenses.py.

The semantics ARE the product here, so these tests pin them directly rather than
going through the collectors. Every case below corresponds to a decision recorded in
docs/superpowers/specs/2026-09-07-license-compliance-design.md section 7.
"""

from __future__ import annotations

import importlib.util
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
