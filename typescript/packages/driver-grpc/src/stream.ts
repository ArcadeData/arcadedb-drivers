import { randomUUID } from "node:crypto";
import type { CallOptions, Client } from "@connectrpc/connect";
import type { MessageInitShape, MessageShape } from "@bufbuild/protobuf";
import type { ArcadeDbService } from "./gen/arcadedb-server-26.10.1-SNAPSHOT_pb.js";
import {
  DatabaseCredentialsSchema,
  GrpcRecordSchema,
  InsertChunkSchema,
  InsertOptionsSchema,
  InsertSummarySchema,
  QueryResultSchema,
  StreamQueryRequestSchema,
  TransactionContextSchema,
} from "./gen/arcadedb-server-26.10.1-SNAPSHOT_pb.js";

/** The generated Connect client for `com.arcadedb.grpc.ArcadeDbService`. */
type RawClient = Client<typeof ArcadeDbService>;

type GrpcRecordInit = MessageInitShape<typeof GrpcRecordSchema>;
type QueryResult = MessageShape<typeof QueryResultSchema>;
type InsertSummary = MessageShape<typeof InsertSummarySchema>;
type InsertChunkInit = MessageInitShape<typeof InsertChunkSchema>;

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
   * `7ccade7348`, not yet in a release as of this writing): such a server re-reads a non-empty
   * chunk `database` on every chunk it appears on, it is not cached. 26.10.1-SNAPSHOT and every earlier
   * server ignore it entirely, which is why {@link envelopeChunks} also mirrors it into
   * `options.database` on the first chunk - see the comment there.
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
        // Empirically verified against a real server (task 6 of the M1B plan): on 26.10.1-SNAPSHOT and
        // every earlier release, `InsertContext` builds itself from `InsertOptions.database`
        // only and never reads `InsertChunk.database` at all, despite the .proto contract
        // documenting the latter as REQUIRED on the first chunk. Without this mirror, every
        // stream against such a server fails on the deferred commit with "Invalid database name:
        // name is required", even though `database` was sent correctly per the .proto contract.
        // Fixed server-side in ArcadeData/arcadedb#6597 (merged in 7ccade7348, not yet in a
        // release as of this writing): a fixed server prefers a non-empty `InsertChunk.database`
        // and falls back to `InsertOptions.database`, so setting both here can never diverge and
        // keeps this wrapper working against every server this package supports, fixed or not.
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
