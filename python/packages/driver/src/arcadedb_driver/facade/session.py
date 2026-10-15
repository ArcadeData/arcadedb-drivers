"""Login sessions and API tokens (issue #123).

The pure half of `ArcadeDBServer`'s and `AsyncArcadeDBServer`'s `login`, `login_as`,
`with_token`, `logout`, `list_sessions` and API-token methods: the public result types, request
building, local validation and response shaping, shared so the sync and async facades cannot
drift. The methods themselves, and their full docstrings, live on the two server classes.

`login`, `logout`, `list_sessions` and the three API-token methods use the generated operations.
`login_as` does not: it must send credentials other than the client's own, and the generated
operations take no per-call headers, while the generated `Client.with_headers` would rewrite the
shared httpx client's headers in place, changing the credentials of every other call. It posts
through the pooled httpx client with a per-request `Authorization` header instead, which httpx
lets override the client's, and parses the answer with the generated `LoginResponse`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .._generated.models.api_token_list import ApiTokenList
from .._generated.models.api_token_list_result_item import ApiTokenListResultItem
from .._generated.models.create_api_token_request import CreateApiTokenRequest
from .._generated.models.create_api_token_response import CreateApiTokenResponse
from .._generated.models.create_api_token_response_result import CreateApiTokenResponseResult
from .._generated.models.error_response import ErrorResponse
from .._generated.models.login_response import LoginResponse
from .._generated.models.session_list import SessionList
from .._generated.types import Unset
from ..errors import ArcadeDBError

LOGIN_URL = "/api/v1/login"

#: Starts every token `POST /api/v1/login` issues ("AU-<server name>-<uuid>"). An API token
#: starts with "at-" instead.
SESSION_TOKEN_PREFIX = "AU-"

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_TOKEN_HASH = re.compile(r"[0-9a-f]{64}")


class NotSessionTokenError(Exception):
    """Raised by `logout` when the client does not present a session token from `login`.

    The server answers 204 to a logout that carries Basic credentials or an API token and
    invalidates nothing, so without this check such a `logout` would report a success that
    never happened. Nothing is sent.
    """


@dataclass(frozen=True)
class LoginResult:
    """What `login` and `login_as` return: the session token and the user it authenticates.

    `token` is prefixed `AU-`; present it with `with_token`. It is a credential: anyone holding
    it acts as `user` until it is logged out or expires, so it is left out of `repr()`.
    """

    token: str = field(repr=False)
    user: str


@dataclass(frozen=True)
class Session:
    """One authentication session as `list_sessions` returns it. These are the server's login
    sessions, not the transaction sessions `transaction()` opens.

    `token` is the session's live bearer token, a credential in its own right, and is left out
    of `repr()`. `issuer` names the cluster node that issued the session when this node holds a
    copy of it, and is `None` for a session this node issued. `elapsed` is the time since the
    session was last used, as the server measured it. `source_ip`, `user_agent`, `country` and
    `city` are `None` when the server has none: `country` and `city` are only known behind a
    proxy that reports them. Times are timezone-aware, in UTC.
    """

    token: str = field(repr=False)
    user: str
    issuer: str | None
    created_at: datetime
    last_update: datetime
    elapsed: timedelta
    source_ip: str | None
    user_agent: str | None
    country: str | None
    city: str | None


@dataclass(frozen=True)
class APIToken:
    """One issued API token, as metadata: the server keeps only the hash, so the token itself
    is never listed.

    `created_at` is when the token was issued, and `expires_at` is `None` for a token that
    never expires; both are timezone-aware, in UTC. `expired` is only reported by
    `list_api_tokens`; `create_api_token` always leaves it `False`. An expired token
    authenticates nobody, but stays listed until the next token change retires it.
    `permissions` takes the shape a group's `types` map takes. `token_hash` is the SHA-256 hex
    of the token, and the argument `delete_api_token` takes; `token_suffix` is the token's last
    characters, to tell two entries apart.
    """

    name: str
    database: str
    created_at: datetime
    expires_at: datetime | None
    expired: bool
    permissions: dict[str, Any]
    token_hash: str
    token_suffix: str


@dataclass(frozen=True)
class CreatedAPIToken(APIToken):
    """What `create_api_token` returns: the token's metadata and, this once, the token itself.

    `token` is the plaintext token, prefixed `at-`. The server stores only its hash, so this is
    the only time it can be read: store it before dropping this value. This client never logs or
    keeps it, and it is left out of `repr()`.
    """

    token: str = field(repr=False, kw_only=True)


def login_result(data: LoginResponse | ErrorResponse | None) -> LoginResult:
    """`data` is what `unwrap` returned for a 2xx answer, which the generated parser only types
    as `LoginResponse`."""
    assert isinstance(data, LoginResponse)
    return LoginResult(token=data.token, user=data.user)


def login_as_response(raw: httpx.Response) -> LoginResult:
    """Raises `ArcadeDBError` unless the server answered 2xx; otherwise parses the body with the
    generated `LoginResponse`."""
    if not 200 <= raw.status_code < 300:
        raise ArcadeDBError.from_httpx_response(raw)
    return login_result(LoginResponse.from_dict(raw.json()))


def authorization_of(headers: Mapping[str, str]) -> str | None:
    """The `Authorization` header's value, matched without regard to case, as httpx does."""
    for key, value in headers.items():
        if key.lower() == "authorization":
            return value
    return None


