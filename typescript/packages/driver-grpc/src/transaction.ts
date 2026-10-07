import type { CallOptions, Client } from "@connectrpc/connect";
import type { MessageInitShape } from "@bufbuild/protobuf";
import type { ArcadeDbService } from "./gen/arcadedb-server-26.11.1-SNAPSHOT_pb.js";
import { TransactionContextSchema } from "./gen/arcadedb-server-26.11.1-SNAPSHOT_pb.js";
import { createInsertStream, createStreamQuery, createTimeSeriesQuery } from "./stream.js";

/** The generated Connect client for `com.arcadedb.grpc.ArcadeDbService`. */
type RawClient = Client<typeof ArcadeDbService>;

type TransactionContextInit = MessageInitShape<typeof TransactionContextSchema>;

/**
 * The data-plane calls available inside a {@link createTransaction} callback, each with the
 * transaction's context bound in automatically - the caller never sets `database` or
 * `transaction` itself. Deliberately excludes `beginTransaction` / `commitTransaction` /
 * `rollbackTransaction` (owned by the wrapper) and the two RPCs the design spec keeps
 * unwrapped (`insertBidirectional`, `graphBatchLoad` - reachable, unwrapped, via `client.raw`).
 *
 * Also excludes `bulkInsert`, which stays reachable only through `client.raw.bulkInsert` (the same
 * parity bar that keeps `graphBatchLoad` raw-only). `insertStream` IS included - see its own doc
 * below for the server-version caveat that applies to it.
 */
export interface TransactionHandle {
  executeQuery: RawClient["executeQuery"];
  executeCommand: RawClient["executeCommand"];
  createRecord: RawClient["createRecord"];
  updateRecord: RawClient["updateRecord"];
  deleteRecord: RawClient["deleteRecord"];
  lookupByRid: RawClient["lookupByRid"];
  vectorSearch: RawClient["vectorSearch"];
  hybridSearch: RawClient["hybridSearch"];
  fullTextSearch: RawClient["fullTextSearch"];
  /** See {@link createStreamQuery}; bound to this transaction. */
  streamQuery: ReturnType<typeof createStreamQuery>;
  /**
   * See {@link createTimeSeriesQuery}; bound to this transaction. `TimeSeriesQueryRequest` carries
   * a `transaction` field (issue #7370: a query naming an open transaction runs on that
   * transaction's own thread and observes its uncommitted points; without it the read runs on a
   * gRPC worker and sees only committed data), so this is the same shape as `streamQuery` above.
   */
  timeSeriesQuery: ReturnType<typeof createTimeSeriesQuery>;
  /**
   * `TimeSeriesLatest` also carries a `transaction` field, for the same reason as
   * `timeSeriesQuery` above, but it is unary - there is no batching or flattening for a wrapper to
   * own, so it is bound directly rather than through a `create*` wrapper the way
   * `executeQuery`/`vectorSearch`/etc. are above.
   */
  timeSeriesLatest: RawClient["timeSeriesLatest"];
  /**
   * See {@link createInsertStream}; bound to this transaction. Same request and return as the
   * client's own `insertStream`, and the same chunk envelope (it IS the client's implementation):
   * `database` on the first chunk only, `transaction`, `options` and `credentials` on every chunk.
   * Whatever `database` and `transaction` the caller puts on the request are replaced, as for
   * every other handle method, with this transaction's database and a bare `{ transactionId,
   * database }` context - no `commit`/`rollback` flags survive - so the rows commit or roll back
   * with the transaction.
   *
   * That depends on a server that reads the chunk's transaction context: servers before 26.9.1
   * ignored it on `InsertStream`
   * ([ArcadeData/arcadedb#6607](https://github.com/ArcadeData/arcadedb/issues/6607), fixed in
   * `79d931070b`) and committed the rows on their own, so they survived a rollback. Those servers
   * are outside this package's compatibility table.
   */
  insertStream: ReturnType<typeof createInsertStream>;
}

/**
 * Forces `database` and `transaction` onto `request`, overriding whatever the caller supplied.
 * This is the mechanism that makes `transaction()` safe: a caller cannot forget, drop, or
 * mismatch the transaction id the way the 2026-07 gRPC audit found three times (#5040-#5042) -
 * every request made through a `TransactionHandle` carries the bound transaction's id, always.
 */
function bindTransaction<T extends { database?: string; transaction?: TransactionContextInit }>(
  request: T,
  database: string,
  transactionId: string,
): T {
  return { ...request, database, transaction: { transactionId, database } };
}

