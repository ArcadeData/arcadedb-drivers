"""Frame building and answer interpretation for the `/ws` insert session, shared by the synchronous
and asynchronous clients in `facade/insert_session.py`.

Everything here is pure: no socket, no clock. The two clients differ only in how they send a frame
and wait for the answer, so the rules that must not drift between them - what a `start` frame
carries, what counts as an error answer, which errors end the session - live in one place.
"""

from __future__ import annotations

import json
import ssl
from collections.abc import Mapping, Sequence
from typing import Any

from ..errors import InsertSessionError

#: What the server answers a `commit`/`rollback` frame on an externally-managed transaction with.
OUTCOME_DETACHED = "detached"

#: The `error` of the frame the server's idle sweep pushes, unsolicited, when it rolls a session
#: back. The session is gone whatever the frame the client was waiting on would have said.
EXPIRED_ERROR = "Insert session expired"


def websocket_url(base_url: str) -> str:
    """`http(s)://host:port[/prefix]` -> `ws(s)://host:port[/prefix]/ws`."""
    base = base_url.rstrip("/")
    if base.startswith("https://"):
        base = "wss://" + base[len("https://") :]
    elif base.startswith("http://"):
        base = "ws://" + base[len("http://") :]
    return base + "/ws"


def tls_context(url: str, verify: str | bool | ssl.SSLContext) -> ssl.SSLContext | None:
    """The `ssl` argument `websockets` wants: `None` for `ws://` (it refuses one there), else a context
    honouring the HTTP client's own `verify_ssl` setting."""
    if not url.startswith("wss://"):
        return None
    if isinstance(verify, ssl.SSLContext):
        return verify
    if verify is False:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    if isinstance(verify, str):
        return ssl.create_default_context(cafile=verify)
    return ssl.create_default_context()


def build_start(
    *,
    database: str,
    session_id: str | None,
    transaction_id: str | None,
    target_type: str | None,
    transaction_mode: str | None,
    conflict_mode: str | None,
    key_columns: Sequence[str] | None,
    update_columns_on_conflict: Sequence[str] | None,
    validate_only: bool,
) -> dict[str, Any]:
    options: dict[str, Any] = {}
    if target_type is not None:
        options["targetType"] = target_type
    if transaction_mode is not None:
        options["transactionMode"] = transaction_mode
    if conflict_mode is not None:
        options["conflictMode"] = conflict_mode
    if key_columns is not None:
        options["keyColumns"] = list(key_columns)
    if update_columns_on_conflict is not None:
        options["updateColumnsOnConflict"] = list(update_columns_on_conflict)
    if validate_only:
        options["validateOnly"] = True

    frame: dict[str, Any] = {"action": "start", "database": database}
    if session_id is not None:
        frame["sessionId"] = session_id
    if transaction_id is not None:
        frame["transactionId"] = transaction_id
    frame["options"] = options
    return frame


def build_chunk(session_id: str, seq: int, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {"action": "chunk", "sessionId": session_id, "chunkSeq": seq, "records": list(records)}


def build_finish(action: str, session_id: str) -> dict[str, Any]:
    return {"action": action, "sessionId": session_id}


def encode(frame: Mapping[str, Any]) -> str:
    return json.dumps(frame)


def ends_session(answer: Mapping[str, Any]) -> bool:
    """Whether an `error` frame means the session is gone, as opposed to a refusal that left it usable.

    Read from `WebSocketInsertProtocol` / `WebSocketInsertSessionManager` / `WebSocketInsertSession`:

    - `"Insert session expired"`: the idle sweep rolled it back.
    - `"Security error"`: the grant was revoked (the session is already rolled back) or the principal
      is no longer valid (every session on the connection rolled back, the connection closing).
    - `"Internal error"`: nothing says what state the session was left in; treated as gone.
    - `"Insert session error"` whose detail says `not found or expired` or `' is closed`: the
      server no longer has it.

    Everything else under `"Insert session error"` - the row cap, `skips ahead`, a malformed record
    or option - is a refusal of that one frame, and the session carries on.
    """
    error = answer.get("error")
    if error in (EXPIRED_ERROR, "Security error", "Internal error"):
        return True
    detail = answer.get("detail")
    return isinstance(detail, str) and ("not found or expired" in detail or "' is closed" in detail)


def interpret(raw: str | bytes, expected: str, session_id: str | None) -> dict[str, Any]:
    """Parses the one answer a frame got and checks it is the one expected.

    Every frame the client sends is answered by exactly one frame, so whatever arrives next IS the
    answer - including an unsolicited `error`, which is reported rather than skipped: whatever the
    frame awaited would have said, the session behind it is gone.

    An `error` frame leaves the session usable (`session_closed=False`) only when it refused that one
    frame; `ends_session` lists the ones that mean the session is gone. Any other action is a
    desynchronised stream, which ends the session.
    """
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    try:
        answer = json.loads(text)
    except ValueError as err:
        raise InsertSessionError(
            f"Unparseable frame on /ws insert session '{session_id}'", session_id=session_id
        ) from err
    if not isinstance(answer, dict):
        raise InsertSessionError(
            f"Unexpected non-object frame on /ws insert session '{session_id}'", session_id=session_id
        )

    if answer.get("result") == "error" or answer.get("action") == "error":
        detail = answer.get("detail") or answer.get("error") or "unknown error"
        raise InsertSessionError(
            f"Error on /ws insert session '{session_id}': {detail}",
            frame=answer,
            session_id=session_id,
            session_closed=ends_session(answer),
        )

    action = answer.get("action", "")
    if action != expected:
        raise InsertSessionError(
            f"Unexpected frame '{action}' on /ws insert session '{session_id}', expected '{expected}'",
            frame=answer,
            session_id=session_id,
        )
    return answer


#: The key this client adds to every `batchAck` it returns. snake_case on purpose: it is derived
#: client-side, not sent by the server, and must not be mistaken for a server field.
WHOLE_CHUNK_FAILED = "whole_chunk_failed"


def is_whole_chunk_failure(ack: Mapping[str, Any]) -> bool:
    """Whether a `batchAck` reports a failure of the chunk's TRANSACTION rather than of its rows.

    Only under `per_batch`, where each chunk commits in a transaction of its own, does a
    commit-time failure (a duplicate key the engine reports on commit, for one) undo the whole
    chunk. (Under `per_stream` nothing commits until the `commit` frame, so the same duplicate is an
    error answering THAT frame, and the session is gone.) The server still answers a normal `batchAck`, but with
    `failed == received` and an `errors` entry whose `rowIndex` is -1, and it does NOT advance its
    watermark: the chunk is to be replayed under the same `chunkSeq`, and a client that moved on
    would be refused for skipping ahead (or, worse, have its next chunk taken as the replay).
    """
    errors = ack.get("errors")
    if not isinstance(errors, list):
        return False
    return any(isinstance(e, Mapping) and e.get("rowIndex") == -1 for e in errors)
