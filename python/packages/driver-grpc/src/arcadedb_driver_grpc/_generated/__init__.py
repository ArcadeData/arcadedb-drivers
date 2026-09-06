"""Package marker for the generated protobuf modules.

This is the one HAND-WRITTEN file inside a generated directory in this repository.
protoc emits no package marker of its own.

It is NOT what makes the directory importable, and the docstring used to overclaim
that it was. Deleting it and re-checking (2026-09) shows the runtime import still
resolves, `mypy --strict` still passes, and hatchling still ships all four generated
modules in the wheel: PEP 420 turns the directory into an implicit NAMESPACE package
and everything downstream keeps working.

What the file buys is that `_generated` is a REGULAR package rather than a namespace
one, which is worth having for two reasons. A namespace package has no `__file__`
and its `__path__` is a live `_NamespacePath` recomputed from `sys.path`, so any
other `arcadedb_driver_grpc/_generated/` directory that turns up on the path silently
MERGES into this one - a contract-versioned tree is the last place that should be
possible. And it states outright that this directory is a shipped part of the
package, rather than leaving that to a build backend's globbing.

It is intentionally empty and must stay that way: the drift gate diffs this whole
directory, so anything that changes here has to be reproducible by
`scripts/generate-grpc.sh`, and this file is not.
"""
