"""Fixtures for the end-to-end suite. Requires Docker."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from typing import TYPE_CHECKING

import httpx
import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

if TYPE_CHECKING:
    from arcadedb_driver import ArcadeDBServer

# Image pin: arcadedata/arcadedb:26.10.1-SNAPSHOT is the release the committed OpenAPI
# contract was generated from, so the client under test and the server it runs
# against are the same version.
#
# That was not true until this pin moved. It sat at 26.8.1 - a release predating
# M0 - and needed a paragraph arguing why a client generated from a newer contract
# still worked against an older server: the M0 changes were documentation fixes to
# spec-generator classes, and the server had always answered 204 with
# arcadedb-session-id and always demanded CommandRequest.language (upstream fix
# #6562). That argument was sound but load-bearing, and it had to be re-made on
# every bump. Pinning to the contract's own release retires it. Move this pin with
# the contract and it stays retired.
DEFAULT_ARCADEDB_IMAGE = "arcadedata/arcadedb:26.10.1-SNAPSHOT"

# ARCADEDB_DOCKER_IMAGE overrides the pin. It exists for the smoke job in
# ArcadeData/arcadedb, which runs against the image built from the server commit
# under review rather than a published tag. The variable name matches the
# one ArcadeDB's own e2e-js suite uses, so the harnesses are driven the same way.
ARCADEDB_IMAGE = os.environ.get("ARCADEDB_DOCKER_IMAGE", DEFAULT_ARCADEDB_IMAGE)

ROOT_PASSWORD = "playwithdata"
DB_NAME = "clienttest"


def _wait_until_ready(base_url: str, timeout: float = 90.0) -> None:
    """Polls /api/v1/ready for a 204.

    testcontainers-python's wait_for_logs matches log OUTPUT, not an HTTP status, so
    readiness is polled here rather than expressed as a built-in wait strategy.
    """
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base_url}/api/v1/ready", timeout=5.0).status_code == 204:
                return
        except httpx.HTTPError as err:  # the port is not accepting connections yet
            last = err
        time.sleep(1.0)
    raise TimeoutError(f"{base_url} was not ready within {timeout}s") from last


@pytest.fixture(scope="session")
def base_url() -> Iterator[str]:
    """Starts an ArcadeDB container and yields its base URL.

    The port is exposed, not bound: a developer machine may already have ArcadeDB on
    host port 2480, so binding directly would clash.
    """
    container = (
        DockerContainer(ARCADEDB_IMAGE)
        .with_env("JAVA_OPTS", f"-Darcadedb.server.rootPassword={ROOT_PASSWORD}")
        .with_exposed_ports(2480)
    )
    with container:
        url = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(2480)}"
        _wait_until_ready(url)
        yield url


@pytest.fixture(scope="session")
def database(base_url: str) -> str:
    """Creates the test database and returns its name.

    No dedicated create-database endpoint exists; database creation goes through the
    generic server-command endpoint (POST /api/v1/server), the same one root-only
    administrative commands share.

    Issued through the pooled httpx client rather than the generated
    `execute_server_command` operation, deliberately: the contract declares this
    endpoint's 200 response as `QueryResponse` (`result: array`), but the real server
    answers an admin command like `create database` with `{"result": "ok"}` - a
    string, not an array. The generated model's `from_dict` iterates that string
    character by character as if it were a list of row objects and raises
    `ValueError`. No facade method wraps this endpoint (see the README's "Endpoints
    this client does not wrap"), so this is the same escape hatch
    `facade/timeseries.py`'s `query`/`latest` use for the same root cause: bypass the
    generated model, check the status code, and do not "fix" this back onto the
    generated operation without fixing the contract first.
    """
    from arcadedb_driver import ArcadeDBServer, basic_auth

    with ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        response = srv.raw.get_httpx_client().post(
            "/api/v1/server",
            json={"command": f"create database {DB_NAME}", "language": "sql"},
        )
        assert response.is_success, response.text
    return DB_NAME


# Image pin: kept independent of `base_url`'s pin above, even though both currently name
# the same tag. They agree because each is pinned to the release its own contract came
# from, not because this one inherits the other's reasoning. The .proto and the OpenAPI
# spec are separate artifacts published from the same server release; if they ever stop
# moving together, these two pins move apart, and nothing here should make that awkward.
GRPC_DEFAULT_ARCADEDB_IMAGE = "arcadedata/arcadedb:26.10.1-SNAPSHOT"
GRPC_ARCADEDB_IMAGE = os.environ.get("ARCADEDB_DOCKER_IMAGE", GRPC_DEFAULT_ARCADEDB_IMAGE)
GRPC_DB_NAME = "clienttestgrpc"


@pytest.fixture(scope="session")
def grpc_server() -> Iterator[tuple[str, str]]:
    """Starts an ArcadeDB container with the gRPC plugin on.

    Yields `(http_base_url, grpc_target)`.

    A SEPARATE container from `base_url`'s, not an extension of it: sharing would let a
    gRPC plugin failure redden the HTTP suite, which has nothing to do with gRPC.

    Two facts that are easy to get wrong and hard to diagnose:

    - The GRPC plugin is NOT enabled by default. `SERVER_PLUGINS` defaults to empty, so
      without the `-Darcadedb.server.plugins=...` below, nothing listens on 50051 at all.
    - `ROOT_PASSWORD` must be at least 8 characters. A shorter one kills the server at
      startup with `ServerSecurityException: User password too short (<8 characters)`,
      and the only visible symptom is a closed port 50051 - which reads exactly like
      "gRPC is broken in this image" rather than "the whole server refused to start".
      `playwithdata` is 12, well clear of the limit.
    """
    container = (
        DockerContainer(GRPC_ARCADEDB_IMAGE)
        .with_env(
            "JAVA_OPTS",
            f"-Darcadedb.server.rootPassword={ROOT_PASSWORD} "
            "-Darcadedb.server.plugins=GRPC:com.arcadedb.server.grpc.GrpcServerPlugin",
        )
        .with_exposed_ports(2480, 50051)
    )
    with container:
        host = container.get_container_host_ip()
        http_url = f"http://{host}:{container.get_exposed_port(2480)}"
        _wait_until_ready(http_url)
        # This line appears only once the GRPC plugin has finished starting and is
        # actually listening, so it is the signal - not the open TCP port. The
        # procedural `wait_for_logs` the brief for this task names is deprecated in
        # the pinned testcontainers version in favour of this structured strategy;
        # the signal it waits for is unchanged.
        LogMessageWaitStrategy(r"gRPC server started on 0\.0\.0\.0:50051").with_startup_timeout(90).wait_until_ready(
            container
        )
        yield http_url, f"{host}:{container.get_exposed_port(50051)}"


@pytest.fixture(scope="session")
def grpc_database(grpc_server: tuple[str, str]) -> str:
    """Creates the gRPC test database and its schema over HTTP.

    No data-plane RPC creates a database and the admin service is out of scope for this
    package, so setup goes over HTTP - exactly as `typescript/e2e/grpc.test.ts` does.
    """
    from arcadedb_driver import ArcadeDBServer, basic_auth

    http_url, _ = grpc_server
    with ArcadeDBServer(base_url=http_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        # Issued through the pooled httpx client rather than the generated
        # `execute_server_command` operation, for the reason the `database` fixture above
        # documents at length: the contract declares this endpoint's 200 response as
        # `QueryResponse` (`result: array`), but the server answers `create database`
        # with `{"result": "ok"}` - a string - and the generated model's `from_dict`
        # iterates that string character by character and raises `ValueError`.
        response = srv.raw.get_httpx_client().post(
            "/api/v1/server",
            json={"command": f"create database {GRPC_DB_NAME}", "language": "sql"},
        )
        assert response.is_success, response.text
        srv.db(GRPC_DB_NAME).command(language="sql", command="CREATE VERTEX TYPE Person IF NOT EXISTS")
    return GRPC_DB_NAME


VECTOR_TYPE = "VectorItem"


def _create_vector_fixture(srv: ArcadeDBServer, db_name: str) -> tuple[str, str]:
    """Creates `VectorItem` with a real `LSM_VECTOR` index, a real `FULL_TEXT` index, and three
    rows of real (small) embeddings - not zero rows.

    The exact DDL was worked out against a live container before any e2e test file was touched,
    with a scratch script, not guessed - see task-4-report.md for the transcript. Two facts cost
    the time: `embedding` must be declared `ARRAY_OF_FLOATS` (the property type an `LSM_VECTOR`
    index accepts), and `CREATE INDEX ... LSM_VECTOR` refuses to run without a `METADATA` clause
    naming `dimensions` - the server names both requirements in its own
    `CommandSQLParsingException` message, which is where `METADATA {"dimensions": 4}` below
    comes from.

    `red-apple`'s embedding is the exact query vector every vector test below searches for, so
    it is always the nearest neighbor (distance 0) and the only row a "known term" full-text
    query can be checked against unambiguously.

    Returns `(vector_index_name, fulltext_index_name)` - `"VectorItem[embedding]"` and
    `"VectorItem[description]"`, ArcadeDB's `Type[property]` naming for an unnamed index.
    """
    db = srv.db(db_name)
    db.command(language="sql", command=f"CREATE DOCUMENT TYPE {VECTOR_TYPE} IF NOT EXISTS")
    db.command(language="sql", command=f"CREATE PROPERTY {VECTOR_TYPE}.name STRING")
    db.command(language="sql", command=f"CREATE PROPERTY {VECTOR_TYPE}.embedding ARRAY_OF_FLOATS")
    db.command(language="sql", command=f"CREATE PROPERTY {VECTOR_TYPE}.description STRING")
    db.command(
        language="sql",
        command=f'CREATE INDEX ON {VECTOR_TYPE} (embedding) LSM_VECTOR METADATA {{"dimensions": 4}}',
    )
    db.command(
        language="sql",
        command=(
            f"INSERT INTO {VECTOR_TYPE} SET name = 'red-apple', embedding = [1,0,0,0], "
            "description = 'a bright red apple'"
        ),
    )
    db.command(
        language="sql",
        command=(
            f"INSERT INTO {VECTOR_TYPE} SET name = 'green-apple', embedding = [0.9,0.1,0,0], "
            "description = 'a crisp green apple'"
        ),
    )
    db.command(
        language="sql",
        command=(
            f"INSERT INTO {VECTOR_TYPE} SET name = 'blue-car', embedding = [0,0,1,0], "
            "description = 'a fast blue car engine'"
        ),
    )
    db.command(language="sql", command=f"CREATE INDEX ON {VECTOR_TYPE} (description) FULL_TEXT")
    return f"{VECTOR_TYPE}[embedding]", f"{VECTOR_TYPE}[description]"


@pytest.fixture(scope="session")
def vector_index(base_url: str, database: str) -> tuple[str, str]:
    """Creates the vector fixture in the HTTP suite's shared database.

    Session-scoped like `database` itself, so the DDL runs once no matter how many tests in
    `test_data_plane.py` use it. Returns `(vector_index_name, fulltext_index_name)`.
    """
    from arcadedb_driver import ArcadeDBServer, basic_auth

    with ArcadeDBServer(base_url=base_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        return _create_vector_fixture(srv, database)


GRPC_TS_TYPE = "GrpcTsPoint"


@pytest.fixture(scope="session")
def grpc_timeseries_type(grpc_server: tuple[str, str], grpc_database: str) -> str:
    """Creates the TIMESERIES type shared by `test_grpc.py`'s and `test_grpc_aio.py`'s
    time-series tests, and returns its name.

    The exact DDL was worked out against a live container before any e2e test file was
    touched (see task-4-report.md for the transcript): `CREATE TIMESERIES TYPE` takes an
    inline `TIMESTAMP` column plus optional `TAGS (...)`/`FIELDS (...)` clauses in the SAME
    statement - there is no other way to declare a type's tag/field columns. Two things that
    look like they should work do not: a plain `CREATE PROPERTY` after the type exists adds
    the column to the schema listing but a time-series write never populates it, and neither
    does `ALTER PROPERTY ... CUSTOM role = "FIELD"` on top of that - both were tried against
    this server and both silently drop the column's values rather than raising. Only naming
    the column inside `CREATE TIMESERIES TYPE` itself makes it a real tag/field column.

    There is no data-plane RPC for DDL, so - exactly like `grpc_database` and
    `grpc_vector_index` - this goes over HTTP; only the writes and reads in the tests
    themselves run over gRPC.
    """
    from arcadedb_driver import ArcadeDBServer, basic_auth

    http_url, _ = grpc_server
    with ArcadeDBServer(base_url=http_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        srv.db(grpc_database).command(
            language="sql",
            command=f"CREATE TIMESERIES TYPE {GRPC_TS_TYPE} TIMESTAMP ts TAGS (sensor STRING) FIELDS (value DOUBLE)",
        )
    return GRPC_TS_TYPE


@pytest.fixture(scope="session")
def grpc_vector_index(grpc_server: tuple[str, str], grpc_database: str) -> tuple[str, str]:
    """Creates the vector fixture over HTTP, in the gRPC suite's shared database.

    There is no data-plane RPC for DDL, so setup goes over HTTP - exactly as `grpc_database`
    already does for `Person`/`BatchPerson` - and only the searches themselves, in
    `test_grpc.py` and `test_grpc_aio.py`, run over gRPC. Returns
    `(vector_index_name, fulltext_index_name)`.
    """
    from arcadedb_driver import ArcadeDBServer, basic_auth

    http_url, _ = grpc_server
    with ArcadeDBServer(base_url=http_url, auth=basic_auth("root", ROOT_PASSWORD)) as srv:
        return _create_vector_fixture(srv, grpc_database)
