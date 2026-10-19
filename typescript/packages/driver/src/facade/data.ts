import type { Client } from "openapi-fetch";
import type { components, paths } from "../generated/schema.js";
import { ArcadeDBError } from "../errors.js";
import { unwrap } from "../internal/unwrap.js";
import { SESSION_HEADER, buildCommandBody, buildQueryBody, queryTagHeader, statementHeaders } from "../internal/request-body.js";

/** The unwrapped openapi-fetch client, typed against ArcadeDB's OpenAPI schema. */
type RawClient = Client<paths>;

/**
 * Query/command language, as accepted by the `/query` and `/command` endpoints. `"sqlscript"` runs
 * several SQL statements, separated by `;`, as one script.
 */
export type QueryLanguage = "sql" | "sqlscript" | "cypher" | "gremlin" | "graphql" | "mongo";

/** Options for `/command`. `/query` takes the same ones; see `QueryOptions`. */
export interface CommandOptions {
  language: QueryLanguage;
  command: string;
  params?: Record<string, unknown>;
  /**
   * Maximum number of rows to serialize into the response. When omitted, a `LIMIT` stated by the
   * statement is honored as written, and only a statement stating none is capped by the server
   * default (`arcadedb.server.httpQueryDefaultLimit`). Use `-1` for no cap. No value here can widen
   * a single response past the server's hard ceiling (`arcadedb.server.httpQueryMaxResultRows`): a
   * result that would exceed it is refused with 413 instead of being truncated - so raising this
   * is not always the fix for a `truncated: true` response; see `QueryEnvelope`'s doc comment.
   *
   * Up to 0.3.0 this was on `QueryOptions` only, because `/command`'s contract (`CommandRequest`)
   * had no `limit` field, so a `command` past the server default came back truncated with no way to
   * lift the cap (issue #151). The contract now declares it on both.
   */
  limit?: number;
  /**
   * Label for this statement, sent as the `X-ArcadeDB-Query-Tag` header (never in the body). The
   * server lists it under `list queries` and stops it with `terminate queries tag <label>`. Sent
   * only when non-empty. The contract allows at most 256 printable characters; that rule is the
   * server's, and this client does not check it (see `queryTagHeader`). Inside `transaction()`, a
   * statement with no tag of its own inherits the one passed to `transaction`; a tag here
   * overrides it for this statement.
   */
  queryTag?: string;
}

/**
 * Options for `/query`: the same as `CommandOptions`, `limit` included. Kept as its own name
 * because it is public API; it no longer adds anything.
 */
export type QueryOptions = CommandOptions;

/**
 * A transaction isolation level `/begin` accepts. The engine has these two and no others; the
 * server refuses any other value, a differently-cased one included, with 400.
 */
export type IsolationLevel = NonNullable<components["schemas"]["BeginRequest"]["isolationLevel"]>;

/** Options for `ArcadeDBDatabase.transaction`. */
export interface TransactionOptions {
  /**
   * Isolation level the transaction runs at, sent in the begin request's body. Omitted, no body is
   * sent and the server begins at the database's default isolation level. Under `REPEATABLE_READ`,
   * a record the transaction has read keeps the value it was read with even after another session
   * commits a change to it; under `READ_COMMITTED` a second read sees that change.
   */
  isolationLevel?: IsolationLevel;
  /**
   * Label for the whole transaction, sent as `X-ArcadeDB-Query-Tag` on the begin request only. The
   * server applies it to every statement of the session that carries no tag of its own, so
   * `terminate queries tag <label>` stops the transaction's statements; a statement passing its own
   * `queryTag` is labelled with that one instead. See `CommandOptions.queryTag`.
   */
  queryTag?: string;
}

