import createOpenApiClient from "openapi-fetch";
import type { Client, Middleware } from "openapi-fetch";
import type { components, paths } from "./generated/schema.js";
import { ArcadeDBError } from "./errors.js";
import { unwrap } from "./internal/unwrap.js";
import { beginTransaction, commitTransaction, executeCommand, executeQuery, rollbackTransaction } from "./facade/data.js";
import type { CommandOptions, QueryEnvelope, QueryOptions, TransactionOptions } from "./facade/data.js";
import { commandStream, queryStream } from "./facade/stream.js";
import type { NdJsonQueryEvent } from "./facade/stream.js";
import { batchLoad, batchLoadStream } from "./facade/batch.js";
import { basicAuth, bearerAuth } from "./auth.js";
import type { APIToken, CreateAPITokenOptions, CreatedAPIToken, LoginResult, Session } from "./facade/session.js";
import type {
  CreateUserOptions,
  GroupDefinition,
  SaveGroupOptions,
  ServerUser,
  UpdateUserOptions,
} from "./facade/admin.js";
import type { BatchLoadArgs, BatchSummary, NdJsonBatchEvent } from "./facade/batch.js";
import type {
  GrafanaQueryOptions,
  GrafanaQueryResponse,
  PromQLDataResponse,
  PromQLLabelValuesOptions,
  PromQLLabelsResponse,
  PromQLQueryOptions,
  PromQLQueryRangeOptions,
  PromQLSeriesOptions,
  PromQLSeriesResponse,
} from "./facade/dashboards.js";
import type {
  ListQueriesOptions,
  OpenTransaction,
  ProgressResponse,
  RunningQuery,
  TerminateOptions,
  TerminateResult,
} from "./facade/running.js";
import type { InsertSession, InsertSessionContext, InsertSessionOptions, WebSocketConstructor } from "./facade/insert-session.js";
import type { TimeSeriesQueryOptions, TimeSeriesQueryResult, TimeSeriesWriteOptions } from "./facade/timeseries.js";
import type {
  FullTextSearchOptions,
  FullTextSearchResult,
  HybridSearchOptions,
  HybridSearchResult,
  VectorSearchOptions,
  VectorSearchResult,
} from "./facade/vector.js";

export { ArcadeDBError, NotSessionTokenError, TimeSeriesWriteError, isQueryTerminated } from "./errors.js";
export type {
  ListQueriesOptions,
  OpenTransaction,
  ProgressResponse,
  QueryStatus,
  RunningQuery,
  TerminateOptions,
  TerminateResult,
} from "./facade/running.js";
export type { ArcadeDBErrorExtras } from "./errors.js";
export { basicAuth, bearerAuth } from "./auth.js";
export type { APIToken, CreateAPITokenOptions, CreatedAPIToken, LoginResult, Session } from "./facade/session.js";
export type { Middleware } from "openapi-fetch";
export type { CommandOptions, QueryEnvelope, QueryLanguage, QueryOptions, TransactionOptions } from "./facade/data.js";
export type { NdJsonQueryEvent } from "./facade/stream.js";
export type {
  CreateUserOptions,
  GroupDefinition,
  SaveGroupOptions,
  ServerUser,
  UpdateUserOptions,
  UserDatabases,
} from "./facade/admin.js";
export type {
  BatchAck,
  CommittedFrame,
  InsertConflictMode,
  InsertRecord,
  InsertRowError,
  InsertSession,
  InsertSessionContext,
  InsertSessionOptions,
  InsertSummary,
  InsertTransactionMode,
  WebSocketConstructor,
  WebSocketEventLike,
  WebSocketLike,
} from "./facade/insert-session.js";
export type { BatchLoadArgs, BatchOptions, BatchSummary, NdJsonBatchEvent } from "./facade/batch.js";
export type { EdgeRow, VertexRow } from "./internal/batch-rows.js";
export type {
  GrafanaQueryOptions,
  GrafanaQueryResponse,
  PromQLDataResponse,
  PromQLLabelValuesOptions,
  PromQLLabelsResponse,
  PromQLMatrixSeries,
  PromQLQueryOptions,
  PromQLQueryRangeOptions,
  PromQLResult,
  PromQLSeriesOptions,
  PromQLSeriesResponse,
  PromQLVectorSample,
} from "./facade/dashboards.js";
export type { TimeSeriesQueryOptions, TimeSeriesQueryResult, TimeSeriesWriteOptions } from "./facade/timeseries.js";
export type { VectorSearchOptions, VectorSearchResult, HybridSearchOptions, HybridSearchResult, FullTextSearchOptions, FullTextSearchResult } from "./facade/vector.js";
// Type-only: these classes are constructed exclusively through ArcadeDBDatabase.ts/.grafana/.promql/.vector,
// which is what threads them the RawClient they need. Exporting the type (not the class as a
// constructible value) lets a consumer name `db.grafana`'s type in their own code without being
// able to `new` one directly, bypassing that plumbing.
export type { TimeSeriesNamespace, GrafanaNamespace, PromQLNamespace };
export type { VectorNamespace };

