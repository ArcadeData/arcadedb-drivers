"""A hand-written list of 44 RPC names is exactly the kind of prose that rots silently on the
next contract bump, and a stale list is worse than none because a reader trusts it. This pins the
README's enumeration against the GENERATED stub's own method set: a contract bump regenerates
`arcadedb_server_pb2`, and this is what makes the README disagree with it loudly instead of
quietly.
"""

from __future__ import annotations

import re
from pathlib import Path

from arcadedb_driver_grpc._generated import arcadedb_server_pb2 as pb2

README_PATH = Path(__file__).parent.parent / "README.md"
MARKER_BEGIN = "<!-- admin-rpcs:begin -->"
MARKER_END = "<!-- admin-rpcs:end -->"


def _documented_admin_rpc_names() -> list[str]:
    """Every backtick-delimited token between the admin-rpcs markers is one RPC name (see the
    README's "The 44 RPCs" section). Group labels in the table's first column are deliberately
    left unbackticked, so this needs no Markdown table parser - just this one regex.
    """
    text = README_PATH.read_text()
    start = text.index(MARKER_BEGIN)
    end = text.index(MARKER_END)
    return re.findall(r"`([A-Za-z]+)`", text[start:end])


def _generated_admin_rpc_names() -> list[str]:
    """The admin stub's own RPC names, read from the generated pb2 descriptor - not the
    `.proto` contract - so a contract bump that regenerates the stub is what this test actually
    reacts to. Reading the `.proto` instead would let this pass through a bump that changed the
    proto but, for whatever reason, never reached the generated module.
    """
    service = pb2.DESCRIPTOR.services_by_name["ArcadeDbAdminService"]
    return [method.name for method in service.methods]


def test_readme_documents_exactly_the_generated_stubs_rpcs() -> None:
    documented = _documented_admin_rpc_names()
    generated = _generated_admin_rpc_names()
    documented_set = set(documented)
    generated_set = set(generated)

    missing = sorted(generated_set - documented_set)
    extra = sorted(documented_set - generated_set)

    assert not missing, f"README is missing these RPCs: {missing}"
    assert not extra, f"README documents RPCs that don't exist on the generated stub: {extra}"


def test_readme_lists_each_rpc_exactly_once() -> None:
    documented = _documented_admin_rpc_names()
    duplicates = sorted({name for name in documented if documented.count(name) > 1})
    assert not duplicates, f"README lists these RPCs more than once: {duplicates}"


def test_the_contract_still_declares_44_admin_rpcs() -> None:
    """Not a README check - the two tests above already pin the README against the generated
    stub's *names*, inside the marker region only. This one is blind to the README entirely and
    exists solely to catch the day this number moves, because roughly twenty other places state
    "44" or "42 of 44" as prose OUTSIDE that marker region, where nothing else here re-derives it
    from the contract. If this fails, the contract's admin RPC count changed - update every one of:
    both READMEs (the "The 44 RPCs" heading and surrounding prose, both packages), the
    `ArcadeDBGrpcClient`/`AsyncArcadeDBGrpcClient` class docstrings in `__init__.py` and `aio.py`,
    `errors.py`'s `InsecureChannelError` docstring, the equivalent docstrings and guard message in
    `typescript/packages/driver-grpc/src/index.ts`, and the admin-service bullets in
    `typescript/CLAUDE.md` and `python/CLAUDE.md`.
    """
    count = len(_generated_admin_rpc_names())
    assert count == 44, (
        f"ArcadeDbAdminService now declares {count} RPCs, not 44. Update every '44'/'42 of 44' "
        "statement: both READMEs, the class docstrings in __init__.py and aio.py, errors.py, "
        "typescript/src/index.ts's docstrings and guard message, and both CLAUDE.md files."
    )
