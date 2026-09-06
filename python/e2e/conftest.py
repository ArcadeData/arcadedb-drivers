"""Fixtures for the end-to-end suite. Requires Docker."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator

import httpx
import pytest
from testcontainers.core.container import DockerContainer

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
