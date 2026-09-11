import { randomUUID } from "node:crypto";
import { GenericContainer, Wait } from "testcontainers";
import type { StartedTestContainer } from "testcontainers";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { MessageInitShape, MessageShape } from "@bufbuild/protobuf";
import { basicAuth, createClient as createHttpClient } from "../packages/driver/src/index.js";
import type { ArcadeDBServer } from "../packages/driver/src/index.js";
import { unwrap } from "../packages/driver/src/internal/unwrap.js";
import { bearerAuth, createClient as createGrpcClient, passwordAuth } from "../packages/driver-grpc/src/index.js";
import type { ArcadeDBGrpcClient, GrpcRecordSchema, GrpcValueSchema, InsertSummarySchema, Interceptor, QueryResultSchema } from "../packages/driver-grpc/src/index.js";
import { TimeSeriesPrecision } from "../packages/driver-grpc/src/gen/arcadedb-server-26.10.1-SNAPSHOT_pb.js";
import type { TimeSeriesPoint } from "../packages/driver-grpc/src/gen/arcadedb-server-26.10.1-SNAPSHOT_pb.js";

// Image pin: kept independent of `e2e/data-plane.test.ts`'s pin, even though both currently name
// the same tag. They agree because each is pinned to the release its own contract came from, not
// because this suite inherits the other's reasoning. The `.proto` and the OpenAPI spec are
// separate artifacts published from the same server release; if they ever stop moving together,
// these two pins move apart, and nothing here should make that awkward.
const DEFAULT_ARCADEDB_IMAGE = "arcadedata/arcadedb:26.10.1-SNAPSHOT";

// `ARCADEDB_DOCKER_IMAGE` overrides the pin - same variable name `e2e-js` and the HTTP e2e suite
// already use. The M2 smoke job in ArcadeData/arcadedb sets this to the image built from the
// server commit under review; honoring it here (not merely in data-plane.test.ts) is what lets
// that job actually exercise the gRPC data plane instead of silently covering HTTP alone.
const ARCADEDB_IMAGE = process.env.ARCADEDB_DOCKER_IMAGE ?? DEFAULT_ARCADEDB_IMAGE;

// Both facts below were verified against a real container while preparing this suite, and cost
// real time to discover - see the plan/report for this task.
//
// 1. The gRPC plugin is NOT enabled by default: `SERVER_PLUGINS` defaults to empty, so without
//    `-Darcadedb.server.plugins=GRPC:com.arcadedb.server.grpc.GrpcServerPlugin` nothing listens
//    on port 50051 at all.
// 2. The root password MUST be at least 8 characters. A shorter one kills the server at startup
//    with `ServerSecurityException: User password too short (<8 characters)`, and the only
//    visible symptom is a closed port 50051 - which reads exactly like "gRPC is broken in this
//    image" rather than "the whole server refused to start". `playwithdata` below is 12
//    characters, well clear of the limit.
const ROOT_PASSWORD = "playwithdata";
const DB_NAME = "clienttestgrpc";

let container: StartedTestContainer;
let httpBaseUrl: string;
let grpcBaseUrl: string;
let httpRoot: ArcadeDBServer;
let rootGrpc: ArcadeDBGrpcClient;

type GrpcRecordInit = MessageInitShape<typeof GrpcRecordSchema>;
type GrpcValueInit = MessageInitShape<typeof GrpcValueSchema>;
type QueryResultRecord = MessageShape<typeof QueryResultSchema>["records"][number];

/** Builds a `GrpcValue`-shaped `string_value` entry for a `GrpcRecord.properties` map. */
function stringProperty(value: string): GrpcValueInit {
  return { kind: { case: "stringValue", value } };
}

/** Reads a `string_value` property back off a `GrpcRecord` returned by the server. */
function readStringProperty(record: QueryResultRecord, key: string): string | undefined {
  const value = record.properties[key];
  return value?.kind.case === "stringValue" ? value.kind.value : undefined;
}

/** Builds a `GrpcValue`-shaped `double_value` entry, for a `TimeSeriesPoint.fields` map. */
function doubleProperty(value: number): GrpcValueInit {
  return { kind: { case: "doubleValue", value } };
}

/** Composes a call-recording wrapper around an auth interceptor: every outgoing RPC's method
 * name is pushed to `calls` before the (still fully functional) authenticated call proceeds.
 * Used by the rollback test to assert the MECHANISM (RollbackTransaction was actually issued,
 * CommitTransaction was not) rather than only the row-absence outcome - see that test for why
 * the outcome alone is not proof. */
