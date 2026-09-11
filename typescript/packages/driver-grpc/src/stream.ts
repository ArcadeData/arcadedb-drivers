import { randomUUID } from "node:crypto";
import type { CallOptions, Client } from "@connectrpc/connect";
import type { MessageInitShape, MessageShape } from "@bufbuild/protobuf";
import type { ArcadeDbService, TimeSeriesPoint, TimeSeriesPrecision } from "./gen/arcadedb-server-26.10.1-SNAPSHOT_pb.js";
import {
  DatabaseCredentialsSchema,
  GrpcRecordSchema,
  InsertChunkSchema,
  InsertOptionsSchema,
  InsertSummarySchema,
  QueryResultSchema,
  StreamQueryRequestSchema,
  TimeSeriesQueryRequestSchema,
  TimeSeriesQueryResultSchema,
  TimeSeriesWriteChunkSchema,
  TimeSeriesWriteSummarySchema,
  TransactionContextSchema,
} from "./gen/arcadedb-server-26.10.1-SNAPSHOT_pb.js";

/** The generated Connect client for `com.arcadedb.grpc.ArcadeDbService`. */
type RawClient = Client<typeof ArcadeDbService>;

type GrpcRecordInit = MessageInitShape<typeof GrpcRecordSchema>;
type QueryResult = MessageShape<typeof QueryResultSchema>;
type InsertSummary = MessageShape<typeof InsertSummarySchema>;
type InsertChunkInit = MessageInitShape<typeof InsertChunkSchema>;
type TimeSeriesWriteChunkInit = MessageInitShape<typeof TimeSeriesWriteChunkSchema>;
type TimeSeriesWriteSummary = MessageShape<typeof TimeSeriesWriteSummarySchema>;
type TimeSeriesQueryResult = MessageShape<typeof TimeSeriesQueryResultSchema>;

/**
 * `StreamQuery` request. `retrievalMode` (CURSOR / MATERIALIZE_ALL / PAGED) and `batchSize`
 * pass through to the server unchanged - this wrapper never picks a default for the caller,
 * since the three retrieval modes have materially different memory and consistency behaviour
 * that only the caller can judge.
 */
export type StreamQueryRequestInit = MessageInitShape<typeof StreamQueryRequestSchema>;

/**
 * Wraps `ArcadeDbService.StreamQuery` (server-streaming): iterates the server's stream of
 * `QueryResult` batches and yields each `GrpcRecord` row individually, flattening the batching
 * the wire protocol uses. Thin by design - no batch-size or retrieval-mode defaulting happens
 * here, both pass through to the server as given.
 */
export function createStreamQuery(raw: Pick<RawClient, "streamQuery">) {
  return async function* streamQuery(
    request: StreamQueryRequestInit,
    options?: CallOptions,
  ): AsyncGenerator<QueryResult["records"][number], void, undefined> {
    for await (const result of raw.streamQuery(request, options)) {
      yield* result.records;
    }
  };
}

/**
 * `TimeSeriesQuery` request. Unlike {@link StreamQueryRequestInit}, no field is defaulted or
 * reshaped here either - `limit`, `batchSize`, `aggregation` and the rest pass straight through.
 */
export type TimeSeriesQueryRequestInit = MessageInitShape<typeof TimeSeriesQueryRequestSchema>;

/**
 * Wraps `ArcadeDbService.TimeSeriesQuery` (server-streaming): yields each `TimeSeriesQueryResult`
 * message the server sends, in order, unflattened. This is deliberately thinner than
 * {@link createStreamQuery}, which flattens `QueryResult` batches into individual rows -
 * `TimeSeriesQueryResult` cannot be flattened the same way, because `truncated` and `last` are
 * carried per-message (only meaningful on the message where `last` is true) and a raw answer's
 * `rows` versus an aggregated answer's `buckets` are shaped differently. Flattening either away
 * would throw away information a caller needs to tell "the stream ended" from "the stream ended
 * early because of `limit`".
 */
export function createTimeSeriesQuery(raw: Pick<RawClient, "timeSeriesQuery">) {
  return async function* timeSeriesQuery(
    request: TimeSeriesQueryRequestInit,
    options?: CallOptions,
  ): AsyncGenerator<TimeSeriesQueryResult, void, undefined> {
    yield* raw.timeSeriesQuery(request, options);
  };
}

/**
 * `InsertStream` request. `chunks` is the sequence of row batches the caller wants to send -
 * each element becomes exactly one wire `InsertChunk`. This wrapper owns the envelope
 * bookkeeping around those batches (`session_id`, `chunk_seq`, first-chunk-only `database`,
 * final-chunk `last`); it does not decide how rows are batched, that's the caller's call.
 */
