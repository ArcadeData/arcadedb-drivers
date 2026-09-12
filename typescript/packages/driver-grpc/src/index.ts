import { createClient as createConnectClient } from "@connectrpc/connect";
import type { Client, Interceptor } from "@connectrpc/connect";
import { createGrpcTransport } from "@connectrpc/connect-node";
import { ArcadeDbAdminService, ArcadeDbService } from "./gen/arcadedb-server-26.10.1-SNAPSHOT_pb.js";
import { sendsPlaintextPassword } from "./auth.js";
import { createInsertStream, createStreamQuery, createTimeSeriesQuery, createTimeSeriesWriteStream } from "./stream.js";
import { createTransaction } from "./transaction.js";

export { bearerAuth, passwordAuth } from "./auth.js";
export type { Interceptor } from "@connectrpc/connect";
export type {
  InsertStreamRequest,
  StreamQueryRequestInit,
  TimeSeriesQueryRequestInit,
  TimeSeriesWriteStreamRequest,
} from "./stream.js";
export type { TransactionHandle } from "./transaction.js";
// Re-exports every data-plane message type and enum the generated client uses (`GrpcRecord`,
// `QueryResult`, `StreamQueryRequest_RetrievalMode`, etc.) under this package's own entry point.
// Without this, a caller cannot name a single one of these types without importing the
// version-stamped generated file directly (`./gen/arcadedb-server-26.10.1-SNAPSHOT_pb.js`) - which
// the `exports` map in package.json blocks for an installed copy anyway - and cannot use
// `retrievalMode` at all, since `StreamQueryRequest_RetrievalMode` is a runtime enum, not a type:
// without this re-export a caller would have to pass a bare numeric literal (e.g. `2`) instead of
// `StreamQueryRequest_RetrievalMode.PAGED`.
export * from "./gen/arcadedb-server-26.10.1-SNAPSHOT_pb.js";

/** The generated Connect client for `com.arcadedb.grpc.ArcadeDbService` (the data plane). */
type RawClient = Client<typeof ArcadeDbService>;
/** The generated Connect client for `com.arcadedb.grpc.ArcadeDbAdminService` (the control plane). */
type RawAdminClient = Client<typeof ArcadeDbAdminService>;

/**
 * Options for {@link createClient}.
 */
export interface CreateClientOptions {
  /** The gRPC server's base URL, e.g. `https://localhost:50051` or `http://localhost:50051`. */
  baseUrl: string;
  /** An auth interceptor, typically {@link bearerAuth} or {@link passwordAuth}. */
  auth?: Interceptor;
  /**
   * Opts into an `http://` (non-TLS) `baseUrl` paired with a plaintext-password auth
   * interceptor ({@link passwordAuth}). Without this, `createClient` throws rather than send a
   * password over an unencrypted channel. Has no effect otherwise (TLS `baseUrl`, no auth, or a
   * non-password auth interceptor such as {@link bearerAuth}).
   */
  insecure?: boolean;
}

/**
 * ArcadeDB's gRPC data-plane client. `raw` is the generated Connect client
 * (`createClient(ArcadeDbService, transport)`); `streamQuery`, `insertStream`, and `transaction`
 * are the higher-level convenience wrappers this package builds on top of it.
 */