function withCallRecording(auth: Interceptor, calls: string[]): Interceptor {
  return (next) => {
    const authenticated = auth(next);
    return async (req) => {
      calls.push(req.method.name);
      return authenticated(req);
    };
  };
}

beforeAll(async () => {
  container = await new GenericContainer(ARCADEDB_IMAGE)
    .withEnvironment({
      JAVA_OPTS:
        `-Darcadedb.server.rootPassword=${ROOT_PASSWORD} ` +
        "-Darcadedb.server.plugins=GRPC:com.arcadedb.server.grpc.GrpcServerPlugin",
    })
    // Exposed-but-not-bound: Testcontainers maps both ports to random host ports, so this
    // doesn't clash with any locally running ArcadeDB service.
    .withExposedPorts(2480, 50051)
    .withWaitStrategy(
      Wait.forAll([
        Wait.forHttp("/api/v1/ready", 2480).forStatusCodeMatching((statusCode) => statusCode === 204),
        // The success signal called out in the plan: this line only appears once the GRPC plugin
        // has finished starting and is actually listening on 50051.
        Wait.forLogMessage(/gRPC server started on 0\.0\.0\.0:50051/),
      ]),
    )
    .withStartupTimeout(60_000)
    .start();

  httpBaseUrl = `http://${container.getHost()}:${container.getMappedPort(2480)}`;
  grpcBaseUrl = `http://${container.getHost()}:${container.getMappedPort(50051)}`;

  httpRoot = createHttpClient({ baseUrl: httpBaseUrl, auth: basicAuth("root", ROOT_PASSWORD) });

  // There is no data-plane RPC to create a database, and the admin service is deliberately out
  // of scope for this package - so database (and schema) setup goes over HTTP, exactly as
  // `data-plane.test.ts` already does for the REST suite.
  await unwrap(
    httpRoot.raw.POST("/api/v1/server", {
      body: { command: `create database ${DB_NAME}`, language: "sql" },
    }),
  );

  const httpDb = httpRoot.db(DB_NAME);
  await httpDb.command({ language: "sql", command: "CREATE VERTEX TYPE Person IF NOT EXISTS" });
  await httpDb.command({ language: "sql", command: "CREATE VERTEX TYPE BatchPerson IF NOT EXISTS" });

  rootGrpc = createGrpcClient({
    baseUrl: grpcBaseUrl,
    auth: passwordAuth("root", ROOT_PASSWORD, DB_NAME),
    insecure: true,
  });
}, 90_000);

afterAll(async () => {
  await container?.stop();
});

