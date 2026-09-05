"""Package marker for the generated protobuf modules.

This is the one HAND-WRITTEN file inside a generated directory in this repository.
protoc emits no package marker of its own, and without this file the generated
modules are not importable as `arcadedb_driver_grpc._generated.*` from an
installed wheel.

It is intentionally empty and must stay that way: the drift gate diffs this whole
directory, so anything that changes here has to be reproducible by
`scripts/generate-grpc.sh`, and this file is not.
"""