/** The unwrapped openapi-fetch client, typed against ArcadeDB's OpenAPI schema. */
type RawClient = Client<paths>;

/**
 * Ingests and queries samples in a time-series type - the `db.ts` namespace.
 *
 * Each method dynamically imports `facade/timeseries.js` on first call rather than `index.ts`
 * statically importing it. `db.ts`/`db.grafana`/`db.promql` are dashboard/ingest namespaces, not
 * the data plane (`query`/`command`/`transaction`); every method here was already
 * `Promise`-returning, so deferring the import to inside the method body is invisible to callers -
 * `db.ts` itself stays a synchronous property access, only the first call pays the import cost. This
 * is what lets a bundler that supports code-splitting keep `facade/timeseries.js` out of a chunk that
 * only reaches `query`/`command`/`transaction`; see `test/treeshake.test.ts`.
 */
class TimeSeriesNamespace {
  constructor(
    private readonly client: RawClient,
    private readonly database: string,
  ) {}

  /** Ingests samples in InfluxDB Line Protocol. */
  async write(opts: TimeSeriesWriteOptions): Promise<void> {
    const { writeTimeSeries } = await import("./facade/timeseries.js");
    return writeTimeSeries(this.client, this.database, opts);
  }

  /** Queries samples, optionally aggregated into buckets. */
  async query(opts: TimeSeriesQueryOptions): Promise<TimeSeriesQueryResult> {
    const { queryTimeSeries } = await import("./facade/timeseries.js");
    return queryTimeSeries(this.client, this.database, opts);
  }
}

/**
 * Grafana panel queries over a time-series type - the `db.grafana` namespace.
 *
 * Lazily imports `facade/dashboards.js`; see `TimeSeriesNamespace`'s doc comment for why.
 */
class GrafanaNamespace {
  constructor(
    private readonly client: RawClient,
    private readonly database: string,
  ) {}

  /** Executes one query per `targets` entry, returning DataFrames keyed by `refId`. */
  async query(opts: GrafanaQueryOptions): Promise<GrafanaQueryResponse> {
    const { queryGrafana } = await import("./facade/dashboards.js");
    return queryGrafana(this.client, this.database, opts);
  }
}

/**
 * A Prometheus-compatible query surface over a time-series type - the `db.promql` namespace.
 *
 * Lazily imports `facade/dashboards.js`; see `TimeSeriesNamespace`'s doc comment for why.
 */
class PromQLNamespace {
  constructor(
    private readonly client: RawClient,
    private readonly database: string,
  ) {}

  /** Evaluates a PromQL expression at one instant. */
  async query(opts: PromQLQueryOptions): Promise<PromQLDataResponse> {
    const { queryPromQL } = await import("./facade/dashboards.js");
    return queryPromQL(this.client, this.database, opts);
  }

  /** Evaluates a PromQL expression at every step across a range. */
  async queryRange(opts: PromQLQueryRangeOptions): Promise<PromQLDataResponse> {
    const { queryRangePromQL } = await import("./facade/dashboards.js");
    return queryRangePromQL(this.client, this.database, opts);
  }

  /** Lists every label name present in the database, sorted, always including `__name__`. */
  async labels(): Promise<PromQLLabelsResponse> {
    const { labelsPromQL } = await import("./facade/dashboards.js");
    return labelsPromQL(this.client, this.database);
  }

  /** Lists the values of one label over an optional time range; `"__name__"` lists the time-series type names. */
  async labelValues(name: string, opts?: PromQLLabelValuesOptions): Promise<PromQLLabelsResponse> {
    const { labelValuesPromQL } = await import("./facade/dashboards.js");
    return labelValuesPromQL(this.client, this.database, name, opts);
  }

  /** Returns the label sets of the series matching the given `match[]` selectors. */
  async series(opts: PromQLSeriesOptions): Promise<PromQLSeriesResponse> {
    const { seriesPromQL } = await import("./facade/dashboards.js");
    return seriesPromQL(this.client, this.database, opts);
  }
}

/**
 * Vector, hybrid and full-text retrieval - the `db.vector` namespace.
 *
 * Each method dynamically imports `facade/vector.js` on first call, for the reason
 * `TimeSeriesNamespace`'s doc comment gives: `db.vector` stays a synchronous property access, only
 * the first call pays the import cost, and a code-splitting bundler can keep `facade/vector.js` out
 * of a chunk that only reaches the data plane. `test/treeshake.test.ts` is what holds that.
 */
class VectorNamespace {
  constructor(
    private readonly client: RawClient,
    private readonly database: string,
  ) {}

  /**
   * kNN over a named vector index.
   *
   * `T`, a hit's `properties` type, defaults to `Record<string, unknown>` and is forwarded
   * straight to {@link VectorSearchResult} - see that type's doc comment, and
   * `WithTypedProperties` in `facade/vector.ts`, for why the default is what stops an unchecked
   * `hit.properties.someField` read from compiling, and how to pass a real row type instead:
   * `db.vector.search<{ name: string }>(...)`.
   */
  async search<T = Record<string, unknown>>(opts: VectorSearchOptions): Promise<VectorSearchResult<T>> {
    const { vectorSearch } = await import("./facade/vector.js");
    return vectorSearch<T>(this.client, this.database, opts);
  }