describe("end-to-end against a real ArcadeDB gRPC server", () => {
  it("password auth works", async () => {
    const response = await rootGrpc.raw.executeQuery({ database: DB_NAME, query: "SELECT FROM Person", language: "sql" });
    expect(response.results).toBeDefined();
  });

  it("bearer auth works, using a token minted by POST /api/v1/login", async () => {
    const login = await unwrap(httpRoot.raw.POST("/api/v1/login", {}));
    expect(login.token).toBeDefined();
    if (!login.token) throw new Error("login did not return a token");
    expect(login.token).toMatch(/^AU-/);

    const bearerGrpc = createGrpcClient({ baseUrl: grpcBaseUrl, auth: bearerAuth(login.token) });
    const response = await bearerGrpc.raw.executeQuery({ database: DB_NAME, query: "SELECT FROM Person", language: "sql" });
    expect(response.results).toBeDefined();
  });

  it("executeCommand writes and streamQuery reads it back", async () => {
    const commandResponse = await rootGrpc.raw.executeCommand({
      database: DB_NAME,
      command: "INSERT INTO Person SET name = 'Alice'",
      language: "sql",
    });
    expect(commandResponse.success).toBe(true);

    const rows: QueryResultRecord[] = [];
    for await (const row of rootGrpc.streamQuery({
      database: DB_NAME,
      query: "SELECT FROM Person WHERE name = 'Alice'",
      language: "sql",
    })) {
      rows.push(row);
    }

    expect(rows).toHaveLength(1);
    expect(readStringProperty(rows[0], "name")).toBe("Alice");
  });

  it("insertStream ingests a batch and the InsertSummary matches what is queryable afterwards", async () => {
    function batchRow(name: string): GrpcRecordInit {
      return { type: "BatchPerson", properties: { name: stringProperty(name) } };
    }

    async function* chunks(): AsyncGenerator<GrpcRecordInit[]> {
      yield [batchRow("Batch1"), batchRow("Batch2")];
      yield [batchRow("Batch3"), batchRow("Batch4")];
    }

    // `targetClass` names the type the whole stream inserts into - the server resolves it from
    // `InsertOptions.targetClass` only; a per-row `GrpcRecord.type` (set on `batchRow` above for
    // documentation purposes) is not consulted by `insertStream`'s row-insert path.
    const summary = await rootGrpc.insertStream({
      database: DB_NAME,
      options: { targetClass: "BatchPerson" },
      chunks: chunks(),
    });

    expect(summary.failed).toBe(0n);
    expect(summary.inserted).toBe(4n);
    expect(summary.received).toBe(4n);

    const rows: QueryResultRecord[] = [];
    for await (const row of rootGrpc.streamQuery({ database: DB_NAME, query: "SELECT FROM BatchPerson", language: "sql" })) {
      rows.push(row);
    }

    expect(BigInt(rows.length)).toBe(summary.inserted);
  });

  it("a transaction commits, with writes visible afterwards", async () => {
    await rootGrpc.transaction(DB_NAME, async (tx) => {
      await tx.executeCommand({ command: "INSERT INTO Person SET name = 'Bob'", language: "sql" });
    });

    const rows: QueryResultRecord[] = [];
    for await (const row of rootGrpc.streamQuery({
      database: DB_NAME,
      query: "SELECT FROM Person WHERE name = 'Bob'",
      language: "sql",
    })) {
      rows.push(row);
    }

    expect(rows).toHaveLength(1);
  });

  it("a transaction whose body throws leaves no writes behind", async () => {
    // Asserts the MECHANISM, not merely the outcome. M1's HTTP e2e originally asserted only "the
    // row is absent afterwards" - that assertion PASSED even with the rollback call deleted from
    // the implementation, because an abandoned (never committed, never rolled back) transaction
    // also leaves its writes invisible, through ordinary isolation rather than cleanup. So this
    // test records every RPC method name the spied client actually issues and asserts
    // RollbackTransaction fired and CommitTransaction did not, in addition to the row-absence
    // check below. This was proven to catch a deleted rollback call - see this task's report.
    const calls: string[] = [];
    const spiedGrpc = createGrpcClient({
      baseUrl: grpcBaseUrl,
      auth: withCallRecording(passwordAuth("root", ROOT_PASSWORD, DB_NAME), calls),
      insecure: true,
    });

    await expect(
      spiedGrpc.transaction(DB_NAME, async (tx) => {
        await tx.executeCommand({ command: "INSERT INTO Person SET name = 'Carol'", language: "sql" });
        throw new Error("deliberate failure to force a rollback");
      }),
    ).rejects.toThrow("deliberate failure to force a rollback");

    expect(calls).toContain("RollbackTransaction");
    expect(calls).not.toContain("CommitTransaction");

    // Belt and suspenders, and the brief's explicit requirement: the row must also be ABSENT,
    // not merely that the promise rejected and RollbackTransaction was observed.
    const rows: QueryResultRecord[] = [];
    for await (const row of rootGrpc.streamQuery({
      database: DB_NAME,
      query: "SELECT FROM Person WHERE name = 'Carol'",
      language: "sql",
    })) {
      rows.push(row);
    }
    expect(rows).toHaveLength(0);
  });

  it("a single empty final insertStream chunk is accepted and returns an all-zero InsertSummary", async () => {
    // This test predates the fix: it bypassed `insertStream`'s wrapper (which used to throw on
    // an empty iterable) and talked to `raw.insertStream` directly to find out empirically
    // whether the server even accepts a zero-row final chunk, bounded by `timeoutMs` so an
    // unexpected server hang fails this one test instead of wedging the whole suite. It found
    // that the server accepts it cleanly - see this task's report - and that finding is now what
    // `insertStream` itself does for an empty iterable (see `src/stream.ts`). Kept as-is, still
    // going through `raw` rather than the wrapper, as a standing record of the server's own
    // behavior independent of the wrapper's.
    //
    // T1: this used to assert `outcome.kind === "summary" || outcome.kind === "error"` against a
    // try/catch that could only ever produce one of those two values - no server behaviour,
    // including the 15s timeout the comment above claims to test, could turn this test red.
    // `stream.ts`'s own empty-stream handling now depends on this exact server behaviour (see the
    // comment in `envelopeChunks`), so this pins the real contract: the call resolves (does not
    // throw) and comes back with every count at zero.
    async function* oneEmptyChunk() {
      // `options.database` is included alongside the chunk-level `database` the brief specifies,
      // for the same server-side reason `envelopeChunks` in `src/stream.ts` mirrors it: the
      // deployed server's `InsertContext` only reads `InsertOptions.database`, not
      // `InsertChunk.database`. Without it every chunk - empty or not - fails identically on
      // that unrelated gap, which would tell us nothing about empty-chunk handling specifically.
      // `options.targetClass` is set to an existing type for the same isolation reason: the
      // server resolves the target type unconditionally (before it ever looks at how many rows
      // the chunk carries), so a blank target_class would fail the probe on "type not found"
      // rather than telling us anything about zero-row handling specifically.
      yield {
        database: DB_NAME,
        options: { database: DB_NAME, targetClass: "BatchPerson" },
        sessionId: randomUUID(),
        chunkSeq: 1n,
        rows: [],
        last: true,
      };
    }

    let outcome: { kind: "summary"; value: MessageShape<typeof InsertSummarySchema> } | { kind: "error"; value: unknown };
    try {
      const summary = await rootGrpc.raw.insertStream(oneEmptyChunk(), { timeoutMs: 15_000 });
      outcome = { kind: "summary", value: summary };
    } catch (err) {
      outcome = { kind: "error", value: err };
    }

    expect(outcome.kind).toBe("summary");
    if (outcome.kind !== "summary") throw new Error("unreachable - asserted above");

    expect(outcome.value.received).toBe(0n);
    expect(outcome.value.inserted).toBe(0n);
    expect(outcome.value.updated).toBe(0n);
    expect(outcome.value.ignored).toBe(0n);
    expect(outcome.value.failed).toBe(0n);
    expect(outcome.value.errors).toEqual([]);
  });

  it("exists and listDatabases agree with what was created over HTTP", async () => {
    await expect(httpRoot.exists(DB_NAME)).resolves.toBe(true);
    await expect(httpRoot.listDatabases()).resolves.toContain(DB_NAME);
  });
});

