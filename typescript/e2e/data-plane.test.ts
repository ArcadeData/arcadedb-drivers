import { GenericContainer, Wait } from "testcontainers";
import type { StartedTestContainer } from "testcontainers";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { basicAuth, bearerAuth, createClient } from "../packages/driver/src/index.js";
import type { ArcadeDBServer } from "../packages/driver/src/index.js";
import type { NdJsonQueryEvent } from "../packages/driver/src/facade/stream.js";
import { unwrap } from "../packages/driver/src/internal/unwrap.js";

// Image pin: `arcadedata/arcadedb:26.10.1-SNAPSHOT` is the release the committed OpenAPI contract was
// generated from, so the client under test and the server it runs against are the same version.
//
// That was not true until this pin moved. It sat at 26.8.1 - a release predating M0 - and needed
// a paragraph arguing why a client generated from a newer contract still worked against an older
// server: the M0 changes were documentation fixes to spec-generator classes, and the server had
// always answered 204 with `arcadedb-session-id` and always demanded `CommandRequest.language`
// (upstream fix #6562). That argument was sound but load-bearing, and it had to be re-made on
// every bump. Pinning to the contract's own release retires it. Move this pin with the contract
// and it stays retired.
const DEFAULT_ARCADEDB_IMAGE = "arcadedata/arcadedb:26.10.1-SNAPSHOT";

// `ARCADEDB_DOCKER_IMAGE` overrides the pin. It exists for the smoke job in ArcadeData/arcadedb,
// which runs this suite against the image built from the server commit under review rather than
// against a published tag. That is the only check that catches a payload-shape change on the PR
// that introduces one: the anti-drift test there (ArcadeData/arcadedb#4896) compares registered
// ROUTES, so it is blind to a request-body schema or a header that stops matching the handler.
//
// The variable name matches the one ArcadeDB's own `e2e-js` suite already uses, so the two
// harnesses are driven the same way.
//
// Locally and in this repository's CI the variable is unset, and the pin above applies.
const ARCADEDB_IMAGE = process.env.ARCADEDB_DOCKER_IMAGE ?? DEFAULT_ARCADEDB_IMAGE;

const ROOT_PASSWORD = "playwithdata";
const DB_NAME = "clienttest";

let container: StartedTestContainer;
let rootServer: ArcadeDBServer;
let baseUrl: string;

beforeAll(async () => {
  container = await new GenericContainer(ARCADEDB_IMAGE)
    .withEnvironment({ JAVA_OPTS: `-Darcadedb.server.rootPassword=${ROOT_PASSWORD}` })
    // Exposed-but-not-bound: Testcontainers maps 2480 to a random host port. This machine already
    // has an ArcadeDB service listening on host port 2480, so binding directly would clash.
    .withExposedPorts(2480)
    .withWaitStrategy(Wait.forHttp("/api/v1/ready", 2480).forStatusCodeMatching((statusCode) => statusCode === 204))
    .withStartupTimeout(60_000)
    .start();

  baseUrl = `http://${container.getHost()}:${container.getMappedPort(2480)}`;
  rootServer = createClient({ baseUrl, auth: basicAuth("root", ROOT_PASSWORD) });

  // No dedicated "create database" REST endpoint exists; database creation goes through the
  // generic server-command endpoint (POST /api/v1/server, body { command, language }), the same
  // one root-only administrative commands (drop database, create user, ...) share.
  await unwrap(
    rootServer.raw.POST("/api/v1/server", {
      body: { command: `create database ${DB_NAME}`, language: "sql" },
    }),
  );

  await rootServer.db(DB_NAME).command({ language: "sql", command: "CREATE VERTEX TYPE Person IF NOT EXISTS" });
}, 90_000);

afterAll(async () => {
  await container?.stop();
});