export interface InsertStreamRequest {
  /**
   * Sent on the first chunk only, per the `.proto` contract (`InsertChunk.database` is documented
   * REQUIRED there on the first chunk). This field is authoritative on a server carrying the fix
   * for [ArcadeData/arcadedb#6597](https://github.com/ArcadeData/arcadedb/issues/6597) (merged in
   * `7ccade7348`, released in 26.9.1): such a server re-reads a non-empty chunk `database` on
   * every chunk it appears on, it is not cached. 26.8.1 and every earlier server ignore it
   * entirely, which is why {@link envelopeChunks} also mirrors it into `options.database` on the
   * first chunk - see the comment there.
   */
  database: string;
  credentials?: MessageInitShape<typeof DatabaseCredentialsSchema>;
  options?: MessageInitShape<typeof InsertOptionsSchema>;
  transaction?: MessageInitShape<typeof TransactionContextSchema>;
  /** One element per wire chunk. */
  chunks: AsyncIterable<GrpcRecordInit[]>;
}

/**
 * Wraps `ArcadeDbService.InsertStream` (client-streaming): turns `request.chunks` into the
 * `AsyncIterable<InsertChunk>` the generated client expects, adding the envelope bookkeeping a
 * caller would otherwise have to hand-roll:
 * - one `session_id` (a fresh UUID), stable for the whole stream
 * - `chunk_seq` starting at 1 and incrementing by 1
 * - `database` set on the first chunk only, per the `.proto` contract, and mirrored into
 *   `options.database` there too for compatibility with servers that predate #6597's fix (see
 *   {@link InsertStreamRequest.database})
 * - `last: true` on the final chunk only
 *
 * An empty `request.chunks` sends a single chunk with zero rows and `last: true`, rather than
 * throwing - see the comment in {@link envelopeChunks} for why.
 *
 * Awaits and returns the server's single `InsertSummary` response.
 */
export function createInsertStream(raw: Pick<RawClient, "insertStream">) {
  return function insertStream(request: InsertStreamRequest, options?: CallOptions): Promise<InsertSummary> {
    return raw.insertStream(envelopeChunks(request, randomUUID()), options);
  };
}

async function* envelopeChunks(request: InsertStreamRequest, sessionId: string): AsyncGenerator<InsertChunkInit> {
  const iterator = request.chunks[Symbol.asyncIterator]();

  // The iterator is pulled manually below (not via `for await...of`), so its finalization is not
  // automatic: if this generator is abandoned early - the RPC call it feeds aborts mid-stream, or
  // the caller of `insertStream` itself stops consuming - nothing would otherwise call
  // `iterator.return()` on the caller's own async iterable, and any `finally` block the caller
  // wrote around it (closing a file handle, a DB cursor) would never run. Wrapping the whole body
  // in try/finally makes that cleanup happen on every exit path, not just normal completion.
  try {
    let current = await iterator.next();
    if (current.done === true) {
      // An empty stream is a legitimate outcome, not an error - a filter that matched nothing
      // produces one. `@arcadedb/driver`'s README establishes the same principle for `truncated`:
      // do not turn a legitimate outcome into an exception, and do not invent a result the server
      // did not give you. Empirically verified against a real server (task 6 of the M1B plan): a
      // single chunk with zero rows and `last: true` is accepted cleanly, in under 100ms, and
      // returns an all-zero `InsertSummary` - so this sends exactly that chunk and hands back
      // whatever summary the server gives back, rather than throwing.
      yield {
        database: request.database,
        credentials: request.credentials,
        options: { ...request.options, database: request.database },
        transaction: request.transaction,
        sessionId,
        chunkSeq: 1n,
        rows: [],
        last: true,
      };
      return;
    }

    let chunkSeq = 1n;
    for (;;) {
      const next = await iterator.next();
      const isLast = next.done === true;
      const isFirst = chunkSeq === 1n;

      yield {
        ...(isFirst ? { database: request.database } : {}),
        credentials: request.credentials,
        // Empirically verified against a real server (task 6 of the M1B plan, re-measured when
        // this package adopted the 26.10.1-SNAPSHOT contract): on 26.8.1 and every earlier
        // release, `InsertContext` builds itself from `InsertOptions.database` only and never
        // reads `InsertChunk.database` at all, despite the .proto contract documenting the latter
        // as REQUIRED on the first chunk. Without this mirror, a stream against such a server
        // inserts nothing - it reports `received` rows and `inserted: 0`, or fails on the
        // deferred commit with "Invalid database name: name is required" - even though `database`
        // was sent correctly per the .proto contract.
        //
        // Fixed server-side in ArcadeData/arcadedb#6597 (merged in 7ccade7348, RELEASED IN
        // 26.9.1, not unreleased as this comment previously claimed): a fixed server prefers a
        // non-empty `InsertChunk.database` and falls back to `InsertOptions.database`, so setting
        // both here can never diverge. Measured directly against 26.8.1, 26.9.1 and
        // 26.10.1-SNAPSHOT: a single-chunk stream carrying `database` on the chunk with
        // `options.database` left empty inserts 0 rows on 26.8.1 and 2 of 2 on both 26.9.1 and
        // 26.10.1-SNAPSHOT.
        //
        // Every server version this package claims support for (see the compatibility table in
        // the README - 26.9.1 and up) therefore carries the fix, so the mirror is belt-and-braces
        // rather than load-bearing today. It is kept because removing it is a behaviour change,
        // and is tracked as a follow-up rather than done here.
        options: isFirst ? { ...request.options, database: request.database } : request.options,
        transaction: request.transaction,
        sessionId,
        chunkSeq,
        rows: current.value,
        last: isLast,
      };

      if (isLast) return;
      current = next;
      chunkSeq += 1n;
    }
  } finally {
    await iterator.return?.();
  }
}