// The exact DDL was worked out against a live container before any test file was touched - see
// task-4-report.md for the transcript. `embedding` must be declared `ARRAY_OF_FLOATS`, and
// `CREATE INDEX ... LSM_VECTOR` refuses to run without a `METADATA` clause naming `dimensions`;
// the server names both requirements in its own error message. There is no data-plane RPC for
// DDL, so - exactly like `Person`/`BatchPerson` above - the type, properties, index and rows are
// all created over HTTP; only the searches themselves run over gRPC.
const VECTOR_TYPE = "VectorItem";
const VECTOR_INDEX = "VectorItem[embedding]";
const FULLTEXT_INDEX = "VectorItem[description]";

describe("VectorSearch, HybridSearch and FullTextSearch: through raw outside a transaction, through the handle inside one", () => {
  beforeAll(async () => {
    const httpDb = httpRoot.db(DB_NAME);
    await httpDb.command({ language: "sql", command: `CREATE DOCUMENT TYPE ${VECTOR_TYPE} IF NOT EXISTS` });
    await httpDb.command({ language: "sql", command: `CREATE PROPERTY ${VECTOR_TYPE}.name STRING` });
    await httpDb.command({ language: "sql", command: `CREATE PROPERTY ${VECTOR_TYPE}.embedding ARRAY_OF_FLOATS` });
    await httpDb.command({ language: "sql", command: `CREATE PROPERTY ${VECTOR_TYPE}.description STRING` });
    await httpDb.command({
      language: "sql",
      command: `CREATE INDEX ON ${VECTOR_TYPE} (embedding) LSM_VECTOR METADATA {"dimensions": 4}`,
    });
    // `red-apple`'s embedding is the exact query vector every test below searches for, so it is
    // always the nearest neighbor (distance 0) and the only unambiguous "known term" full-text hit.
    await httpDb.command({
      language: "sql",
      command: `INSERT INTO ${VECTOR_TYPE} SET name = 'red-apple', embedding = [1,0,0,0], description = 'a bright red apple'`,
    });
    await httpDb.command({
      language: "sql",
      command: `INSERT INTO ${VECTOR_TYPE} SET name = 'green-apple', embedding = [0.9,0.1,0,0], description = 'a crisp green apple'`,
    });
    await httpDb.command({
      language: "sql",
      command: `INSERT INTO ${VECTOR_TYPE} SET name = 'blue-car', embedding = [0,0,1,0], description = 'a fast blue car engine'`,
    });
    await httpDb.command({ language: "sql", command: `CREATE INDEX ON ${VECTOR_TYPE} (description) FULL_TEXT` });
  }, 30_000);

  it("raw.vectorSearch, outside any transaction, returns a non-empty, nearest-first result", async () => {
    const result = await rootGrpc.raw.vectorSearch({
      database: DB_NAME,
      indexName: VECTOR_INDEX,
      queryVector: [1, 0, 0, 0],
      k: 10,
    });

    expect(result.results.length).toBeGreaterThan(0);
    expect(result.count).toBe(3);
    expect(result.truncated).toBe(false);
    expect(result.results[0]?.distance).toBe(0);
    const distances = result.results.map((r) => r.distance ?? Number.POSITIVE_INFINITY);
    expect(distances).toEqual([...distances].sort((a, b) => a - b));
  });

  it("raw.hybridSearch, outside any transaction, fuses both legs into a non-empty result", async () => {
    const result = await rootGrpc.raw.hybridSearch({
      database: DB_NAME,
      vectorIndexName: VECTOR_INDEX,
      queryVector: [1, 0, 0, 0],
      fulltextIndexName: FULLTEXT_INDEX,
      fulltextQuery: "apple",
      k: 10,
    });

    expect(result.results.length).toBeGreaterThan(0);
    expect(result.count).toBe(3);
    expect(result.fused).toBe(true);
  });

  it("raw.fullTextSearch, outside any transaction, matches a known term", async () => {
    const result = await rootGrpc.raw.fullTextSearch({ database: DB_NAME, indexName: FULLTEXT_INDEX, queryText: "apple" });

    expect(result.results.length).toBeGreaterThan(0);
    expect(result.count).toBe(2);
  });

  it("tx.vectorSearch, tx.hybridSearch and tx.fullTextSearch, bound to an open transaction, all return non-empty results (D-M5-1)", async () => {
    // No top-level `grpc.vectorSearch` alias exists - D-M5-1's point proven end to end: the same
    // RPC reached two ways, raw above and bound-to-a-transaction here, both against a real server.
    const [search, hybrid, fulltext] = await rootGrpc.transaction(DB_NAME, async (tx) => {
      const searchResult = await tx.vectorSearch({ indexName: VECTOR_INDEX, queryVector: [1, 0, 0, 0], k: 10 });
      const hybridResult = await tx.hybridSearch({
        vectorIndexName: VECTOR_INDEX,
        queryVector: [1, 0, 0, 0],
        fulltextIndexName: FULLTEXT_INDEX,
        fulltextQuery: "apple",
        k: 10,
      });
      const fulltextResult = await tx.fullTextSearch({ indexName: FULLTEXT_INDEX, queryText: "apple" });
      return [searchResult, hybridResult, fulltextResult] as const;
    });

    expect(search.results.length).toBeGreaterThan(0);
    expect(search.count).toBe(3);
    expect(search.truncated).toBe(false);

    expect(hybrid.results.length).toBeGreaterThan(0);
    expect(hybrid.fused).toBe(true);

    expect(fulltext.results.length).toBeGreaterThan(0);
    expect(fulltext.count).toBe(2);
  });
});