describe("end-to-end against a real ArcadeDB server", () => {
  it("basic auth works", async () => {
    await expect(rootServer.exists(DB_NAME)).resolves.toBe(true);
  });

  it("bearer auth works, using a token minted by POST /api/v1/login", async () => {
    const login = await unwrap(rootServer.raw.POST("/api/v1/login", {}));
    expect(login.token).toBeDefined();
    if (!login.token) throw new Error("login did not return a token");
    expect(login.token).toMatch(/^AU-/);

    const bearerServer = createClient({ baseUrl, auth: bearerAuth(login.token) });
    await expect(bearerServer.exists(DB_NAME)).resolves.toBe(true);
  });

  it("command inserts and query reads it back", async () => {
    const db = rootServer.db(DB_NAME);

    await db.command({ language: "sql", command: "INSERT INTO Person SET name = 'Alice'" });

    const envelope = await db.query<{ name: string }>({
      language: "sql",
      command: "SELECT FROM Person WHERE name = 'Alice'",
    });

    expect(envelope.result).toHaveLength(1);
    expect(envelope.result[0].name).toBe("Alice");
  });

  it("a transaction commits and its writes are visible afterwards", async () => {
    const db = rootServer.db(DB_NAME);

    await db.transaction(async (tx) => {
      await tx.command({ language: "sql", command: "INSERT INTO Person SET name = 'Bob'" });
    });

    const envelope = await db.query({ language: "sql", command: "SELECT FROM Person WHERE name = 'Bob'" });
    expect(envelope.result).toHaveLength(1);
  });

  it("a transaction whose body throws leaves no writes behind", async () => {
    // Wraps the real fetch to record which endpoints were actually hit, while every request still
    // goes to the live container. This is needed because absence of the row alone is not proof of
    // a correct rollback: an abandoned session that is never committed OR rolled back also leaves
    // the write invisible (ordinary transactional isolation), so that assertion by itself cannot
    // tell "rolled back" apart from "leaked". Confirmed by temporarily deleting the
    // `rollbackTransaction` call from `ArcadeDBDatabase.transaction` - the row-absence-only version
    // of this test still passed, for the wrong reason.
    const calls: { path: string; status: number }[] = [];
    const spiedServer = createClient({
      baseUrl,
      auth: basicAuth("root", ROOT_PASSWORD),
      fetch: async (request) => {
        const response = await fetch(request);
        calls.push({ path: new URL(request.url).pathname, status: response.status });
        return response;
      },
    });
    const db = spiedServer.db(DB_NAME);

    await expect(
      db.transaction(async (tx) => {
        await tx.command({ language: "sql", command: "INSERT INTO Person SET name = 'Carol'" });
        throw new Error("deliberate failure to force a rollback");
      }),
    ).rejects.toThrow("deliberate failure to force a rollback");

    const rollbackCall = calls.find((c) => c.path === `/api/v1/rollback/${DB_NAME}`);
    expect(rollbackCall).toBeDefined();
    expect(rollbackCall?.status).toBe(204);
    expect(calls.some((c) => c.path === `/api/v1/commit/${DB_NAME}`)).toBe(false);

    // Belt and suspenders, and the brief's explicit requirement: the row must also be ABSENT, not
    // merely that the promise rejected and rollback was called.
    const envelope = await db.query({ language: "sql", command: "SELECT FROM Person WHERE name = 'Carol'" });
    expect(envelope.result).toHaveLength(0);
  });

  it("exists and listDatabases agree with what was created", async () => {
    await expect(rootServer.exists(DB_NAME)).resolves.toBe(true);
    await expect(rootServer.listDatabases()).resolves.toContain(DB_NAME);
  });
});

// STREAM_ROW_COUNT and STREAM_PAYLOAD_SIZE were worked out empirically against a live container
// before this describe block was written, not guessed - see task-4-report.md for the transcript
// of chunk counts measured at increasing row counts. A handful of rows arrives from a real server
// in a single ndjson chunk (one `reader.read()`), which would let a decoder with no cross-chunk
// buffering at all pass this suite for the wrong reason - the exact defect `stream.test.ts`'s
// fabricated-boundary cases target. 2000 rows of ~150 bytes each reliably splits the response
// across dozens of real reads.
const STREAM_TYPE = "StreamRow";
const STREAM_ROW_COUNT = 2000;
const STREAM_PAYLOAD = "x".repeat(100);