function createHandle(raw: RawClient, database: string, transactionId: string): TransactionHandle {
  const bound = <T extends { database?: string; transaction?: TransactionContextInit }, R>(
    call: (request: T, options?: CallOptions) => R,
  ) => {
    return (request: T, options?: CallOptions): R => call(bindTransaction(request, database, transactionId), options);
  };

  // `streamQuery`'s ergonomic wrapper (batch flattening) is reused as-is; only the underlying raw
  // call it forwards to is bound to this transaction.
  const streamRaw: Parameters<typeof createStreamQuery>[0] = { streamQuery: bound(raw.streamQuery) };
  // Same pattern as `streamRaw` above: `createTimeSeriesQuery`'s wrapper is reused as-is, only the
  // underlying raw call it forwards to is bound to this transaction. Do not bind `timeSeriesQuery`
  // directly and skip the wrapper - that would be a second binding path alongside this one.
  const timeSeriesQueryRaw: Parameters<typeof createTimeSeriesQuery>[0] = { timeSeriesQuery: bound(raw.timeSeriesQuery) };

  return {
    executeQuery: bound(raw.executeQuery),
    executeCommand: bound(raw.executeCommand),
    createRecord: bound(raw.createRecord),
    updateRecord: bound(raw.updateRecord),
    deleteRecord: bound(raw.deleteRecord),
    lookupByRid: bound(raw.lookupByRid),
    vectorSearch: bound(raw.vectorSearch),
    hybridSearch: bound(raw.hybridSearch),
    fullTextSearch: bound(raw.fullTextSearch),
    streamQuery: createStreamQuery(streamRaw),
    timeSeriesQuery: createTimeSeriesQuery(timeSeriesQueryRaw),
    timeSeriesLatest: bound(raw.timeSeriesLatest),
    // The client's own `insertStream` wrapper, bound at the request level: `InsertStreamRequest`
    // carries `database` and `transaction` like every other request here, so the same `bound`
    // override applies before the envelope is built, and the envelope logic is not duplicated.
    insertStream: bound(createInsertStream(raw)),
  };
}

/** Best-effort: releases the server-side transaction. Its own failure is deliberately swallowed
 * so it never masks the caller's real error (the body's throw, or a failed commit). */
async function safeRollback(raw: RawClient, database: string, transactionId: string): Promise<void> {
  try {
    await raw.rollbackTransaction({ transaction: { transactionId, database } });
  } catch {
    // Discarded - see the doc comment above.
  }
}

/**
 * Builds the `transaction(database, fn)` method: begins a server-side transaction, hands `fn` a
 * {@link TransactionHandle} whose calls all carry the transaction's id automatically, and ends
 * the transaction on both the success and failure paths.
 *
 * - `beginTransaction`'s response is validated before it is trusted: a missing or blank
 *   `transactionId` throws immediately, rather than handing `fn` a handle whose every call binds
 *   an empty id - on this server a blank transaction id means "no external transaction, use the
 *   auto-transaction path", so every statement would silently auto-commit and rollback would
 *   become a no-op while this wrapper reported success.
 * - `fn` resolving normally commits.
 * - `fn` throwing or rejecting - synchronously or otherwise - rolls back and re-throws `fn`'s
 *   original error unchanged. If the rollback itself fails, that failure is attached as `cause`
 *   on `fn`'s error (only when `fn`'s error is an `Error` with no `cause` already, so a
 *   caller-set causal chain is never overwritten), and swallowed if attaching it throws - some
 *   errors are frozen/non-extensible, and assigning `cause` on those throws under strict-mode
 *   ESM. `fn`'s error is re-thrown as itself either way.
 * - A resolved `commitTransaction` call is not, by itself, proof of a commit: the server answers
 *   a transaction id it no longer recognises (e.g. reaped after sitting idle past the server's
 *   idle timeout) with `success=true, committed=false` and no error status at all. This wrapper
 *   reads `committed` and throws (including the server's `message`) when it is false, rather than
 *   reporting success for a transaction whose writes were silently lost.
 * - A failing commit issues a best-effort rollback (its own failure is swallowed - the server
 *   would otherwise hold the transaction open until it's reaped) and re-throws the commit error.
 */
export function createTransaction(raw: RawClient) {
  return async function transaction<T>(database: string, fn: (tx: TransactionHandle) => Promise<T>): Promise<T> {
    const begun = await raw.beginTransaction({ database });
    if (!begun.transactionId || begun.transactionId.trim() === "") {
      throw new Error(
        `transaction: beginTransaction did not return a transaction id for database "${database}" - ` +
          "refusing to run the callback outside a real transaction.",
      );
    }
    const tx = createHandle(raw, database, begun.transactionId);

    let result: T;
    try {
      result = await fn(tx);
    } catch (err) {
      try {
        await raw.rollbackTransaction({ transaction: { transactionId: begun.transactionId, database } });
      } catch (rollbackErr) {
        if (err instanceof Error) {
          try {
            if (err.cause === undefined) err.cause = rollbackErr;
          } catch {
            // err is frozen/non-extensible - assigning `cause` would throw in strict-mode ESM.
            // The rollback failure is dropped in that case; err is re-thrown as itself below.
          }
        }
      }
      throw err;
    }

    try {
      const committed = await raw.commitTransaction({ transaction: { transactionId: begun.transactionId, database } });
      if (!committed.committed) {
        throw new Error(
          `transaction: commit for database "${database}" (transactionId=${begun.transactionId}) did not take ` +
            `effect: ${committed.message || "no message from server"}`,
        );
      }
    } catch (commitErr) {
      await safeRollback(raw, database, begun.transactionId);
      throw commitErr;
    }

    return result;
  };
}