// The exact DDL was worked out against a live container before any test file was touched - see
// task-4-report.md for the transcript. `CREATE TIMESERIES TYPE` takes an inline TIMESTAMP column
// plus optional `TAGS (...)`/`FIELDS (...)` clauses in the SAME statement; there is no other way
// to declare a type's tag/field columns. Two things that look like they should work do not: a
// plain `CREATE PROPERTY` after the type exists adds the column to the schema listing, but the
// column is never populated by a time-series write, and neither is `ALTER PROPERTY ... CUSTOM
// role = "FIELD"` on top of it - both were tried against this server and both silently drop the
// column's values rather than raising. Only naming the column inside `CREATE TIMESERIES TYPE`
// itself, via `TAGS (...)`/`FIELDS (...)`, makes it a real tag/field column.
const TS_TYPE = "GrpcTsPoint";

describe("TimeSeriesWriteStream, TimeSeriesQuery and TimeSeriesLatest", () => {
  beforeAll(async () => {
    const httpDb = httpRoot.db(DB_NAME);
    await httpDb.command({
      language: "sql",
      command: `CREATE TIMESERIES TYPE ${TS_TYPE} TIMESTAMP ts TAGS (sensor STRING) FIELDS (value DOUBLE)`,
    });
  }, 30_000);

  it("a MULTI-CHUNK timeSeriesWriteStream reports written == the total points sent and dropped == 0", async () => {
    // Multi-chunk is the point: it is the only thing that can prove the per-chunk envelope
    // (database/type/precision repeated on every wire chunk, per D-M6-4) actually works end to
    // end - a unit test against a fake servicer cannot prove that, because the fake is not the
    // server.
    async function* chunks(): AsyncGenerator<TimeSeriesPoint[]> {
      yield [
        { timestamp: 1_000n, tags: { sensor: stringProperty("A") }, fields: { value: doubleProperty(1.1) } },
        { timestamp: 2_000n, tags: { sensor: stringProperty("A") }, fields: { value: doubleProperty(1.2) } },
      ] as TimeSeriesPoint[];
      yield [
        { timestamp: 3_000n, tags: { sensor: stringProperty("B") }, fields: { value: doubleProperty(2.1) } },
      ] as TimeSeriesPoint[];
    }

    const summary = await rootGrpc.timeSeriesWriteStream({
      database: DB_NAME,
      type: TS_TYPE,
      precision: TimeSeriesPrecision.TS_PRECISION_MILLISECONDS,
      chunks: chunks(),
    });

    expect(summary.received).toBe(3n);
    expect(summary.written).toBe(3n);
    expect(summary.dropped).toBe(0n);
  });

  it("an empty timeSeriesWriteStream sends zero wire chunks and the server answers with an all-zero summary, not an error", async () => {
    // Established empirically against a real server (see task-4-report.md): a stream that never
    // sends a single wire chunk - so the server never learns database, type or precision - is
    // accepted cleanly rather than rejected. This is the answer to the question stream.ts's own
    // doc comment for `createTimeSeriesWriteStream` leaves open ("an all-zero summary and an
    // error are both plausible outcomes... a real e2e run settles it"): it does NOT raise.
    async function* noChunks(): AsyncGenerator<TimeSeriesPoint[]> {
      // Yields nothing - zero wire chunks.
    }

    const summary = await rootGrpc.timeSeriesWriteStream({
      database: DB_NAME,
      type: TS_TYPE,
      precision: TimeSeriesPrecision.TS_PRECISION_MILLISECONDS,
      chunks: noChunks(),
    });

    expect(summary.received).toBe(0n);
    expect(summary.written).toBe(0n);
    expect(summary.dropped).toBe(0n);
    expect(summary.unknownTypes).toEqual([]);
    expect(summary.nonTimeSeriesTypes).toEqual([]);
    expect(summary.unavailableTypes).toEqual([]);
  });

  it("timeSeriesQuery returns the points written above, non-empty", async () => {
    const results = [];
    for await (const result of rootGrpc.timeSeriesQuery({ database: DB_NAME, type: TS_TYPE })) {
      results.push(result);
    }

    const rows = results.flatMap((result) => result.rows);
    expect(rows.length).toBeGreaterThan(0);
  });

  it("timeSeriesLatest, bound to an open transaction handle, returns the most recently written point", async () => {
    // No top-level `timeSeriesLatest` alias exists on `ArcadeDBGrpcClient` (see index.ts) - the
    // only wrapped way to reach it is through a transaction handle, which is what this test
    // exercises; `timeSeriesQuery` above already covers the top-level (non-transactional) path.
    const latest = await rootGrpc.transaction(DB_NAME, async (tx) => tx.timeSeriesLatest({ type: TS_TYPE }));

    expect(latest.found).toBe(true);
    const tsColumn = latest.columns.indexOf("ts");
    expect(tsColumn).toBeGreaterThanOrEqual(0);
    const tsValue = latest.latest?.values[tsColumn];
    expect(tsValue?.kind.case).toBe("int64Value");
    // The most recently written point above carries timestamp 3000.
    expect(tsValue?.kind.case === "int64Value" ? tsValue.kind.value : undefined).toBe(3_000n);
  });
});
