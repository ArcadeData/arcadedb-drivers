import { describe, expect, it } from "vitest";
import type { MessageInitShape, MessageShape } from "@bufbuild/protobuf";
import {
  InsertChunkSchema,
  InsertSummarySchema,
  QueryResultSchema,
  StreamQueryRequest_RetrievalMode,
  StreamQueryRequestSchema,
} from "../src/gen/arcadedb-server-26.10.1-SNAPSHOT_pb.js";
import { createInsertStream, createStreamQuery } from "../src/stream.js";

type QueryResult = MessageShape<typeof QueryResultSchema>;
type InsertChunk = MessageInitShape<typeof InsertChunkSchema>;
type InsertSummary = MessageShape<typeof InsertSummarySchema>;

/** Builds a minimal `QueryResult`-shaped object, only the fields these tests exercise. */
function queryResult(records: QueryResult["records"]): QueryResult {
  return {
    $typeName: "com.arcadedb.grpc.QueryResult",
    records,
    totalRecordsInBatch: records.length,
    runningTotalEmitted: 0n,
    isLastBatch: false,
  };
}

function record(rid: string): QueryResult["records"][number] {
  return { $typeName: "com.arcadedb.grpc.GrpcRecord", rid, type: "V", properties: {} };
}

/** Builds a full `InsertSummary`-shaped object (all fields the schema declares), so fixtures
 * used across these tests reflect the real wire shape rather than an invented one. */
function insertSummary(overrides: Partial<InsertSummary> = {}): InsertSummary {
  return {
    $typeName: "com.arcadedb.grpc.InsertSummary",
    received: 0n,
    inserted: 0n,
    updated: 0n,
    ignored: 0n,
    failed: 0n,
    errors: [],
    executionTimeMs: 0n,
    startedAt: undefined,
    finishedAt: undefined,
    ...overrides,
  };
}

describe("streamQuery", () => {
  it("yields each row from the server stream, flattened across batches", async () => {
    async function* fakeServerStream(): AsyncGenerator<QueryResult> {
      yield queryResult([record("#1:0"), record("#1:1")]);
      yield queryResult([record("#1:2")]);
    }

    const raw = { streamQuery: () => fakeServerStream() };
    const streamQuery = createStreamQuery(raw);

    const rows: string[] = [];
    for await (const row of streamQuery({ database: "mydb", query: "SELECT FROM V" })) {
      rows.push(row.rid);
    }

    expect(rows).toEqual(["#1:0", "#1:1", "#1:2"]);
  });

  it("passes retrievalMode and batchSize through unchanged, without defaulting", async () => {
    let seenRequest: MessageInitShape<typeof StreamQueryRequestSchema> | undefined;

    const raw = {
      streamQuery: (request: MessageInitShape<typeof StreamQueryRequestSchema>) => {
        seenRequest = request;
        return (async function* () {})();
      },
    };
    const streamQuery = createStreamQuery(raw);

    const request = {
      database: "mydb",
      query: "SELECT FROM V",
      retrievalMode: StreamQueryRequest_RetrievalMode.PAGED,
      batchSize: 250,
    };
    // Drain the generator without binding an unused loop variable.
    const rows = streamQuery(request);
    for (let step = await rows.next(); !step.done; step = await rows.next());

    expect(seenRequest?.retrievalMode).toBe(StreamQueryRequest_RetrievalMode.PAGED);
    expect(seenRequest?.batchSize).toBe(250);
  });

  it("does not default retrievalMode or batchSize when the caller omits them (T2)", async () => {
    // The previous version of this test supplied both fields, so it could not tell "passed
    // through unchanged" from "a default happens to match what was supplied" - adding a default
    // of PAGED/250 would still have left it green. Omitting both and asserting `undefined` proves
    // this wrapper genuinely never picks a value on the caller's behalf.
    let seenRequest: MessageInitShape<typeof StreamQueryRequestSchema> | undefined;

    const raw = {
      streamQuery: (request: MessageInitShape<typeof StreamQueryRequestSchema>) => {
        seenRequest = request;
        return (async function* () {})();
      },
    };
    const streamQuery = createStreamQuery(raw);

    const request = { database: "mydb", query: "SELECT FROM V" };
    const rows = streamQuery(request);
    for (let step = await rows.next(); !step.done; step = await rows.next());

    expect(seenRequest?.retrievalMode).toBeUndefined();
    expect(seenRequest?.batchSize).toBeUndefined();
  });
});