/**
 * `TimeSeriesWriteStream` request. `chunks` is the sequence of point batches the caller wants to
 * send - each element becomes exactly one wire `TimeSeriesWriteChunk`. Unlike
 * {@link InsertStreamRequest}, there is no session/sequence/last envelope for this wrapper to own:
 * `TimeSeriesWriteChunk` declares only `database`, `credentials`, `type` and `precision` alongside
 * its `points`, with no `session_id`, `chunk_seq` or `last` field on the message at all, so those
 * four are simply repeated on every chunk (see {@link createTimeSeriesWriteStream}).
 *
 * `precision` is REQUIRED here, deliberately - the one place this wrapper diverges from "pass
 * everything through unchanged". `TimeSeriesPrecision`'s proto3 zero value is
 * `TS_PRECISION_MILLISECONDS` (0), and the wire cannot distinguish "the caller omitted precision"
 * from "the caller explicitly chose milliseconds". The HTTP `/ts/{database}/write` endpoint speaks
 * InfluxDB Line Protocol, whose omitted-precision default is NANOSECONDS - a factor of 10^6 away.
 * A caller porting a working HTTP ingest to gRPC who drops this field would have every timestamp
 * misread by that factor, silently, with no error on either side. Requiring the field on this
 * wrapper's TypeScript type removes that failure mode by construction rather than documenting
 * around it.
 */
export interface TimeSeriesWriteStreamRequest {
  database: string;
  credentials?: MessageInitShape<typeof DatabaseCredentialsSchema>;
  /** Default measurement for points in a chunk that do not name one. */
  type: string;
  /** REQUIRED - see the interface doc comment above for why. */
  precision: TimeSeriesPrecision;
  /** One element per wire chunk. */
  chunks: AsyncIterable<TimeSeriesPoint[]>;
}

/**
 * Wraps `ArcadeDbService.TimeSeriesWriteStream` (client-streaming): turns `request.chunks` into
 * the `AsyncIterable<TimeSeriesWriteChunk>` the generated client expects, setting `database`,
 * `credentials`, `type` and `precision` on EVERY chunk rather than mirroring them onto the first
 * one the way {@link envelopeChunks} mirrors `database` into `options.database` for `InsertStream`
 * (D-M6-4). That mirror exists to work around
 * [ArcadeData/arcadedb#6597](https://github.com/ArcadeData/arcadedb/issues/6597), a bug confirmed
 * specific to `InsertStream`/`InsertContext` (closed, fixed in 26.9.1); `TimeSeriesWriteChunk`
 * carries none of `InsertChunk`'s session/sequence/last fields and was never shown to share that
 * bug, so copying the workaround here would be cargo-culting a fix onto an RPC that never needed
 * one - setting all four fields on every chunk is simply the contract-faithful reading of the
 * `.proto` (see the field comments on `TimeSeriesWriteChunk`).
 *
 * An empty `request.chunks` sends zero wire chunks and awaits whatever `TimeSeriesWriteSummary` the
 * server returns for a stream that carried none, rather than throwing - the same "an empty input is
 * a legitimate outcome" principle {@link createInsertStream} documents for `InsertStream`, without
 * that wrapper's single-empty-chunk special case: there is no first-chunk-only field here (no
 * `database`-on-chunk-1-only rule) that would otherwise go unset on an all-empty stream.
 *
 * Returns the server's `TimeSeriesWriteSummary` whole (D-M6-3): `received`, `written`, `dropped`,
 * `unknownTypes`, `nonTimeSeriesTypes`, `unavailableTypes` and `executionTimeMs` all survive
 * unchanged. A write is NOT atomic - each measurement's batch commits its own shard transaction as
 * it is appended - so a SUCCESSFUL call can still report `written < received`. A caller who checks
 * only that the returned promise resolved has not checked that its data landed; this wrapper never
 * reduces the summary to a boolean or a count.
 */
export function createTimeSeriesWriteStream(raw: Pick<RawClient, "timeSeriesWriteStream">) {
  return function timeSeriesWriteStream(
    request: TimeSeriesWriteStreamRequest,
    options?: CallOptions,
  ): Promise<TimeSeriesWriteSummary> {
    return raw.timeSeriesWriteStream(timeSeriesWriteChunks(request), options);
  };
}

async function* timeSeriesWriteChunks(request: TimeSeriesWriteStreamRequest): AsyncGenerator<TimeSeriesWriteChunkInit> {
  for await (const points of request.chunks) {
    yield {
      database: request.database,
      credentials: request.credentials,
      type: request.type,
      precision: request.precision,
      points,
    };
  }
}
