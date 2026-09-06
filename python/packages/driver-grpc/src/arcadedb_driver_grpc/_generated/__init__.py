"""Package marker for the generated protobuf modules.

This is the one HAND-WRITTEN file inside a generated directory in this repository.
protoc emits no package marker of its own.

It is not required for the runtime import to resolve, for `mypy --strict` to pass, or
for hatchling to ship all four generated modules in the wheel. Deleting it and
re-checking (2026-09) confirms all three still work: PEP 420 turns the directory into
an implicit NAMESPACE package, and everything downstream keeps resolving through it.

What the file buys, instead, is that `_generated` is a REGULAR package rather than a
namespace one: a fixed, single-element `__path__` (a plain `list`) and a real
`__file__`, in place of the `__file__ is None` and live `_NamespacePath` a namespace
portion gets. It also states outright, in the source tree, that this directory is a
shipped part of the package, rather than leaving that to a build backend's globbing.

It is intentionally empty and must stay that way: the drift gate diffs this whole
directory, so anything that changes here has to be reproducible by
`scripts/generate-grpc.sh`, and this file is not.
"""