  /** Combined vector and full-text retrieval, fused server-side. `T` is as {@link VectorNamespace.search}'s. */
  async hybrid<T = Record<string, unknown>>(opts: HybridSearchOptions): Promise<HybridSearchResult<T>> {
    const { hybridSearch } = await import("./facade/vector.js");
    return hybridSearch<T>(this.client, this.database, opts);
  }

  /** Full-text search over a named index or type. `T` is as {@link VectorNamespace.search}'s. */
  async fulltext<T = Record<string, unknown>>(opts: FullTextSearchOptions): Promise<FullTextSearchResult<T>> {
    const { fullTextSearch } = await import("./facade/vector.js");
    return fullTextSearch<T>(this.client, this.database, opts);
  }
}

/**
 * A single database reached through an `ArcadeDBServer`. Constructed by
 * `ArcadeDBServer.db()`.
 *
 * When held via `transaction()`'s callback parameter, `sessionId` is set and
 * every `query`/`command` call made through this instance carries it on the
 * `arcadedb-session-id` header, which is what keeps those calls inside the
 * transaction rather than auto-committing individually.
 */
/**
 * Loads `facade/running.js` on first use. One loader shared by the six methods that need it, rather
 * than an `import()` in each, because every byte of `ArcadeDBServer` lands in the eager chunk
 * `test/treeshake.test.ts` caps.
 */
const loadRunning = () => import("./facade/running.js");

export class ArcadeDBDatabase {
  private _ts: TimeSeriesNamespace | undefined;
  private _grafana: GrafanaNamespace | undefined;
  private _promql: PromQLNamespace | undefined;
  private _vector: VectorNamespace | undefined;

  constructor(
    private readonly client: RawClient,
    readonly name: string,
    private readonly sessionId?: string,
    private readonly insertContext?: InsertSessionContext,
  ) {}

  /** Ingests and queries samples in a time-series type. Loaded on first use; see `TimeSeriesNamespace`. */
  get ts(): TimeSeriesNamespace {
    return (this._ts ??= new TimeSeriesNamespace(this.client, this.name));
  }

  /** Grafana panel queries over a time-series type. Loaded on first use; see `GrafanaNamespace`. */
  get grafana(): GrafanaNamespace {
    return (this._grafana ??= new GrafanaNamespace(this.client, this.name));
  }

  /** A Prometheus-compatible query surface over a time-series type. Loaded on first use; see `PromQLNamespace`. */
  get promql(): PromQLNamespace {
    return (this._promql ??= new PromQLNamespace(this.client, this.name));
  }

  /** Vector, hybrid and full-text retrieval. Loaded on first use; see `VectorNamespace`. */
  get vector(): VectorNamespace {
    return (this._vector ??= new VectorNamespace(this.client, this.name));
  }

  /**
   * Lists the long-running maintenance operations running on this server for this database, with
   * their step-by-step progress; `result` is empty when none is. The server reads a lock-free
   * snapshot, so polling at any rate cannot interfere with the operation being watched. Never
   * forwarded to the cluster leader. Throws `ArcadeDBError` on a non-2xx status.
   */
  async progress(): Promise<ProgressResponse> {
    return (await loadRunning()).progress(this.client, this.name);
  }

  /** Executes a read-or-write query and returns the whole result envelope - not just `result`. */
  async query<T = unknown>(opts: QueryOptions): Promise<QueryEnvelope<T>> {
    return executeQuery<T>(this.client, this.name, this.sessionId, opts);
  }

  /** Executes a command and returns the whole result envelope - not just `result`. */
  async command<T = unknown>(opts: CommandOptions): Promise<QueryEnvelope<T>> {
    return executeCommand<T>(this.client, this.name, this.sessionId, opts);
  }

  /**
   * Opens a duplex insert session on the server's `/ws` endpoint: send chunks, see each
   * acknowledgement, then decide whether to `commit()` or `rollback()`. See `InsertSession` and
   * the README for the protocol rules and failure modes. Loaded on first use, like `db.ts`.
   *
   * On the `tx` handle of `transaction()`, `{ joinTransaction: true }` writes into that
   * transaction instead of a server-managed one.
   */
  async insertSession(opts: InsertSessionOptions = {}): Promise<InsertSession> {
    const { openInsertSession } = await import("./facade/insert-session.js");
    return openInsertSession(this.insertContext, this.name, this.sessionId, opts);
  }

  /**
   * Streams a read-or-write query as `application/x-ndjson` instead of buffering the whole
   * result server-side first. Yields one `NdJsonQueryEvent` per line - `record` rows in order,
   * then a `stats` trailer carrying the same `limit`/`returned`/`truncated` `query` reports at
   * the top of its envelope. An in-band `error` event raises `ArcadeDBError` instead of being
   * yielded; see `facade/stream.ts` for why the contract puts that failure in band.
   */
  queryStream(opts: QueryOptions): AsyncGenerator<NdJsonQueryEvent> {
    return queryStream(this.client, this.name, this.sessionId, opts);
  }