/**
 * The whole result envelope `query`/`command` return - not just the rows.
 *
 * `truncated` means the serializer's row cap stopped mid-serialization with rows still pending,
 * so `result` is incomplete: callers that only read `result` and ignore `truncated` can silently
 * work off a partial answer.
 *
 * `QueryResponse` used to declare no `required` list, so every field was optional on the wire and
 * this client defaulted each one it did not get - `limit` to `-1`, `returned` to `0`, `truncated`
 * to `false` - asserting completeness the server itself never claimed. 26.10.1 made
 * `limit`, `returned` and `truncated` required, and the generated schema now types them as plain
 * `number`/`boolean`. `truncated === false` is therefore a server statement now, not a client-side
 * guess.
 *
 * The `??` fallbacks in `toEnvelope` below are consequently unreachable for those three fields.
 * They are kept rather than deleted because `result` still needs one and because they cost nothing
 * if a later contract loosens the list again; nobody should go looking for the path that triggers
 * them today.
 *
 * `explain` and `explainPlan` carry the execution plan of an EXPLAIN or PROFILE statement (or of
 * any statement run with `profileExecution`). On such an answer `result` is empty and `returned`
 * is `0`: the plan is the answer and the server does not repeat it as a row, so an empty `result`
 * there does not mean "no rows matched". Both keys are present only when the server sent them -
 * absent, not `undefined`-valued, on every other answer.
 */
export type QueryEnvelope<T = unknown> = {
  result: T[];
  limit: number;
  returned: number;
  truncated: boolean;
  /** The execution plan as indented text, one line per step. Present exactly when the server sent one. */
  explain?: string;
  /** The same plan in structured form. Present exactly when `explain` is. */
  explainPlan?: Record<string, unknown>;
};

type QueryResponse = components["schemas"]["QueryResponse"];
type NdJsonQueryEvent = components["schemas"]["NdJsonQueryEvent"];

/**
 * Narrows the `200` payload of `/query` and `/command` to the buffered JSON envelope.
 *
 * `openapi-typescript` unions every media type declared under a response code, and
 * ArcadeData/arcadedb#7306 added `application/x-ndjson` beside `application/json` on
 * these two responses - so `unwrap` now yields `QueryResponse | NdJsonQueryEvent`
 * where it used to yield `QueryResponse` alone.
 *
 * `executeQuery`/`executeCommand` in this file never send `Accept: application/x-ndjson` -
 * `queryStream`/`commandStream` in `facade/stream.ts` do, and decode the response themselves
 * without ever reaching this function. So a real discriminator is still deciding something
 * that, for THIS call site, can only go one way: `{}` satisfies both members (every field of
 * both is optional), and the tie is broken by the encoding this particular call actually
 * requested, not by shape - only a payload carrying a key that exists ONLY on the streaming
 * event is treated as one.
 *
 * The throw is not defensive noise. Without it a stray ndjson line would flow through
 * `toEnvelope` and become `{ result: [], limit: -1, returned: 0, truncated: false }` - an
 * answer asserting completeness that nobody gave. The reason for the throw has changed since
 * this function was written, though: it is no longer "this client never asks for ndjson" (M7
 * added `queryStream`/`commandStream`, which do) but "this call did not ask for it" - the
 * buffered `query`/`command` methods want a `QueryResponse` specifically, and an ndjson event
 * reaching them is still a protocol mismatch worth surfacing rather than silently coercing.
 */
function asQueryResponse(data: QueryResponse | NdJsonQueryEvent): QueryResponse {
  if ("record" in data || "stats" in data || "error" in data) {
    throw new ArcadeDBError(200, {
      error: "the server answered with a streamed ndjson event, but this call requested the buffered application/json response",
    });
  }
  return data as QueryResponse;
}

/**
 * 26.10.1 widened `result` into a union: an array of rows under the default `record`
 * serializer, and one `{ vertices, edges }` object - plus `records` under `studio` - under the two
 * graph serializers. `QueryEnvelope.result` is `T[]` and cannot represent the second shape.
 *
 * The `as T[]` cast below would hide that on its own: it satisfies the compiler on either arm, so
 * a graph object would reach a caller wearing an array's type and fail at their first `.map`. The
 * Python sibling got a compile error from the same contract change - `openapi-python-client` emits
 * a real union where `openapi-typescript` emits one this cast erases - so the check is written out
 * here rather than inherited from the typechecker.
 *
 * `buildQueryBody` never sends `serializer`, so the server always picks `record` and the graph arm
 * cannot arrive. That is a property of today's request builder, not of the contract, which is why
 * this throws rather than asserts.
 */
