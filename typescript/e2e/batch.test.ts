import { GenericContainer, Wait } from "testcontainers";
import type { StartedTestContainer } from "testcontainers";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { basicAuth, createClient } from "../packages/driver/src/index.js";
import type { ArcadeDBServer } from "../packages/driver/src/index.js";
import type { NdJsonBatchEvent } from "../packages/driver/src/facade/batch.js";
import { unwrap } from "../packages/driver/src/internal/unwrap.js";

// Same image pin as data-plane.test.ts, for the same reason: the client under test and the
// server it runs against come from the same contract-defining release. See that file's comment
// for the full argument.
const DEFAULT_ARCADEDB_IMAGE = "arcadedata/arcadedb:26.10.1-SNAPSHOT";
const ARCADEDB_IMAGE = process.env.ARCADEDB_DOCKER_IMAGE ?? DEFAULT_ARCADEDB_IMAGE;

const ROOT_PASSWORD = "playwithdata";
const DB_NAME = "batchtest";

let container: StartedTestContainer;
let rootServer: ArcadeDBServer;

beforeAll(async () => {
  container = await new GenericContainer(ARCADEDB_IMAGE)
    .withEnvironment({ JAVA_OPTS: `-Darcadedb.server.rootPassword=${ROOT_PASSWORD}` })
    // Exposed-but-not-bound, same reason as data-plane.test.ts: avoid clashing with a local
    // ArcadeDB already bound to host port 2480.
    .withExposedPorts(2480)
    .withWaitStrategy(Wait.forHttp("/api/v1/ready", 2480).forStatusCodeMatching((statusCode) => statusCode === 204))
    .withStartupTimeout(60_000)
    .start();

  const baseUrl = `http://${container.getHost()}:${container.getMappedPort(2480)}`;
  rootServer = createClient({ baseUrl, auth: basicAuth("root", ROOT_PASSWORD) });

  await unwrap(
    rootServer.raw.POST("/api/v1/server", {
      body: { command: `create database ${DB_NAME}`, language: "sql" },
    }),
  );

  // The batch endpoint has no DDL of its own - the vertex/edge types and the property it will
  // resolve names against have to exist before any batch load reaches the server.
  const db = rootServer.db(DB_NAME);
  await db.command({ language: "sql", command: "CREATE VERTEX TYPE Person IF NOT EXISTS" });
  await db.command({ language: "sql", command: "CREATE PROPERTY Person.name IF NOT EXISTS STRING" });
  await db.command({ language: "sql", command: "CREATE EDGE TYPE Knows IF NOT EXISTS" });
}, 90_000);

afterAll(async () => {
  await container?.stop();
});

describe("batchLoad / batchLoadStream against a real ArcadeDB server", () => {
  it("loads vertices and edges and resolves temp ids to RIDs", async () => {
    const db = rootServer.db(DB_NAME);

    const summary = await db.batchLoad({
      vertices: [
        { type: "Person", id: "a", properties: { name: "Ann" } },
        { type: "Person", id: "b", properties: { name: "Ben" } },
      ],
      edges: [{ type: "Knows", from: "a", to: "b", properties: { since: 2020 } }],
    });

    expect(summary.verticesCreated).toBe(2);
    expect(summary.edgesCreated).toBe(1);
    expect(Object.keys(summary.idMapping ?? {})).toEqual(expect.arrayContaining(["a", "b"]));
  });

  it("stores properties as real fields, not nested under 'properties'", async () => {
    // The regression guard for the corruption of the spec's section 3. If a refactor ever nests
    // properties again, the load still returns 200 and correct counters - only this query
    // notices.
    const db = rootServer.db(DB_NAME);

    await db.batchLoad({ vertices: [{ type: "Person", id: "c", properties: { name: "Cat" } }] });

    const rows = await db.query<{ name: string }>({
      language: "sql",
      command: "SELECT FROM Person WHERE name = 'Cat'",
    });
    expect(rows.result).toHaveLength(1);
  });

  it("streams progress before exactly one summary", async () => {
    const db = rootServer.db(DB_NAME);
    const events: NdJsonBatchEvent[] = [];

    for await (const event of db.batchLoadStream({
      vertices: [
        { type: "Person", id: "d", properties: { name: "Dan" } },
        { type: "Person", id: "e", properties: { name: "Eve" } },
      ],
      edges: [{ type: "Knows", from: "d", to: "e" }],
      options: { commitEvery: 1 },
    })) {
      events.push(event);
    }

    const progressEvents = events.filter((e) => e.progress !== undefined);
    const summaryEvents = events.filter((e) => e.summary !== undefined);

    expect(progressEvents.length).toBeGreaterThan(0);
    expect(summaryEvents).toHaveLength(1);
    // The summary must be the LAST event, i.e. every progress event precedes it.
    expect(events[events.length - 1]?.summary).toBeDefined();

    // The streamed shape from the Amendment: idMappingStreamed: true with idMappingSize, NOT the
    // buffered idMapping map.
    expect(summaryEvents[0]?.summary?.idMappingStreamed).toBe(true);
    expect(typeof summaryEvents[0]?.summary?.idMappingSize).toBe("number");
    expect(summaryEvents[0]?.summary).not.toHaveProperty("idMapping");
  });
});