  /**
   * Streams a command as `application/x-ndjson`. As {@link ArcadeDBDatabase.queryStream}, but for
   * `/command`. Only a READ-ONLY statement can stream: a mutating one (`UPDATE`, `INSERT`, DDL,
   * `RETURN AFTER` included) is refused with an `ArcadeDBError` (HTTP 400) before it produces a
   * row, because a streamed response starts sending rows before the transaction commits, and that
   * commit can still roll back. Use `command` for a mutating statement.
   */
  commandStream(opts: CommandOptions): AsyncGenerator<NdJsonQueryEvent> {
    return commandStream(this.client, this.name, this.sessionId, opts);
  }

  /**
   * Bulk-loads vertices and edges via `POST /api/v1/batch/{database}`, buffering the whole
   * response before returning. `serializeRows` (via `args.vertices`/`args.edges`) always emits
   * every vertex before any edge, because the server resolves an edge's `from`/`to` against
   * temporary ids declared earlier in the SAME payload only.
   *
   * A load is NOT atomic: the server commits every `options.commitEvery` records, so a failure
   * partway through leaves earlier chunks durably committed - `ArcadeDBError` thrown from a
   * failed load still corresponds to real, already-durable data. Because temporary ids are not
   * keys, retrying the whole payload after such a failure duplicates whatever already committed
   * rather than resuming cleanly. Use `batchLoadStream` when the caller needs to see how far a
   * load got before it failed.
   */
  async batchLoad(args: BatchLoadArgs): Promise<BatchSummary> {
    return batchLoad(this.client, this.name, args);
  }

  /**
   * Streams the same bulk load as `batchLoad`, but as `application/x-ndjson`: a `progress` event
   * at every vertex commit and every `options.commitEvery` edges, then exactly one `summary` or
   * `error` event carrying the same object the buffered call would otherwise have returned. An
   * in-band `error` event raises `ArcadeDBError` instead of being yielded - see `facade/batch.ts`'s
   * `raiseOnErrorEvent` for why the two ways a load can fail (before vs. after the first
   * acknowledgement) both end up on this one throwing path. A `progress` event's `idMapping` is
   * only the fragment that chunk resolved - it is never merged across events, so a caller that
   * needs the whole mapping must concatenate it themselves as they receive it.
   */
  batchLoadStream(args: BatchLoadArgs): AsyncGenerator<NdJsonBatchEvent> {
    return batchLoadStream(this.client, this.name, args);
  }

  /**
   * Runs `fn` inside a server-side transaction. `fn` is handed a database
   * handle scoped to the transaction's session id, so every call it makes
   * through that handle - not the outer `this` - takes part in the
   * transaction. Commits when `fn` resolves and returns its value; rolls
   * back and re-throws the original error when `fn` throws or rejects,
   * synchronously or otherwise.
   *
   * Two failure paths beyond `fn` throwing are handled explicitly so the
   * server-side session is never left open and the caller's real error is
   * never swallowed:
   *  - if `fn` throws and the resulting rollback itself fails, the
   *    rollback's error is attached as `cause` on `fn`'s error (when that
   *    error is an `Error`) rather than replacing it - `fn`'s error is what
   *    the caller asked about. The attach is skipped when `fn`'s error
   *    already has a `cause` (a caller-set causal chain is never
   *    overwritten) and is swallowed if it throws (a frozen/non-extensible
   *    error - some libraries intern sentinel errors - cannot take a new
   *    property in strict-mode ESM; `fn`'s error still gets re-thrown as
   *    itself either way).
   *  - if the commit itself fails, a best-effort rollback is issued to
   *    release the session (its own failure is swallowed - the commit
   *    error is what the caller needs to see) before the commit error is
   *    re-thrown. Without this, a failed commit leaves the session open
   *    server-side until `arcadedb.server.httpSessionExpireTimeout` reaps it.
   *
   * `opts.queryTag` labels the transaction: it is sent on the begin request only, and the server
   * applies it to every statement that carries no tag of its own.
   *
   * A rollback cannot undo a statement that published a commit while it ran - an explicit
   * `BATCH n` boundary, or a statement with its own `COMMIT`. The server marks such a response
   * `arcadedb-session-partial-commit: true`; this method does not surface that header (reach it
   * through `raw`), so a caller who replays a whole `transaction` block on conflict must not do so
   * for a body containing such statements - part of it is already durable.
   */
  async transaction<T>(fn: (tx: ArcadeDBDatabase) => Promise<T>, opts: TransactionOptions = {}): Promise<T> {
    const sessionId = await beginTransaction(this.client, this.name, opts.queryTag);
    const tx = new ArcadeDBDatabase(this.client, this.name, sessionId, this.insertContext);
    let result: T;
    try {
      result = await fn(tx);
    } catch (err) {
      try {
        await rollbackTransaction(this.client, this.name, sessionId);
      } catch (rollbackErr) {
        if (err instanceof Error) {
          try {
            if (err.cause === undefined) {
              err.cause = rollbackErr;
            }
          } catch {
            // err is frozen/non-extensible - assigning `cause` would throw in strict-mode ESM.
            // The rollback failure is dropped in that case; `err` is what the caller asked
            // about and is re-thrown below regardless.
          }
        }
      }
      throw err;
    }
    try {
      await commitTransaction(this.client, this.name, sessionId);
    } catch (commitErr) {
      try {
        await rollbackTransaction(this.client, this.name, sessionId);
      } catch {
        // Best-effort: the commit error is what the caller needs to see, so the rollback's own
        // failure (the session may already be gone, or the server may be unreachable) is
        // deliberately discarded here rather than overwriting or chaining onto commitErr.
      }
      throw commitErr;
    }
    return result;
  }
}