// BIG_PAYLOAD_SIZE is a second, different way to force a genuinely multi-chunk response: not many
// ordinarily-sized rows, but ONE record whose own ndjson line is large enough that a single write
// of it cannot be delivered to the client in one read. This matters because a large text field or
// a base64 blob big enough to land here is an ordinary shape, not an exotic one - a caller could
// plausibly store either - even though most rows are nowhere near this size and never take this
// path. The point of this test is not that the split is common; it is that the decoder must still
// reassemble it correctly on the rows where it does happen, which is the case where cross-chunk
// buffering is load-bearing against a real server rather than only against the fabricated
// boundaries in stream.test.ts.
//
// The size was swept empirically against a live container (see task-4-report.md for the full
// table), not guessed. Payload sizes from 1,000 through 32,000 bytes never split across a real
// read, not once in repeated probing: ArcadeDB's response writer appears to issue one write() per
// output line, and TCP delivers a write that size as one segment on loopback as long as it stays
// under the client's own socket read buffer, so the record's line and the stats trailer always
// arrived as two whole chunks. Splitting starts to appear at 40,000 bytes, but unreliably - 3 of 5
// repeated runs split there against this client's transport (Node's `fetch`), 2 of 5 against the
// Python client's (`httpx`) - and the whole 40,000-65,000-byte band is non-deterministic run to
// run, consistent with the boundary being the client's own socket read-buffer size (chunk sizes
// cluster at 65536 bytes once a field is large enough to force several full buffers, matching what
// the 500,000-byte field used to first confirm the mechanism showed). Past that band, splitting
// becomes reliable: 70,000 and 80,000 bytes split on every one of 6 repeated runs against both this
// client's transport and the Python client's; 90,000 and 95,000 bytes were additionally confirmed
// 6-for-6 against this client's transport alone. 80,000 bytes sits in the middle of that reliable
// range: comfortably clear of the non-deterministic band with margin for a CI runner whose
// buffering differs slightly from this machine's, and nowhere near the 500,000 bytes it took to
// first confirm the mechanism existed.
const BIG_FIELD_TYPE = "BigFieldRow";
const BIG_PAYLOAD_SIZE = 80_000;
// A cycling digit pattern, not a repeated single character: a decoder that drops, duplicates, or
// reorders a byte at the chunk boundary changes this string's content, not just its length, so
// comparing the reassembled value against this exact string catches corruption a length-only or
// all-the-same-character check would miss.
const BIG_PAYLOAD = Array.from({ length: BIG_PAYLOAD_SIZE }, (_, i) => String(i % 10)).join("");

