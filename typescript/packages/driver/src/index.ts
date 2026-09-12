import createOpenApiClient from "openapi-fetch";
import type { Client, Middleware } from "openapi-fetch";
import type { components, paths } from "./generated/schema.js";
import { ArcadeDBError } from "./errors.js";
import { unwrap } from "./internal/unwrap.js";
import { beginTransaction, commitTransaction, executeCommand, executeQuery, rollbackTransaction } from "./facade/data.js";
import type { CommandOptions, QueryEnvelope, QueryOptions } from "./facade/data.js";
import { commandStream, queryStream } from "./facade/stream.js";
import type { NdJsonQueryEvent } from "./facade/stream.js";
import type {
  GrafanaQueryOptions,
  GrafanaQueryResponse,
  PromQLDataResponse,
  PromQLLabelsResponse,
  PromQLQueryOptions,
  PromQLQueryRangeOptions,
  PromQLSeriesOptions,
  PromQLSeriesResponse,
} from "./facade/dashboards.js";
import type { TimeSeriesQueryOptions, TimeSeriesQueryResult, TimeSeriesWriteOptions } from "./facade/timeseries.js";
import type {
  FullTextSearchOptions,
  FullTextSearchResult,
  HybridSearchOptions,
  HybridSearchResult,
  VectorSearchOptions,
  VectorSearchResult,
} from "./facade/vector.js";

export { ArcadeDBError } from "./errors.js";
export { basicAuth, bearerAuth } from "./auth.js";
export type { Middleware } from "openapi-fetch";
export type { CommandOptions, QueryEnvelope, QueryLanguage, QueryOptions } from "./facade/data.js";
export type { NdJsonQueryEvent } from "./facade/stream.js";
export type {
  GrafanaQueryOptions,
  GrafanaQueryResponse,
  PromQLDataResponse,
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
export class ArcadeDBDatabase {
  private _ts: TimeSeriesNamespace | undefined;
  private _grafana: GrafanaNamespace | undefined;
  private _promql: PromQLNamespace | undefined;
  private _vector: VectorNamespace | undefined;

  constructor(
    private readonly client: RawClient,
    readonly name: string,
    private readonly sessionId?: string,
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

  /** Executes a read-or-write query and returns the whole result envelope - not just `result`. */
  async query<T = unknown>(opts: QueryOptions): Promise<QueryEnvelope<T>> {
    return executeQuery<T>(this.client, this.name, this.sessionId, opts);
  }

  /** Executes a command and returns the whole result envelope - not just `result`. */
  async command<T = unknown>(opts: CommandOptions): Promise<QueryEnvelope<T>> {
    return executeCommand<T>(this.client, this.name, this.sessionId, opts);
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
   *    server-side until `arcadedb.server.httpTxExpireTimeout` reaps it.
   */
  async transaction<T>(fn: (tx: ArcadeDBDatabase) => Promise<T>): Promise<T> {
    const sessionId = await beginTransaction(this.client, this.name);
    const tx = new ArcadeDBDatabase(this.client, this.name, sessionId);
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

  constructor(client: RawClient) {
    this.raw = client;
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

  /** Scopes subsequent calls to one database, reached through this server. */
  db(name: string): ArcadeDBDatabase {
    return new ArcadeDBDatabase(this.raw, name);
  }
}

export interface CreateClientOptions {
  /** Base URL of the ArcadeDB server, e.g. `http://localhost:2480`. */
  baseUrl: string;
  /** Auth middleware, typically `basicAuth(...)` or `bearerAuth(...)`. */
  auth?: Middleware;
  /** Custom `fetch` implementation; defaults to the runtime global. */
  fetch?: typeof fetch;
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
  return new ArcadeDBServer(client);
}