def with_authorization(headers: Mapping[str, str], value: str) -> dict[str, str]:
    """A copy of `headers` with every spelling of `Authorization` replaced by `value`."""
    copy = {key: v for key, v in headers.items() if key.lower() != "authorization"}
    copy["Authorization"] = value
    return copy


def check_session_token(headers: Mapping[str, str]) -> None:
    """Raises `NotSessionTokenError` unless `headers` present a session token from `login`."""
    if not (authorization_of(headers) or "").startswith(f"Bearer {SESSION_TOKEN_PREFIX}"):
        raise NotSessionTokenError("the client does not present a session token from login()")


def check_token_hash(token_hash: str) -> None:
    """Raises `ValueError` unless `token_hash` is 64 lowercase hexadecimal characters.

    The argument travels in the query string, which proxies and access logs record, and the
    likeliest mistake is passing the plaintext token itself, so it is refused before anything
    is sent and the error does not repeat it.
    """
    if not isinstance(token_hash, str) or not _TOKEN_HASH.fullmatch(token_hash):
        raise ValueError("not an API token hash: want the 64-character SHA-256 hex token_hash, never the token itself")


def _from_millis(ms: int) -> datetime:
    return _EPOCH + timedelta(milliseconds=ms)


def _optional(value: str | Unset | None) -> str | None:
    return None if isinstance(value, Unset) else value


def sessions_from(data: SessionList | ErrorResponse | None) -> list[Session]:
    """`data` is what `unwrap` returned for a 2xx answer, which the generated parser only types
    as `SessionList`; a missing body is an empty list."""
    if data is None:
        return []
    assert isinstance(data, SessionList)
    return [
        Session(
            token=item.token,
            user=item.user,
            issuer=_optional(item.issuer),
            created_at=_from_millis(item.created_at),
            last_update=_from_millis(item.last_update),
            elapsed=timedelta(milliseconds=item.elapsed_ms),
            source_ip=item.source_ip,
            user_agent=item.user_agent,
            country=item.country,
            city=item.city,
        )
        for item in data.result
    ]


def create_api_token_request(
    name: str,
    database: str | None,
    expires_at: datetime | None,
    permissions: Mapping[str, Any] | None,
) -> CreateApiTokenRequest:
    """Raises `ValueError` for an `expires_at` that is naive or not after the Unix epoch.

    A naive datetime would be read in the local timezone of whichever machine runs the client,
    and the server reads an expiry of 0 as "never expires", so a time at or before the epoch
    would issue a token that never expires rather than one already expired.
    """
    body: dict[str, Any] = {"name": name}
    if database is not None:
        body["database"] = database
    if expires_at is not None:
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")
        ms = (expires_at - _EPOCH) // timedelta(milliseconds=1)
        if ms <= 0:
            raise ValueError("expires_at must be after the Unix epoch")
        body["expiresAt"] = ms
    if permissions is not None:
        body["permissions"] = dict(permissions)
    return CreateApiTokenRequest.from_dict(body)


def _api_token(item: ApiTokenListResultItem | CreateApiTokenResponseResult) -> dict[str, Any]:
    return {
        "name": item.name,
        "database": item.database,
        "created_at": _from_millis(item.created_at),
        "expires_at": _from_millis(item.expires_at) if item.expires_at else None,
        "expired": item.expired is True,
        "permissions": item.permissions.to_dict(),
        "token_hash": item.token_hash,
        "token_suffix": item.token_suffix,
    }


def created_api_token_from(data: CreateApiTokenResponse | ErrorResponse | None) -> CreatedAPIToken:
    """`data` is what `unwrap` returned for a 2xx answer, which the generated parser only types
    as `CreateApiTokenResponse`."""
    assert isinstance(data, CreateApiTokenResponse)
    return CreatedAPIToken(**_api_token(data.result), token=data.result.token)


def api_tokens_from(data: ApiTokenList | ErrorResponse | None) -> list[APIToken]:
    """`data` is what `unwrap` returned for a 2xx answer, which the generated parser only types
    as `ApiTokenList`; a missing body is an empty list."""
    if data is None:
        return []
    assert isinstance(data, ApiTokenList)
    return [APIToken(**_api_token(item)) for item in data.result]