/**
 * A connection to one ArcadeDB server, scoped to server-level operations
 * (listing/checking databases, server info, health/readiness) plus
 * `db()` to reach a specific database.
 */
export class ArcadeDBServer {
  /**
   * The unwrapped openapi-fetch client this facade is built on. Returns
   * `{ data, error }` and does NOT throw, unlike every method above -
   * that asymmetry is deliberate: use `raw` when you want to handle
   * `ArcadeDBError`-worthy conditions yourself instead of via try/catch.
   */
  readonly raw: RawClient;

  /**
   * `createClient` passes only `options`, which also serves as the insert session's context.
   * `insertContext` is kept for servers constructed by hand, and wins over `options` when both
   * are given.
   */
  constructor(
    client: RawClient,
    private readonly insertContext?: InsertSessionContext,
    private readonly options?: CreateClientOptions,
  ) {
    this.raw = client;
  }

  /**
   * The options this server was built with. `loginAs` and `withToken` build a client from them, so
   * they need a server from `createClient`; one constructed by hand has none.
   */
  private builtWith(method: string): CreateClientOptions {
    if (!this.options) {
      throw new Error(`${method} needs a server built by createClient()`);
    }
    return this.options;
  }

  /**
   * Opens a session with the client's own credentials through `POST /api/v1/login` and resolves
   * to its token. The client itself is unchanged: present the token with `withToken`.
   *
   * Wrong Basic credentials throw `ArcadeDBError` with status **403** ("Security error"), not
   * 401: the server answers a failed password check with 403 on every endpoint, so on `login` it
   * cannot be told apart from a forbidden user (ArcadeData/arcadedb#10109). 401 is what an invalid
   * or expired bearer token gets. A server that has reached its limit of concurrent sessions
   * answers 503.
   *
   * Each login opens a new session, and a user holds at most 100 by default
   * (`arcadedb.server.httpAuthSessionMaxPerUser`): the next login silently evicts that user's
   * oldest session, whose token then gets a 401. Log in once and reuse the token.
   */
  async login(): Promise<LoginResult> {
    const { login } = await import("./facade/session.js");
    return login(this.raw);
  }

  /**
   * Opens a session as `user`, whatever credentials the client is configured with, and resolves to
   * its token, as `login` does and with the same failures. It is the way to act as one user from a
   * client built for another: for per-user isolation, log in as the user once and keep
   * `withToken(result.token)` rather than the user's password.
   *
   * The request goes through a separate client carrying only `basicAuth(user, password)`, built
   * from this server's `baseUrl` and `fetch`: a per-call header would lose to this client's own
   * auth middleware, which sets `Authorization` after the call's headers are applied. This client
   * is unchanged. Requires a server built by `createClient`.
   */
  async loginAs(user: string, password: string): Promise<LoginResult> {
    const { baseUrl, fetch } = this.builtWith("loginAs");
    return createClient({ baseUrl, fetch, auth: basicAuth(user, password) }).login();
  }

  /**
   * Returns a new `ArcadeDBServer` that authenticates every request with `token` as a bearer token,
   * and is otherwise built like this one: the same `baseUrl`, `fetch` and `WebSocket`. This server
   * is unchanged, and nothing is sent. `token` is a session token from `login` or `loginAs`, or an
   * API token from `createAPIToken`.
   *
   * Middleware added to this server's `raw` with `raw.use()` after `createClient` is not carried
   * over. Requires a server built by `createClient`.
   */
  withToken(token: string): ArcadeDBServer {
    const { baseUrl, fetch, WebSocket } = this.builtWith("withToken");
    return createClient({ baseUrl, fetch, WebSocket, auth: bearerAuth(token) });
  }

  /**
   * Invalidates the session token this client presents, through `POST /api/v1/logout`.
   *
   * A client that does not present a session token from `login` (Basic credentials, or an API
   * token) rejects with `NotSessionTokenError` without a request: the server answers 204 to such a
   * logout and invalidates nothing. The token is read from the `auth` middleware given to
   * `createClient`, by running it on a throwaway request as the insert session does. A token that
   * is no longer valid, because it was already logged out or has expired, throws `ArcadeDBError`
   * with status 401. Once this resolves, every request with the token, from any client, is a 401.
   */
  async logout(): Promise<void> {
    const { logout } = await import("./facade/session.js");
    return logout(this.raw, this.options);
  }

