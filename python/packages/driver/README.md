# arcadedb-driver

A Python HTTP client for [ArcadeDB](https://arcadedb.com), generated from ArcadeDB's OpenAPI
contract, with a hand-written facade on top for the data plane, transactions, and the pieces of
the contract the generator cannot model.

Published on PyPI as [`arcadedb-driver`](https://pypi.org/project/arcadedb-driver/), with
attestations: every release is built and published by `publish-python.yml` from a clean checkout of
this repository through PyPI's trusted publishing, with no long-lived token anywhere in the chain.

## Requirements

- Python `>=3.10`.
- An ArcadeDB server at or near the version in the compatibility table below.

## Installation

```bash
pip install arcadedb-driver
```

or, in a [uv](https://docs.astral.sh/uv/) project:

```bash
uv add arcadedb-driver
```

## Quick start

```python
from arcadedb_driver import ArcadeDBServer, basic_auth

with ArcadeDBServer(base_url="http://localhost:2480", auth=basic_auth("root", "playwithdata")) as srv:
    db = srv.db("mydb")
    envelope = db.query(language="sql", command="SELECT FROM Person WHERE age > ?", params={"1": 21})
    print(envelope.result)
```

A bearer token (for example, a session token returned by `/api/v1/login`) works the same way:

```python
from arcadedb_driver import ArcadeDBServer, bearer_auth

with ArcadeDBServer(base_url="http://localhost:2480", auth=bearer_auth("AU-...")) as srv:
    ...
```

The async facade mirrors the sync one method-for-method:

```python
import asyncio

from arcadedb_driver import AsyncArcadeDBServer, basic_auth


async def main() -> None:
    async with AsyncArcadeDBServer(base_url="http://localhost:2480", auth=basic_auth("root", "playwithdata")) as srv:
        db = srv.db("mydb")
        envelope = await db.query(language="sql", command="SELECT FROM Person WHERE age > ?", params={"1": 21})
        print(envelope.result)


asyncio.run(main())
```

## The result envelope, and why `truncated` matters

`query` and `command` do not return bare rows. They return the whole response envelope:

```python
@dataclass(frozen=True, slots=True)
class QueryEnvelope:
    result: list[dict[str, Any]]
    limit: int
    returned: int
    truncated: bool
```

`truncated` is `True` when the server's serializer hit its row cap while a query still had more
rows to write - `result` is then a partial answer, not a short-but-complete one. A caller that
reads `result` and ignores `truncated` can silently work off a partial answer, because a truncated
list and a complete one are indistinguishable by shape alone. Always check `truncated` before
treating `result` as the whole answer, and re-query with a narrower filter or a higher `limit`
when it is `True` - though raising `limit` is not always the fix: a result whose true size exceeds
the server's hard ceiling (`arcadedb.server.httpQueryMaxResultRows`) is refused outright with 413
rather than truncated, so once you are past that ceiling a narrower filter is the only way forward.

`limit` and `truncated` in the envelope above both default when the server's response omits them
(`limit` to `-1`, meaning uncapped; `returned` to `0`; `truncated` to `False`) - `QueryResponse`
has no required fields in the contract, so all four are, strictly, optional on the wire. In
practice the server always sends all four today, but a caller relying on `truncated is False` as
proof of completeness is trusting a client-side default, not a server guarantee.

## Sync and async

`ArcadeDBServer` and `AsyncArcadeDBServer` expose the same methods; the async one awaits them.
Both are context managers - `with` for the sync client, `async with` for the async one - because
each owns an `httpx` client with its own connection pool that must be released. Use the context
manager form where you can; call `close()` (sync) or `await aclose()` (async) yourself otherwise.

```python
srv = ArcadeDBServer(base_url="http://localhost:2480")
try:
    ...
finally:
    srv.close()
```

Both constructors take a `timeout: httpx.Timeout | None = None`, and omitting it disables
timeouts entirely - it is not "use httpx's default" (5 seconds), it is no timeout at all, because
in httpx an explicit `timeout=None` means exactly that. This is deliberate: the generated `Client`
these facades wrap defaults its own timeout to `None` and forwards it the same way, and
`@arcadedb/driver` has no default timeout either, since `fetch` doesn't have one. Pass an
`httpx.Timeout` if you want requests bounded:

```python
srv = ArcadeDBServer(base_url="http://localhost:2480", timeout=httpx.Timeout(5.0))
```

## Transactions

```python
with srv.db("mydb").transaction() as tx:
    tx.command(language="sql", command="INSERT INTO Account SET balance = 100")
    total = tx.query(language="sql", command="SELECT sum(balance) as total FROM Account").result[0]["total"]
```

or, async:

```python
async with srv.db("mydb").transaction() as tx:
    await tx.command(language="sql", command="INSERT INTO Account SET balance = 100")
```

`transaction()` returns a context manager whose `__enter__` (`__aenter__`) begins a server-side
transaction and hands back a SECOND database handle carrying its session id. Every call made
through that `tx` handle - not through the outer `db` object used to open the transaction - takes
part in it; a call made through the outer handle while a transaction is open auto-commits on its
own, outside the transaction, exactly as if no transaction were open at all.

The commit/rollback contract has three clauses:

- The block exits cleanly: the transaction commits.
- The block raises: the transaction rolls back and the block's exception propagates. If that
  rollback itself also fails, the rollback's error is attached as `__cause__` on the block's
  exception rather than replacing it - the block's own error is what the caller asked about - and
  the attach is silently skipped if `__cause__` is already set or if attaching it fails outright.
- The commit itself fails: a best-effort rollback is issued first (its own failure discarded) so
  the server-side session is not left open until `arcadedb.server.httpTxExpireTimeout` reaps it,
  and then the commit's error is re-raised.

## Two error models

The facade methods (`query`, `command`, `transaction`, `list_databases`, `exists`, `server_info`,
`health`, `ready`, the `ts`/`grafana`/`promql` namespaces, ...) raise `ArcadeDBError` on any
non-2xx response:

```python
from arcadedb_driver import ArcadeDBError

try:
    db.query(language="sql", command="SELECT FROM NoSuchType")
except ArcadeDBError as err:
    print(err.status, err.error, err.detail, err.request_id, err.help_)
```

`err.help_` is spelled with a trailing underscore to match the field name on the generated
`ErrorResponse` model, which is reachable through `.raw` - `help` alone would shadow the Python
builtin, and picking a different spelling for the same field on the two error surfaces this
package exposes would be worse than one awkward name used consistently.

`server.raw`, the underlying generated client, does **not** raise. Every one of its operations
returns a `Response` whose `status_code` and `parsed` the caller inspects directly:

```python
from arcadedb_driver._generated.api.database import list_databases

response = list_databases.sync_detailed(client=srv.raw)
if response.status_code >= 300:
    ...  # handle it yourself; srv.raw never raises
```

These are two deliberately different contracts in one package. Use the facade for the ergonomics
of `try`/`except`; use `.raw` when you want to branch on a status code without exceptions. Mixing
assumptions about which one you're calling is the most common way to end up with an unhandled
exception or a silently ignored error.

## `exists` cannot prove absence

```python
present = srv.exists("mydb")
```

`exists` returns `False` both when the database genuinely does not exist and when it exists but
the authenticated caller is not authorized to see it - the server's response does not distinguish
the two cases, so this client cannot either. Do not treat `False` as proof that a database is
absent; it only means "not visible to this caller right now."

## Endpoints this client does not wrap

Two distinct things are true about parts of the contract, and they should not be confused with
each other.

**Not wrapped at all.** `POST /api/v1/batch/{database}` (a jsonl/ndjson/csv body),
`POST /api/v1/ts/{database}/prom/read` and `POST /api/v1/ts/{database}/prom/write` (protobuf
bodies) are endpoints the generator cannot model - it has no way to describe a non-JSON request
body, so it prints a warning, skips the endpoint entirely, and exits 0. Nothing downstream notices
on its own: a skipped endpoint leaves no trace in the generated tree for `git diff` to flag. This
package pins the exact skip set in `scripts/check_codegen_skips.py`, which re-runs the generator
against the committed contract and fails if the set of skipped operations changes - so a future
contract that starts describing `batch` in a way the generator *can* model, or drops one of these
endpoints, cannot pass unnoticed.

`db.ts.write` (`POST /api/v1/ts/{database}/write`, InfluxDB line protocol as `text/plain`) has the
same generator limitation but is hand-written rather than left unwrapped, because a time-series
namespace that could query samples but never ingest any would be an odd thing to ship.

`POST /api/v1/server` (administrative commands) is likewise not wrapped by the facade, and reached
through `.raw` returns a body that does not conform to its declared `QueryResponse` schema
(`{"result": "ok"}` where an array is declared), so the generated model raises on an otherwise
successful call.

**Wrapped, but returning `dict[str, Any]` instead of a generated model.** Unlike `batch`,
`prom/read`, and `prom/write` above, these three routes describe a JSON body the generator *can*
model, and it does generate operation functions and response models for them -
`_generated/api/time_series/query_time_series.py`, `get_time_series_latest.py`, and
`_generated/api/grafana/query_grafana.py` all exist on disk. But `db.ts.query`, `db.ts.latest`,
and `db.grafana.query` do not call any of those generated operations - they are hand-written, and
none of the three generated modules above is imported anywhere outside its own package. Each
method builds the request URL itself and issues it directly through the same pooled httpx client
the generated operations use (`self._client.get_httpx_client()`, or its async twin), returning the
parsed JSON body rather than routing the response through a generated model at all.

The reason is the same in all three: the contract types each of these responses' per-element
scalar values (a timestamp, a numeric measurement, a DataFrame cell) as `"type": "object"`, so the
generated per-element model's `from_dict` calls `dict(value)` on every element - which raises
`TypeError` on an ordinary scalar like a float or an int. Had these methods routed through the
generated operations instead, `db.ts.query`'s `oneOf` response parser would have caught that
`TypeError` and silently fallen through to the aggregated-response model, whose fields are all
optional and so "parses" anything - every raw (non-aggregated) query response would come back
mis-typed as an empty-looking aggregated one instead of raising. `db.ts.latest` and
`db.grafana.query` have no such fallback branch and would simply raise `TypeError` on any real
response. `@arcadedb/driver`, the TypeScript sibling, is unaffected only because `openapi-fetch`
performs no runtime validation of its own - the raw JSON passes through unexamined. Bypassing the
generated operations and returning the parsed body directly is the Python equivalent, and the only
correct behaviour, until the contract is fixed upstream to type these fields correctly; fixing the
contract is also what would let these three methods move onto the generated operations and return
generated models, the same way `db.promql.*` already does - `db.promql.*` is unaffected by any of
this today because its response schemas do not have this shape.

## Contract version and compatibility

This package was generated from `contracts/arcadedb-openapi-26.10.1-SNAPSHOT.json`, recorded in
`pyproject.toml` as `tool.arcadedb.server-version`:

```toml
[tool.arcadedb]
server-version = "26.10.1-SNAPSHOT"
```

| `arcadedb-driver` | ArcadeDB server |
| --- | --- |
| 0.1.0 | 26.9.1 |

This table is a historical record tied to a package version, not something derived automatically:
`scripts/adopt-contract-version.sh` deliberately does not touch it when it retires an old contract
and adopts a new one. Adding a row is a human decision made at release time, not a side effect of
a contract bump.

The client speaks ArcadeDB's HTTP API as described by that contract. Pointing it at a server on a
materially different release may work for the endpoints both versions share, but is not tested or
supported.

## License

Apache-2.0.