function toEnvelope<T>(data: QueryResponse): QueryEnvelope<T> {
  const rows = data.result ?? [];
  if (!Array.isArray(rows)) {
    throw new ArcadeDBError(200, {
      error: "the server answered with a graph-serializer result object, but this call expected rows",
      detail:
        "QueryResponse.result is { vertices, edges }, which QueryEnvelope cannot represent. This client never asks for a graph serializer - it sends no 'serializer' field.",
    });
  }
  return {
    result: rows as T[],
    limit: data.limit ?? -1,
    returned: data.returned ?? 0,
    truncated: data.truncated ?? false,
    ...(data.explain !== undefined ? { explain: data.explain } : {}),
    ...(data.explainPlan !== undefined ? { explainPlan: data.explainPlan } : {}),
  };
}

/** Executes `POST /api/v1/query/{database}`. Returns the whole result envelope, unaltered. */
export async function executeQuery<T = unknown>(
  client: RawClient,
  database: string,
  sessionId: string | undefined,
  opts: QueryOptions,
): Promise<QueryEnvelope<T>> {
  const data = await unwrap(
    client.POST("/api/v1/query/{database}", {
      params: { path: { database }, header: statementHeaders(sessionId, opts.queryTag) },
      body: buildQueryBody(opts),
    }),
  );
  return toEnvelope<T>(asQueryResponse(data));
}

/**
 * Executes `POST /api/v1/command/{database}`. Returns the whole result envelope, unaltered.
 *
 * `CommandRequest.language` is a required field in the generated schema,
 * matching the server's `PostCommandHandler`, which rejects a request
 * without it (`requireStringField(requestMap, "language")`).
 */
export async function executeCommand<T = unknown>(
  client: RawClient,
  database: string,
  sessionId: string | undefined,
  opts: CommandOptions,
): Promise<QueryEnvelope<T>> {
  const data = await unwrap(
    client.POST("/api/v1/command/{database}", {
      params: { path: { database }, header: statementHeaders(sessionId, opts.queryTag) },
      body: buildCommandBody(opts),
    }),
  );
  return toEnvelope<T>(asQueryResponse(data));
}

/**
 * Begins a transaction and returns its session id, read from the
 * `arcadedb-session-id` response header (the endpoint answers 204, with no
 * body). Threading that id onto every subsequent call is what keeps those
 * calls inside the transaction; the actual threading happens in the caller.
 *
 * `isolationLevel`, when set, is the request's only body; with none there is no body at all.
 *
 * `queryTag`, when set, goes on this request only. The server applies it to every statement of
 * the session that carries no tag of its own, so it is not repeated on the statements, nor sent
 * on commit/rollback.
 */
export async function beginTransaction(
  client: RawClient,
  database: string,
  queryTag?: string,
  isolationLevel?: IsolationLevel,
): Promise<string> {
  const { error, response } = await client.POST("/api/v1/begin/{database}", {
    params: { path: { database }, header: queryTagHeader(queryTag) },
    body: isolationLevel === undefined ? undefined : { isolationLevel },
  });
  if (!response.ok) {
    throw ArcadeDBError.fromResponse(response, error);
  }
  const sessionId = response.headers.get(SESSION_HEADER);
  if (!sessionId) {
    throw new ArcadeDBError(response.status, { error: "beginTransaction did not return a session id" });
  }
  return sessionId;
}

/** Commits the transaction identified by `sessionId`. The endpoint answers 204 with no body. */
export async function commitTransaction(client: RawClient, database: string, sessionId: string): Promise<void> {
  await unwrap(
    client.POST("/api/v1/commit/{database}", {
      params: { path: { database }, header: { [SESSION_HEADER]: sessionId } },
    }),
  );
}

/** Rolls back the transaction identified by `sessionId`. The endpoint answers 204 with no body. */
export async function rollbackTransaction(client: RawClient, database: string, sessionId: string): Promise<void> {
  await unwrap(
    client.POST("/api/v1/rollback/{database}", {
      params: { path: { database }, header: { [SESSION_HEADER]: sessionId } },
    }),
  );
}