  /**
   * Lists every authentication session the server holds (root only; any other user gets a 403
   * `ArcadeDBError`). Each carries its live token, so the result is as sensitive as the users'
   * passwords.
   */
  async listSessions(): Promise<Session[]> {
    const { listSessions } = await import("./facade/session.js");
    return listSessions(this.raw);
  }

  /**
   * Issues an API token (root only) through `POST /api/v1/server/api-tokens`. The plaintext token
   * is in the result's `token` and nowhere else, ever: see `CreatedAPIToken`.
   *
   * An `opts.expiresAt` that is not a valid date after the Unix epoch throws `RangeError` before
   * anything is sent: the server reads an expiry of 0 as "never". A name already in use throws
   * `ArcadeDBError` with status 409, and a blank name a 400. The server refuses to send the token
   * in the clear: unless the request arrives over HTTPS, from a loopback address, or through a
   * trusted proxy that terminated TLS, it answers 412 and issues nothing when
   * `arcadedb.server.apiTokenRequireSecureTransport` is on (the default from ArcadeDB 27.1.1).
   */
  async createAPIToken(name: string, opts: CreateAPITokenOptions = {}): Promise<CreatedAPIToken> {
    const { createAPIToken } = await import("./facade/session.js");
    return createAPIToken(this.raw, name, opts);
  }

  /** Lists every issued API token as metadata (root only); never the token itself. */
  async listAPITokens(): Promise<APIToken[]> {
    const { listAPITokens } = await import("./facade/session.js");
    return listAPITokens(this.raw);
  }

  /**
   * Revokes the API token whose hash is `tokenHash` (root only), through
   * `DELETE /api/v1/server/api-tokens`.
   *
   * It takes the `tokenHash` that `listAPITokens` and `createAPIToken` report, never the token:
   * anything but 64 lowercase hexadecimal characters throws `RangeError` before it is sent,
   * because the argument travels in the query string, which proxies and access logs record. The
   * error does not repeat the argument. A hash no token has throws `ArcadeDBError` with status
   * 404, a status the contract does not list (ArcadeData/arcadedb#10110).
   */
  async deleteAPIToken(tokenHash: string): Promise<void> {
    const { deleteAPIToken } = await import("./facade/session.js");
    return deleteAPIToken(this.raw, tokenHash);
  }

  /** Lists the names of every database visible to the authenticated caller. */
  async listDatabases(): Promise<string[]> {
    const data = await unwrap(this.raw.GET("/api/v1/databases", {}));
    return data.result ?? [];
  }

  /**
   * Checks whether a database exists and is visible to the authenticated
   * caller.
   *
   * `false` cannot distinguish "the database does not exist" from "it
   * exists, but the caller is not authorized to see it" - the server does
   * not make that distinction in its response, so this client cannot
   * either. Do not treat a `false` result as proof the database is absent.
   */
  async exists(name: string): Promise<boolean> {
    const data = await unwrap(
      this.raw.GET("/api/v1/exists/{database}", {
        params: { path: { database: name } },
      }),
    );
    return data.result ?? false;
  }

  /** Retrieves server status, version, and configuration information. */
  async serverInfo(): Promise<components["schemas"]["ServerInfo"]> {
    return unwrap(this.raw.GET("/api/v1/server", {}));
  }

  /**
   * Liveness probe: resolves when the server process and HTTP layer are
   * up. Performs no database I/O and requires no authentication. Throws
   * `ArcadeDBError` if the server does not answer 204.
   */
  async health(): Promise<void> {
    await unwrap(this.raw.GET("/api/v1/health", {}));
  }

  /**
   * Readiness probe: resolves `true` when the server is ready to accept
   * requests, `false` when it has answered 503 (not finished starting, not
   * yet joined its Raft group, or still catching up on replication). Any
   * other failure still throws `ArcadeDBError`.
   */
  async ready(): Promise<boolean> {
    const { error, response } = await this.raw.GET("/api/v1/ready", {});
    if (response.status === 503) {
      return false;
    }
    if (!response.ok) {
      throw ArcadeDBError.fromResponse(response, error);
    }
    return true;
  }

  /**
   * Runs one command through `POST /api/v1/server` and returns the whole parsed body.
   *
   * Most server commands are root-only; the contract's `executeServerCommand` lists them and
   * says which ones any user may run. The body is returned as `Record<string, unknown>` because
   * its shape depends on the command: `{"result": "ok"}` for an administrative command, a list
   * for `list databases`, other shapes for others. The contract types it as `QueryResponse`, with
   * an array `result`, which an administrative command's answer does not match; openapi-fetch
   * does not validate, so `raw` would hand back the same body under the wrong type. Throws
   * `ArcadeDBError` on a non-2xx status.
   *
   * The command is sent as given. Prefer `createDatabase` / `dropDatabase`, which refuse a name
   * the server would silently trim, and the user and group methods, which use the dedicated
   * endpoints with a structured body instead of a command string.
   */
  async serverCommand(command: string): Promise<Record<string, unknown>> {
    const { serverCommand } = await import("./facade/admin.js");
    return serverCommand(this.raw, command);
  }