export interface ArcadeDBGrpcClient {
  /** The generated Connect client for the `ArcadeDbService` data plane. */
  raw: RawClient;
  /**
   * The generated Connect client for `ArcadeDbAdminService` - the control plane (database
   * lifecycle, users, groups, API tokens, settings, backups, the profiler, server
   * shutdown/cluster operations, `Health`/`Ready`). No facade: every one of its 44 RPCs is
   * reached exactly as `raw` reaches the data plane's, one stub call at a time.
   *
   * `rawAdmin` is built from the SAME transport `raw` is, so it shares this client's TLS
   * policy - but NOT its authentication. 42 of the 44 admin RPCs (everything but `Health` and
   * `Ready`) authenticate from a `DatabaseCredentials` field INSIDE the request message, not
   * from the transport's auth interceptor, so `bearerAuth`/`passwordAuth` do nothing for them.
   * Accessing this property throws if `createClient`'s `baseUrl` is non-TLS and `insecure: true`
   * was not passed: those in-body credentials would otherwise travel in cleartext regardless of
   * any auth interceptor, the same hazard #5048 closed for the data plane's password auth. The
   * check runs when `rawAdmin` is READ, not when `createClient` is called, so a client built
   * over a plain `http://` baseUrl for the data plane keeps working unchanged - only touching
   * `rawAdmin` requires the same opt-in. `Health` and `Ready` carry no credentials at all and
   * are still refused by this guard: it protects the stub as a whole, not a per-RPC list, so
   * there is deliberately no special case carving the two credential-free RPCs back out.
   */
  readonly rawAdmin: RawAdminClient;
  /**
   * Streams a query's results row by row. `retrievalMode` and `batchSize` pass through to the
   * server unchanged - see {@link StreamQueryRequestInit}.
   */
  streamQuery: ReturnType<typeof createStreamQuery>;
  /**
   * Streams rows to the server in chunks, handling the `session_id` / `chunk_seq` / `database` /
   * `last` envelope bookkeeping - see {@link InsertStreamRequest}.
   */
  insertStream: ReturnType<typeof createInsertStream>;
  /**
   * Streams a time-series answer message by message - see {@link createTimeSeriesQuery}. Also
   * reachable, bound to an open transaction, as `TransactionHandle.timeSeriesQuery` (see
   * `transaction.ts`), since `TimeSeriesQueryRequest` carries a `transaction` field.
   */
  timeSeriesQuery: ReturnType<typeof createTimeSeriesQuery>;
  /**
   * Streams points to `ArcadeDbService.TimeSeriesWriteStream`, one wire chunk per input batch -
   * see {@link TimeSeriesWriteStreamRequest} and {@link createTimeSeriesWriteStream}.
   * `TimeSeriesWrite` (the unary write) and `TimeSeriesLatest` carry no top-level wrapper of their
   * own: `TimeSeriesWrite`'s request has no `transaction` field, so `raw.timeSeriesWrite` already
   * works unassisted, and `TimeSeriesLatest` is reachable only bound to a transaction, as
   * `TransactionHandle.timeSeriesLatest` - a bare stub drives both of those fine, so wrapping
   * either would be a named passthrough adding nothing.
   */
  timeSeriesWriteStream: ReturnType<typeof createTimeSeriesWriteStream>;
  /**
   * Runs `fn` inside a server-side transaction: begins it, hands `fn` a {@link TransactionHandle}
   * whose calls all carry the transaction's id automatically, and ends the transaction on both
   * the success and failure paths - see `transaction.ts` for the full commit/rollback contract.
   * This is the safety net against the transaction-hijack, silent-data-loss and leaked-transaction
   * defects the 2026-07 gRPC audit filed as #5040-#5042.
   */
  transaction: ReturnType<typeof createTransaction>;
}

/**
 * Creates an ArcadeDB gRPC data-plane client over `@connectrpc/connect-node`'s gRPC transport.
 *
 * Refuses to pair a plaintext-password auth interceptor ({@link passwordAuth}) with a non-TLS
 * `baseUrl` unless `insecure: true` is passed explicitly - sending a password in cleartext
 * metadata is a credential-exposure hazard (see issue #5048). The check is `protocol !== "https:"`,
 * not `=== "http:"`: `new URL("localhost:50051")` parses successfully with `protocol` set to
 * `"localhost:"`, not `"http:"`, so a strict `http:` comparison would silently skip the refusal
 * for exactly the kind of schemeless `baseUrl` a caller who forgot the scheme would write.
 *
 * This function itself never throws on account of `rawAdmin` - see that property's doc comment.
 * A data-plane client over a plain `http://` baseUrl is constructed exactly as it always was;
 * the admin guard fires only when `rawAdmin` is actually read.
 */
export function createClient(opts: CreateClientOptions): ArcadeDBGrpcClient {
  const { baseUrl, auth, insecure = false } = opts;

  if (!insecure && sendsPlaintextPassword(auth) && new URL(baseUrl).protocol !== "https:") {
    throw new Error(
      `createClient: refusing to send a plaintext password over insecure baseUrl "${baseUrl}". ` +
        "Use an https:// baseUrl, switch to bearerAuth, or pass insecure: true to opt in explicitly.",
    );
  }

  const transport = createGrpcTransport({ baseUrl, interceptors: auth ? [auth] : [] });
  const raw = createConnectClient(ArcadeDbService, transport);
  const rawAdminClient = createConnectClient(ArcadeDbAdminService, transport);

  // Same `protocol !== "https:"` check as the plaintext-password guard above, and for the same
  // reason (a schemeless baseUrl must not slip past an `=== "http:"` comparison) - but
  // unconditional on `auth`, because the hazard here is credentials INSIDE an admin RPC's own
  // request body, not anything the auth interceptor puts on the wire.
  const rawAdminBlockedByInsecureChannel = !insecure && new URL(baseUrl).protocol !== "https:";

  return {
    raw,
    get rawAdmin(): RawAdminClient {
      if (rawAdminBlockedByInsecureChannel) {
        throw new Error(
          `rawAdmin: refusing to expose ArcadeDbAdminService over insecure baseUrl "${baseUrl}". ` +
            "42 of its 44 RPCs (everything but Health and Ready) carry DatabaseCredentials in the " +
            "request body, which would travel in cleartext regardless of any auth interceptor. Use " +
            "an https:// baseUrl, or pass insecure: true to opt in explicitly.",
        );
      }
      return rawAdminClient;
    },
    streamQuery: createStreamQuery(raw),
    insertStream: createInsertStream(raw),
    timeSeriesQuery: createTimeSeriesQuery(raw),
    timeSeriesWriteStream: createTimeSeriesWriteStream(raw),
    transaction: createTransaction(raw),
  };
}
