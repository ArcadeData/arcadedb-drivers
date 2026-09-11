import { GenericContainer, Wait } from "testcontainers";
import type { StartedTestContainer } from "testcontainers";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { basicAuth, bearerAuth, createClient } from "../packages/driver/src/index.js";
import type { ArcadeDBServer } from "../packages/driver/src/index.js";
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