describe("queryStream / commandStream: ndjson events over a real container", () => {
  beforeAll(async () => {
    const db = rootServer.db(DB_NAME);
    await db.command({ language: "sql", command: `CREATE DOCUMENT TYPE ${STREAM_TYPE} IF NOT EXISTS` });
    await db.command({ language: "sql", command: `CREATE PROPERTY ${STREAM_TYPE}.n INTEGER` });
    await db.command({ language: "sql", command: `CREATE PROPERTY ${STREAM_TYPE}.payload STRING` });

    const values = Array.from({ length: STREAM_ROW_COUNT }, (_, i) => `(${i},'${STREAM_PAYLOAD}')`).join(",");
    await db.command({ language: "sql", command: `INSERT INTO ${STREAM_TYPE} (n, payload) VALUES ${values}` });

    await db.command({ language: "sql", command: `CREATE DOCUMENT TYPE ${BIG_FIELD_TYPE} IF NOT EXISTS` });
    await db.command({ language: "sql", command: `CREATE PROPERTY ${BIG_FIELD_TYPE}.payload STRING` });
    await db.command({ language: "sql", command: `INSERT INTO ${BIG_FIELD_TYPE} SET payload = '${BIG_PAYLOAD}'` });
  }, 30_000);

  it("streams every row as a record event, followed by a stats trailer whose returned matches what arrived", async () => {
    const db = rootServer.db(DB_NAME);
    const events: NdJsonQueryEvent[] = [];
    for await (const event of db.queryStream({ language: "sql", command: `SELECT FROM ${STREAM_TYPE}`, limit: -1 })) {
      events.push(event);
    }

    const records = events.filter((e) => e.record !== undefined);
    const last = events[events.length - 1];

    expect(records.length).toBe(STREAM_ROW_COUNT);
    // The trailer is the LAST event of a complete stream, not merely present somewhere in it.
    expect(last?.stats).toBeDefined();
    expect(last?.stats?.returned).toBe(records.length);
    expect(last?.stats?.truncated).toBe(false);
  });

  it("a limit low enough to truncate reports truncated: true in the trailer, matching the records actually seen", async () => {
    const db = rootServer.db(DB_NAME);
    const cap = 500;
    const events: NdJsonQueryEvent[] = [];
    for await (const event of db.queryStream({ language: "sql", command: `SELECT FROM ${STREAM_TYPE}`, limit: cap })) {
      events.push(event);
    }

    const records = events.filter((e) => e.record !== undefined);
    const last = events[events.length - 1];

    expect(records.length).toBe(cap);
    expect(last?.stats?.returned).toBe(cap);
    expect(last?.stats?.truncated).toBe(true);
  });

  it("the buffered query over the same data returns the same rows streaming did - streaming did not change the buffered path", async () => {
    const db = rootServer.db(DB_NAME);

    const envelope = await db.query<{ n: number; payload: string }>({
      language: "sql",
      command: `SELECT FROM ${STREAM_TYPE}`,
      limit: -1,
    });

    const events: NdJsonQueryEvent[] = [];
    for await (const event of db.queryStream({ language: "sql", command: `SELECT FROM ${STREAM_TYPE}`, limit: -1 })) {
      events.push(event);
    }
    // Compare the FULL row shape (both `n` and `payload`), not just `n` - `StreamRow` carries both
    // fields, and the property under test is that streaming did not change what the buffered path
    // returns, not merely that the two sides agree on one column.
    const streamedRows = events
      .filter((e) => e.record !== undefined)
      .map((e) => (e.record as unknown as { n: number; payload: string }))
      .sort((a, b) => a.n - b.n);
    const bufferedRows = [...envelope.result].sort((a, b) => a.n - b.n);

    expect(envelope.truncated).toBe(false);
    expect(streamedRows).toEqual(bufferedRows);
    expect(bufferedRows).toHaveLength(STREAM_ROW_COUNT);
  });

  it("commandStream also gets a real ndjson stream from the server, not a buffered response in disguise", async () => {
    // The property under test is server-side, not client-side: `stream.test.ts` already proves
    // this client sends the right Accept header and parses whatever it is handed, against a
    // MOCKED response - it cannot prove ArcadeDB actually honors that header on `/command` rather
    // than silently answering with a buffered `QueryResponse` regardless. If the server did that,
    // nothing else in this repository would catch it, since the unit tests never talk to a real
    // server. Asserting a `record` + `stats` shape here - not just "a promise resolved" - is what
    // rules that failure mode out: a buffered JSON body would not decode into these events at all.
    //
    // This does NOT use a mutating statement, unlike the read-only-vs-write asymmetry one might
    // expect a "command" test to cover. Verified empirically against a live container (see
    // task-4-report.md): ArcadeDB rejects `Accept: application/x-ndjson` on `/command` for any
    // non-read-only statement with 400 "The streaming encoding is available only for a read-only
    // statement, because its rows reach the client before the transaction commits: run this one
    // with 'Accept: application/json'" - a deliberate server-side rule (rows cannot stream to the
    // client ahead of a commit that might still roll back), not a gap in this client. A read-only
    // `SELECT` run through `/command` is the only statement shape `/command` can stream at all.
    const db = rootServer.db(DB_NAME);
    const events: NdJsonQueryEvent[] = [];
    for await (const event of db.commandStream({ language: "sql", command: `SELECT FROM ${STREAM_TYPE} WHERE n < 5` })) {
      events.push(event);
    }

    const records = events.filter((e) => e.record !== undefined);
    const last = events[events.length - 1];

    expect(records.length).toBe(5);
    expect(last?.stats).toBeDefined();
    expect(last?.stats?.returned).toBe(5);
  });

  it("reassembles a single record whose own ndjson line spans multiple real reads, intact", async () => {
    // This is a DIFFERENT property from the 2000-row test above: that one proves the response
    // arrives across many real reads; this one proves a single ndjson LINE really spans two of
    // them and still comes back whole. A test that only counted events here would pass against a
    // decoder that silently truncated `payload` at the chunk boundary - the value itself has to be
    // compared.
    const db = rootServer.db(DB_NAME);
    const events: NdJsonQueryEvent[] = [];
    for await (const event of db.queryStream({ language: "sql", command: `SELECT FROM ${BIG_FIELD_TYPE}` })) {
      events.push(event);
    }

    const records = events.filter((e) => e.record !== undefined);
    expect(records).toHaveLength(1);
    const payload = (records[0]?.record as unknown as { payload: string }).payload;
    expect(payload).toHaveLength(BIG_PAYLOAD_SIZE);
    expect(payload).toBe(BIG_PAYLOAD);

    const last = events[events.length - 1];
    expect(last?.stats?.returned).toBe(1);
    expect(last?.stats?.truncated).toBe(false);
  });
});

// The exact DDL below was worked out against a live container before this file was touched, not
// guessed - see task-4-report.md for the transcript. Two facts that cost the time: `embedding`
// must be declared `ARRAY_OF_FLOATS` (a property typed as the generic array the vector value
// arrives as), and `CREATE INDEX ... LSM_VECTOR` refuses to run without a `METADATA` clause naming
// `dimensions` - the server says so in its own `CommandSQLParsingException` message, which is
// where `METADATA {"dimensions": 4}` below comes from.
const VECTOR_TYPE = "VectorItem";
const VECTOR_INDEX = "VectorItem[embedding]";
const FULLTEXT_INDEX = "VectorItem[description]";

