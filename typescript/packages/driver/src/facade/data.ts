import type { Client } from "openapi-fetch";
import type { components, paths } from "../generated/schema.js";
import { ArcadeDBError } from "../errors.js";
import { unwrap } from "../internal/unwrap.js";

/** The unwrapped openapi-fetch client, typed against ArcadeDB's OpenAPI schema. */
type RawClient = Client<paths>;

/** Request header carrying the session id that scopes a call to one transaction. */
const SESSION_HEADER = "arcadedb-session-id";

/** Query/command language, as accepted by the `/query` and `/command` endpoints. */
export type QueryLanguage = "sql" | "cypher" | "gremlin" | "graphql" | "mongo";

/** Options shared by `/command`. `QueryOptions` below adds `limit`, which `/command`'s contract does not have. */
export interface CommandOptions {
  language: QueryLanguage;
  command: string;
  params?: Record<string, unknown>;
}

export interface QueryOptions extends CommandOptions {
  /**
   * Maximum number of rows to serialize into the response. When omitted, a `LIMIT` stated by the
   * query is honored as written, and only a query stating none is capped by the server default
   * (`arcadedb.server.httpQueryDefaultLimit`). Use `-1` for no cap. No value here can widen a
   * single response past the server's hard ceiling (`arcadedb.server.httpQueryMaxResultRows`): a
   * result that would exceed it is refused with 413 instead of being truncated - so raising this
   * is not always the fix for a `truncated: true` response; see `QueryEnvelope`'s doc comment.
   *
   * `/command`'s contract (`CommandRequest`) has no `limit` field, even though the server
   * happens to honor one there too (`PostCommandHandler` reads it as optional) - this is
   * query-only so a typed public option is never shipped with no contract behind it. Adding
   * `limit` to `CommandOptions` later, if the contract grows one, is additive and
   * backwards-compatible.
   */
  limit?: number;
}

/**
 * The whole result envelope `query`/`command` return - not just the rows.
 *
 * `truncated` means the serializer's row cap stopped mid-serialization with rows still pending,
 * so `result` is incomplete: callers that only read `result` and ignore `truncated` can silently
 * work off a partial answer. `QueryResponse` has no `required` list in the generated schema, so
 * every field the server sends is technically optional; when the server omits `truncated`, this
 * client defaults it to `false` (`limit` defaults to `-1`, meaning "uncapped"). Both defaults are
 * the most reassuring possible reading of "the server did not say" - they assert completeness the
 * server itself never claimed. In practice the server always sends both today, but that is a
 * property of the current implementation, not a guarantee this type enforces.
 */
export type QueryEnvelope<T = unknown> = {
  result: T[];
  limit: number;
  returned: number;
  truncated: boolean;
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
 * This client never sends `Accept: application/x-ndjson`, so the ndjson branch is
 * unreachable, and this function's job is to say so out loud. `{}` satisfies both
 * members (every field of both is optional), so the tie is broken by the encoding
 * that was actually requested rather than by shape: only a payload carrying a key
 * that exists ONLY on the streaming event is treated as one.
 *
 * The throw is not defensive noise. Without it a stray ndjson line would flow
 * through `toEnvelope` and become `{ result: [], limit: -1, returned: 0,
 * truncated: false }` - an answer asserting completeness that nobody gave.
 *
 * When the streaming surface lands (drivers#39) this stops being an assertion and
 * becomes the real discriminator between the two encodings.
 */
function asQueryResponse(data: QueryResponse | NdJsonQueryEvent): QueryResponse {
  if ("record" in data || "stats" in data || "error" in data) {
    throw new ArcadeDBError(200, {
      error: "the server answered with a streamed ndjson event, an encoding this client never requests",
    });
  }
  return data as QueryResponse;
}

function toEnvelope<T>(data: QueryResponse): QueryEnvelope<T> {
  return {
    result: (data.result ?? []) as T[],
    limit: data.limit ?? -1,
    returned: data.returned ?? 0,
    truncated: data.truncated ?? false,
  };
}

/**
 * Builds the JSON body for `/command`. Only `params` is cast: it is typed `Record<string, never>`
 * in the generated schema (an openapi-typescript artifact for "untyped object", not a real
 * restriction), so a caller-supplied `Record<string, unknown>` needs a narrow cast to satisfy it.
 * `command` and `language` are passed through with their real types and are NOT cast, so a type
 * change to, or removal of, either required field still fails `tsc` here instead of only failing
 * on the wire.
 *
 * This does NOT extend to a field being removed from the contract outright: this function has an
 * annotated return type, so the object literal handed to `body:` at each call site is not checked
 * as a fresh literal, and excess-property checking never fires for a stray field that no longer
 * exists on the target type.
 */
function buildCommandBody(opts: CommandOptions): { command: string; language: string; params?: Record<string, never> } {
  return {
    command: opts.command,
    language: opts.language,
    params: opts.params as Record<string, never> | undefined,
  };
}

/** Builds the JSON body for `/query`: `buildCommandBody`'s fields plus `limit`, sent only when supplied. */
function buildQueryBody(
  opts: QueryOptions,
): { command: string; language: string; params?: Record<string, never>; limit?: number } {
  return { ...buildCommandBody(opts), limit: opts.limit };
}

/** Attaches the session header when `sessionId` is set; omits it otherwise. */
function sessionHeader(sessionId: string | undefined): { [SESSION_HEADER]?: string } | undefined {
  return sessionId === undefined ? undefined : { [SESSION_HEADER]: sessionId };
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
      params: { path: { database }, header: sessionHeader(sessionId) },
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
      params: { path: { database }, header: sessionHeader(sessionId) },
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
 */
export async function beginTransaction(client: RawClient, database: string): Promise<string> {
  const { error, response } = await client.POST("/api/v1/begin/{database}", {
    params: { path: { database } },
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
