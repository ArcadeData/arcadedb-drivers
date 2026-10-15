"""Server administration: databases, users, groups and raw server commands.

The pure half of `ArcadeDBServer`'s and `AsyncArcadeDBServer`'s administration methods: request
building, name validation and response shaping, shared so the sync and async facades cannot
drift. The methods themselves, and their full docstrings, live on the two server classes.

Users and groups go through their dedicated endpoints (`/api/v1/server/users`,
`/api/v1/server/groups`) and the generated operations, whose JSON bodies the generated models
build and parse correctly.

Databases have no dedicated endpoint, so `create_database` / `drop_database` send a command
through `POST /api/v1/server`, and that endpoint is called through the generated client's own
pooled httpx client rather than the generated `execute_server_command` operation. The contract
declares its 200 body as `QueryResponse` with an array `result`, but an administrative command
answers `{"result": "ok"}`, and the generated `from_dict` iterates that string as if it were a
list of rows and raises `ValueError` (see `python/CLAUDE.md`, "Two contract defects"). Do not
route `server_command` back through the generated operation until the contract is fixed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from .._generated.models.create_user_request import CreateUserRequest
from .._generated.models.error_response import ErrorResponse
from .._generated.models.group_list import GroupList
from .._generated.models.save_group_request import SaveGroupRequest
from .._generated.models.update_user_request import UpdateUserRequest
from .._generated.models.user_list import UserList
from ..errors import ArcadeDBError

SERVER_COMMAND_URL = "/api/v1/server"


def check_database_name(name: str) -> None:
    """Raises `ValueError` for a name the server would silently change.

    The server trims the name it reads out of `create database <name>`, so " db" would create
    or drop "db" rather than the database the caller named. An empty name is refused too.
    """
    if not name or name.strip() != name:
        raise ValueError(f"database name {name!r} is empty or has leading or trailing white space")


def server_command_payload(command: str) -> dict[str, str]:
    """The `POST /api/v1/server` body. `language` is required by the contract's
    `CommandRequest` and ignored by the server for a server command."""
    return {"command": command, "language": "sql"}


def server_command_response(raw: httpx.Response) -> dict[str, Any]:
    """Raises `ArcadeDBError` unless the server answered 2xx; otherwise returns the parsed JSON
    body unaltered. Bypasses the generated response model - see the module docstring."""
    if not 200 <= raw.status_code < 300:
        raise ArcadeDBError.from_httpx_response(raw)
    body: dict[str, Any] = raw.json()
    return body


def create_user_request(name: str, password: str, databases: Mapping[str, Sequence[str]] | None) -> CreateUserRequest:
    body: dict[str, Any] = {"name": name, "password": password}
    if databases is not None:
        body["databases"] = {db: list(groups) for db, groups in databases.items()}
    return CreateUserRequest.from_dict(body)


def update_user_request(password: str | None, databases: Mapping[str, Sequence[str]] | None) -> UpdateUserRequest:
    body: dict[str, Any] = {}
    if password is not None:
        body["password"] = password
    if databases is not None:
        body["databases"] = {db: list(groups) for db, groups in databases.items()}
    return UpdateUserRequest.from_dict(body)


def save_group_request(
    database: str,
    name: str,
    access: Sequence[str] | None,
    read_timeout: int | None,
    result_set_limit: int | None,
    types: Mapping[str, Any] | None,
) -> SaveGroupRequest:
    body: dict[str, Any] = {"database": database, "name": name}
    if access is not None:
        body["access"] = list(access)
    if read_timeout is not None:
        body["readTimeout"] = read_timeout
    if result_set_limit is not None:
        body["resultSetLimit"] = result_set_limit
    if types is not None:
        body["types"] = dict(types)
    return SaveGroupRequest.from_dict(body)


def users_from(data: UserList | ErrorResponse) -> list[dict[str, Any]]:
    """Each user as a plain `{"name": ..., "databases": {...}}` dict. `data` is what `unwrap`
    returned for a 2xx answer, which the generated parser only types as `UserList`."""
    assert isinstance(data, UserList)
    return [user.to_dict() for user in data.result]


def groups_from(data: GroupList | ErrorResponse) -> dict[str, dict[str, dict[str, Any]]]:
    """Group definitions as plain dicts, keyed by database name and then by group name. `data`
    is what `unwrap` returned for a 2xx answer, which the generated parser only types as
    `GroupList`."""
    assert isinstance(data, GroupList)
    databases: dict[str, Any] = data.result.to_dict()["databases"]
    return {db: dict(entry["groups"]) for db, entry in databases.items()}