describe("insertStream", () => {
  /** Drives `raw.insertStream`'s async iterable to completion and records every chunk sent,
   * mimicking what a real Connect transport would consume off the wire. */
  function mockRaw(summary: InsertSummary) {
    const sent: InsertChunk[] = [];
    const raw = {
      insertStream: async (request: AsyncIterable<InsertChunk>): Promise<InsertSummary> => {
        for await (const chunk of request) sent.push(chunk);
        return summary;
      },
    };
    return { raw, sent };
  }

  async function* rowBatches(): AsyncGenerator<InsertChunk["rows"]> {
    yield [{ rid: "", type: "V", properties: {} }];
    yield [{ rid: "", type: "V", properties: {} }];
    yield [{ rid: "", type: "V", properties: {} }];
  }

  it("uses exactly one non-empty session_id for the whole stream", async () => {
    const { raw, sent } = mockRaw(insertSummary({ received: 3n }));
    const insertStream = createInsertStream(raw);

    await insertStream({ database: "mydb", chunks: rowBatches() });

    expect(sent).toHaveLength(3);
    const sessionIds = new Set(sent.map((chunk) => chunk.sessionId));
    expect(sessionIds.size).toBe(1);
    expect([...sessionIds][0]).toBeTruthy();
  });

  it("starts chunk_seq at 1 and increments by 1", async () => {
    const { raw, sent } = mockRaw(insertSummary());
    const insertStream = createInsertStream(raw);

    await insertStream({ database: "mydb", chunks: rowBatches() });

    expect(sent.map((chunk) => chunk.chunkSeq)).toEqual([1n, 2n, 3n]);
  });

  it("sets database on the first chunk only", async () => {
    const { raw, sent } = mockRaw(insertSummary());
    const insertStream = createInsertStream(raw);

    await insertStream({ database: "mydb", chunks: rowBatches() });

    expect(sent[0]?.database).toBe("mydb");
    expect(sent[1]?.database).toBeUndefined();
    expect(sent[2]?.database).toBeUndefined();
  });

  it("mirrors database into options.database on the first chunk only, working around a server-side gap", async () => {
    // Regression test for a real-server finding (task 6 of the M1B plan), filed as
    // ArcadeData/arcadedb#6597: on 26.10.1-SNAPSHOT and every earlier server, `ArcadeDbGrpcService
    // #insertStream` builds its `InsertContext` from `InsertOptions.database` only and never
    // reads `InsertChunk.database`, even though the .proto contract documents the latter as
    // REQUIRED on the first chunk. Without mirroring `database` into `options.database`, every
    // real stream against such a server fails at the deferred commit with "Invalid database
    // name: name is required". Servers carrying the fix (7ccade7348) honour a non-empty
    // `InsertChunk.database` and treat `InsertOptions.database` as the fallback, so the two
    // paths agree and the mirroring stays for as long as released servers need it.
    const { raw, sent } = mockRaw(insertSummary());
    const insertStream = createInsertStream(raw);

    await insertStream({ database: "mydb", options: { targetClass: "Person" }, chunks: rowBatches() });

    expect(sent[0]?.options?.database).toBe("mydb");
    // The caller's other options survive the merge.
    expect(sent[0]?.options?.targetClass).toBe("Person");
    // Subsequent chunks are untouched: no invented database, and the caller's options (or lack
    // thereof) pass through as given rather than being forced to repeat `database`.
    expect(sent[1]?.options?.database).toBeUndefined();
    expect(sent[1]?.options?.targetClass).toBe("Person");
  });

  it("marks only the final chunk as last", async () => {
    const { raw, sent } = mockRaw(insertSummary());
    const insertStream = createInsertStream(raw);

    await insertStream({ database: "mydb", chunks: rowBatches() });

    expect(sent.map((chunk) => chunk.last)).toEqual([false, false, true]);
  });

  it("returns the server's InsertSummary", async () => {
    const summary = insertSummary({ inserted: 42n });
    const { raw } = mockRaw(summary);
    const insertStream = createInsertStream(raw);

    const result = await insertStream({ database: "mydb", chunks: rowBatches() });

    expect(result).toBe(summary);
  });

  it("sends one empty final chunk and returns the server's summary when chunks is empty", async () => {
    // An empty stream is a legitimate outcome (a filter that matched nothing produces one), not
    // an error - empirically verified against a real server (task 6 of the M1B plan): a single
    // chunk with zero rows and `last: true` is accepted cleanly and returns an all-zero
    // `InsertSummary` in under 100ms. This asserts the wrapper sends exactly that chunk rather
    // than throwing, and hands back the server's own summary unchanged.
    const summary = insertSummary();
    const { raw, sent } = mockRaw(summary);
    const insertStream = createInsertStream(raw);

    async function* noBatches(): AsyncGenerator<InsertChunk["rows"]> {
      // Yields nothing.
    }

    const result = await insertStream({ database: "mydb", chunks: noBatches() });

    expect(sent).toHaveLength(1);
    expect(sent[0]?.rows).toEqual([]);
    expect(sent[0]?.last).toBe(true);
    expect(sent[0]?.database).toBe("mydb");
    expect(result).toBe(summary);
  });

  it("finalizes the caller's chunk iterator when the RPC consumption aborts mid-stream (I3)", async () => {
    // `envelopeChunks` pulls the caller's async iterator manually (not via `for await...of`), so
    // without an explicit try/finally an abandoned RPC never runs the caller's `finally` - file
    // handles, DB cursors, etc. behind a caller-supplied generator would leak. Simulating an
    // aborted RPC by calling `.return()` on the enveloped stream after only a partial read proves
    // that abandonment propagates back to the caller's own iterator.
    let cleanedUp = false;
    async function* rows(): AsyncGenerator<InsertChunk["rows"]> {
      try {
        yield [{ rid: "", type: "V", properties: {} }];
        yield [{ rid: "", type: "V", properties: {} }];
        yield [{ rid: "", type: "V", properties: {} }];
      } finally {
        cleanedUp = true;
      }
    }

    const raw = {
      insertStream: async (request: AsyncIterable<InsertChunk>): Promise<InsertSummary> => {
        const iterator = request[Symbol.asyncIterator]();
        await iterator.next(); // consume only the first envelope chunk
        await iterator.return?.(); // simulate the RPC aborting mid-stream
        return insertSummary();
      },
    };
    const insertStream = createInsertStream(raw);

    await insertStream({ database: "mydb", chunks: rows() });

    expect(cleanedUp).toBe(true);
  });
});