  /**
   * Creates the named database (root only).
   *
   * There is no dedicated endpoint, so this sends `create database <name>` through
   * `serverCommand`. A name that is empty or has leading or trailing white space rejects with a
   * `RangeError` before anything is sent: the server trims the name it reads out of the command,
   * so it would create a database other than the one named. Anything else is sent as given,
   * embedded spaces included, and the server takes the rest of the command as the name: one
   * request runs one command, so a name cannot smuggle in a second one, but a name built from
   * untrusted input should still be validated by the caller.
   *
   * A name that already exists throws `ArcadeDBError` with status **409** (`error` "Database
   * already exists"), so a caller can treat 409 as "already there" to create a database only when
   * it is missing. A server built before ArcadeData/arcadedb#10079 answers 400 "Cannot execute
   * command" instead, with the reason only in `detail`, which this client does not match on;
   * against such a server, call `exists` first: as root it sees every database, so its `false`
   * is reliable, although another client can still create the database between the two calls.
   */
  async createDatabase(name: string): Promise<void> {
    const { databaseCommand } = await import("./facade/admin.js");
    return databaseCommand(this.raw, "create", name);
  }

  /**
   * Drops the named database and deletes its files (root only).
   *
   * There is no dedicated endpoint, so this sends `drop database <name>` through `serverCommand`.
   * A name that is empty or has leading or trailing white space rejects with a `RangeError` before
   * anything is sent, as for `createDatabase`. A database that does not exist throws
   * `ArcadeDBError` with status 400.
   */
  async dropDatabase(name: string): Promise<void> {
    const { databaseCommand } = await import("./facade/admin.js");
    return databaseCommand(this.raw, "drop", name);
  }

  /**
   * Lists the statements running on this server, with the tag each was sent with.
   *
   * Open to any authenticated user: root sees every statement, another user only their own.
   * `opts.database` and `opts.tag` narrow the list; omitted or empty, they are no filter. Sends
   * `list queries [database <name>] [tag <label>]` through `POST /api/v1/server`, which is never
   * forwarded to the cluster leader: behind a load balancer this sees only the server the client
   * happened to reach.
   *
   * A `database` containing a space or control character, or a `tag` with a leading or trailing
   * space or control character, rejects with a `RangeError` before anything is sent: the server
   * reads the database as one word and trims the tag. Throws `ArcadeDBError` on a non-2xx status.
   */
  async listQueries(opts: ListQueriesOptions = {}): Promise<RunningQuery[]> {
    return (await loadRunning()).listQueries(this.raw, opts);
  }

  /**
   * Stops the statement with the given id (`RunningQuery.id`) and waits for it to end.
   *
   * `opts.waitMs` bounds the wait; omitted or zero, the server's default of 5000 applies, and the
   * server caps it at 10000. The answer's `status` decides whether the caller has anything to
   * undo: `"terminated"` means it stopped and what it wrote was rolled back, `"completed"` that it
   * finished first and what it did stands, `"terminating"` that it has not stopped yet, and
   * `"not found"` that no such statement runs here or it is another user's (never "forbidden").
   * The stopped request itself throws the 409 that `isQueryTerminated` recognises. Terminating a
   * command inside a transaction ends the transaction too (`sessionOpen` false); a terminated read
   * leaves it open.
   *
   * An id that is empty or contains a space or control character rejects with a `RangeError` before
   * anything is sent. Throws `ArcadeDBError` on a non-2xx status.
   */
  async terminateQuery(id: string, opts: TerminateOptions = {}): Promise<TerminateResult> {
    return (await loadRunning()).terminateQuery(this.raw, id, opts);
  }

  /**
   * Stops every statement sent with the given `queryTag` and waits for them to end, answering each
   * with its own `TerminateResult`; see `terminateQuery` for `waitMs` and for what each status
   * means. No statement with that tag is an empty array, not an error. The tag is sent as given,
   * spaces and quotes included: the server takes the rest of the command as the tag. A tag that is
   * empty, or starts or ends with a space or control character, rejects with a `RangeError` before
   * anything is sent. Throws `ArcadeDBError` on a non-2xx status.
   */
  async terminateQueriesByTag(tag: string, opts: TerminateOptions = {}): Promise<TerminateResult[]> {
    return (await loadRunning()).terminateQueriesByTag(this.raw, tag, opts);
  }

  /**
   * Lists the open transaction sessions on this server. Open to any authenticated user: root sees
   * every session, another user only their own. Never forwarded to the cluster leader. Throws
   * `ArcadeDBError` on a non-2xx status.
   */
  async listTransactions(): Promise<OpenTransaction[]> {
    return (await loadRunning()).listTransactions(this.raw);
  }

  /**
   * Rolls back and ends the transaction session with the given id (`OpenTransaction.id`).
   *
   * `opts.waitMs` bounds how long the server waits for a statement running in it to stop, as for
   * `terminateQuery`; the answer is `"terminating"` when it has not.
   *
   * A statement running in it is stopped, and its request throws the 409 that `isQueryTerminated`
   * recognises; a statement sent on the session afterwards gets a 404. **A commit does not
   * notice:** the server answers a commit naming the vanished session with 204, like a real
   * commit, so the owner's `transaction()` callback can resolve although what it wrote is gone. An
   * unknown session, or another user's, is answered `"not found"`.
   *
   * A session id that is empty or contains a space or control character rejects with a `RangeError`
   * before anything is sent. Throws `ArcadeDBError` on a non-2xx status.
   */
  async terminateTransaction(sessionId: string, opts: TerminateOptions = {}): Promise<TerminateResult> {
    return (await loadRunning()).terminateTransaction(this.raw, sessionId, opts);
  }