describe("db.vector: search, hybrid and full-text search against a real index", () => {
  beforeAll(async () => {
    const db = rootServer.db(DB_NAME);
    await db.command({ language: "sql", command: `CREATE DOCUMENT TYPE ${VECTOR_TYPE} IF NOT EXISTS` });
    await db.command({ language: "sql", command: `CREATE PROPERTY ${VECTOR_TYPE}.name STRING` });
    await db.command({ language: "sql", command: `CREATE PROPERTY ${VECTOR_TYPE}.embedding ARRAY_OF_FLOATS` });
    await db.command({ language: "sql", command: `CREATE PROPERTY ${VECTOR_TYPE}.description STRING` });
    await db.command({
      language: "sql",
      command: `CREATE INDEX ON ${VECTOR_TYPE} (embedding) LSM_VECTOR METADATA {"dimensions": 4}`,
    });
    // Three real, small embeddings - not zero rows. `red-apple`'s embedding is the exact query
    // vector every test below searches for, so it is always the nearest neighbor (distance 0) and
    // the only row a "known term" full-text query can be checked against unambiguously.
    await db.command({
      language: "sql",
      command: `INSERT INTO ${VECTOR_TYPE} SET name = 'red-apple', embedding = [1,0,0,0], description = 'a bright red apple'`,
    });
    await db.command({
      language: "sql",
      command: `INSERT INTO ${VECTOR_TYPE} SET name = 'green-apple', embedding = [0.9,0.1,0,0], description = 'a crisp green apple'`,
    });
    await db.command({
      language: "sql",
      command: `INSERT INTO ${VECTOR_TYPE} SET name = 'blue-car', embedding = [0,0,1,0], description = 'a fast blue car engine'`,
    });
    await db.command({ language: "sql", command: `CREATE INDEX ON ${VECTOR_TYPE} (description) FULL_TEXT` });
  }, 30_000);

  it("search returns a non-empty, nearest-first result, with count and truncated readable off the whole response", async () => {
    const result = await rootServer.db(DB_NAME).vector.search({ indexName: VECTOR_INDEX, queryVector: [1, 0, 0, 0], k: 10 });

    expect(result.results.length).toBeGreaterThan(0);
    expect(result.count).toBe(3);
    // k (10) exceeds the row count (3): the candidate window was never filled, so this is a
    // complete answer, not a partial one that happens to look complete.
    expect(result.truncated).toBe(false);
    // Nearest first: `red-apple`'s embedding IS the query vector, so its distance is exactly 0
    // and every later hit's distance is not smaller.
    expect(result.results[0]?.distance).toBe(0);
    const distances = result.results.map((r) => r.distance ?? Number.POSITIVE_INFINITY);
    expect(distances).toEqual([...distances].sort((a, b) => a - b));
  });

  it("a smaller k fills the candidate window, and truncated says so instead of silently returning a partial answer", async () => {
    const result = await rootServer.db(DB_NAME).vector.search({ indexName: VECTOR_INDEX, queryVector: [1, 0, 0, 0], k: 2 });

    expect(result.count).toBe(2);
    expect(result.truncated).toBe(true);
  });

  it("hybrid fuses the vector and full-text legs into one non-empty, nearest-first ranking", async () => {
    const result = await rootServer.db(DB_NAME).vector.hybrid({
      vectorIndexName: VECTOR_INDEX,
      queryVector: [1, 0, 0, 0],
      fulltextIndexName: FULLTEXT_INDEX,
      fulltextQuery: "apple",
      k: 10,
    });

    expect(result.results.length).toBeGreaterThan(0);
    expect(result.count).toBe(3);
    expect(result.truncated).toBe(false);
    expect(result.fused).toBe(true);
    // `red-apple` is the exact vector match AND matches the full-text query, so it wins both legs
    // and is fused first.
    expect(result.results[0]?.sources).toEqual(expect.arrayContaining(["vector", "fulltext"]));
  });

  it("fulltext matches a known term, and the response carries no truncated field at all (D-M5-2)", async () => {
    const result = await rootServer.db(DB_NAME).vector.fulltext({ queryText: "apple", indexName: FULLTEXT_INDEX });

    expect(result.results.length).toBeGreaterThan(0);
    expect(result.count).toBe(2);
    // Not `false` - ABSENT. FullTextSearchResponse has no `truncated` field in the contract at
    // all, unlike VectorSearchResponse and HybridSearchResponse above.
    expect("truncated" in result).toBe(false);
  });
});