  /**
   * Creates a server user (root only) through `POST /api/v1/server/users`.
   *
   * `opts.databases` maps a database name, or `"*"` for every database, to the groups the user
   * holds there; omitted, no assignment is sent. The server refuses a blank name, a name starting
   * with `apitoken:`, and a password shorter than 8 or longer than 256 characters, each with a
   * 400 `ArcadeDBError`.
   *
   * A name that already exists throws `ArcadeDBError` with status **409** (`error` "User already
   * exists"), so a caller can treat 409 as "already there" to create a user only when it is
   * missing. A server built before ArcadeData/arcadedb#10076 answers 403 "Security error"
   * instead, which is also what a non-root caller gets; against such a server, look for the user
   * in `listUsers` first rather than reading a 403 as "already exists".
   */
  async createUser(name: string, password: string, opts: CreateUserOptions = {}): Promise<void> {
    const { createUser } = await import("./facade/admin.js");
    return createUser(this.raw, name, password, opts);
  }

  /**
   * Changes an existing user's password, database assignments, or both (root only), through
   * `PUT /api/v1/server/users`. A field left out of `opts` is not sent, and the server keeps that
   * value; an empty `databases` object IS sent, and removes every assignment. A user that does not
   * exist throws `ArcadeDBError` with status 404.
   */
  async updateUser(name: string, opts: UpdateUserOptions = {}): Promise<void> {
    const { updateUser } = await import("./facade/admin.js");
    return updateUser(this.raw, name, opts);
  }

  /**
   * Deletes a server user (root only) through `DELETE /api/v1/server/users`. A user that does not
   * exist throws `ArcadeDBError` with status 404; root cannot be deleted (400).
   */
  async dropUser(name: string): Promise<void> {
    const { dropUser } = await import("./facade/admin.js");
    return dropUser(this.raw, name);
  }

  /**
   * Lists every server user (root only), each with the groups it holds per database (`"*"` for
   * every database). The password hash is never returned.
   */
  async listUsers(): Promise<ServerUser[]> {
    const { listUsers } = await import("./facade/admin.js");
    return listUsers(this.raw);
  }

  /**
   * Creates the named group on `database` (`"*"` for every database), or replaces it if it exists
   * (root only), through `POST /api/v1/server/groups`. A field left out of `opts` is not sent.
   */
  async saveGroup(database: string, name: string, opts: SaveGroupOptions = {}): Promise<void> {
    const { saveGroup } = await import("./facade/admin.js");
    return saveGroup(this.raw, database, name, opts);
  }

  /**
   * Deletes one group of one database (root only) through `DELETE /api/v1/server/groups`. A group
   * that does not exist throws `ArcadeDBError` with status 404.
   */
  async deleteGroup(database: string, name: string): Promise<void> {
    const { deleteGroup } = await import("./facade/admin.js");
    return deleteGroup(this.raw, database, name);
  }

  /**
   * Lists every security group (root only), keyed by database name (`"*"` covers every database)
   * and then by group name. The group document's schema version is not returned.
   */
  async listGroups(): Promise<Record<string, Record<string, GroupDefinition>>> {
    const { listGroups } = await import("./facade/admin.js");
    return listGroups(this.raw);
  }

  /** Scopes subsequent calls to one database, reached through this server. */
  db(name: string): ArcadeDBDatabase {
    return new ArcadeDBDatabase(this.raw, name, undefined, this.insertContext ?? this.options);
  }
}

export interface CreateClientOptions {
  /** Base URL of the ArcadeDB server, e.g. `http://localhost:2480`. */
  baseUrl: string;
  /** Auth middleware, typically `basicAuth(...)` or `bearerAuth(...)`. */
  auth?: Middleware;
  /** Custom `fetch` implementation; defaults to the runtime global. */
  fetch?: typeof fetch;
  /**
   * WebSocket class used by `db.insertSession()`. Defaults to the runtime's global `WebSocket`
   * (Node 22+); on Node 20 pass the `ws` package's `WebSocket`. Only the insert session uses it.
   */
  WebSocket?: WebSocketConstructor;
}

/** Builds an `ArcadeDBServer` client scoped to one ArcadeDB server. */
export function createClient(opts: CreateClientOptions): ArcadeDBServer {
  const client = createOpenApiClient<paths>({
    baseUrl: opts.baseUrl,
    fetch: opts.fetch,
  });
  if (opts.auth) {
    client.use(opts.auth);
  }
  // `opts` doubles as the insert session's context (`baseUrl`, `auth`, `WebSocket`); see `db()`.
  return new ArcadeDBServer(client, undefined, opts);
}
