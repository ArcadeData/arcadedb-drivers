import { GenericContainer, Wait } from "testcontainers";
import type { StartedTestContainer } from "testcontainers";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { ArcadeDBError, basicAuth, createClient, isQueryTerminated } from "../packages/driver/src/index.js";
import type { ArcadeDBServer, ListQueriesOptions, RunningQuery } from "../packages/driver/src/index.js";

// List and terminate running work, and `progress`, against a real server (issue #124). Each status
// and the 409 pinned here were measured, not read off the contract: the contract does not describe
// these answers at all.

// Same image pin as data-plane.test.ts, for the same reason: see that file's comment.
const DEFAULT_ARCADEDB_IMAGE = "arcadedata/arcadedb:26.11.1-SNAPSHOT";
const ARCADEDB_IMAGE = process.env.ARCADEDB_DOCKER_IMAGE ?? DEFAULT_ARCADEDB_IMAGE;

const ROOT_PASSWORD = "playwithdata";

// Runs until it is terminated. SQL SLEEP would not do: it notices a terminate only when it ends, so
// it is answered "terminating" rather than "terminated".
const LONG_LOOP = "LET i = 0; WHILE ($i < 1000000000) { LET i = $i + 1; } RETURN $i";

let container: StartedTestContainer;
let root: ArcadeDBServer;
let counter = 0;

const unique = (prefix: string): string => `${prefix}${++counter}${Math.random().toString(36).slice(2, 8)}`;

beforeAll(async () => {
  container = await new GenericContainer(ARCADEDB_IMAGE)
    .withEnvironment({ JAVA_OPTS: `-Darcadedb.server.rootPassword=${ROOT_PASSWORD}` })
    .withExposedPorts(2480)
    .withWaitStrategy(Wait.forHttp("/api/v1/ready", 2480).forStatusCodeMatching((statusCode) => statusCode === 204))
    .withStartupTimeout(60_000)
    .start();
  const baseUrl = `http://${container.getHost()}:${container.getMappedPort(2480)}`;
  root = createClient({ baseUrl, auth: basicAuth("root", ROOT_PASSWORD) });
}, 90_000);

afterAll(async () => {
  await container?.stop();
});

async function withDatabase(fn: (name: string) => Promise<void>): Promise<void> {
  const name = unique("tsrunning");
  await root.createDatabase(name);
  try {
    await fn(name);
  } finally {
    await root.dropDatabase(name);
  }
}

async function waitForQuery(opts: ListQueriesOptions): Promise<RunningQuery> {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    const found = await root.listQueries(opts);
    if (found.length > 0) return found[0]!;
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error(`no running query matched ${JSON.stringify(opts)}`);
}

describe("running work", () => {
  it("lists a tagged query and terminates it by tag; the request gets the 409", async () => {
    await withDatabase(async (name) => {
      const tag = unique("ts running "); // a space, to cross the rest-of-line parse
      const pending = root
        .db(name)
        .command({ language: "sqlscript", command: LONG_LOOP, queryTag: tag })
        .then(
          () => undefined,
          (e: unknown) => e,
        );

      const query = await waitForQuery({ database: name, tag });
      expect(query).toMatchObject({ tag, database: name, language: "sqlscript", text: LONG_LOOP });
      expect(query.sessionId).toBeUndefined();

      const results = await root.terminateQueriesByTag(tag, { waitMs: 5000 });
      expect(results).toEqual([{ id: query.id, status: "terminated" }]);

      const err = await pending;
      expect(isQueryTerminated(err)).toBe(true);
      expect(err).toBeInstanceOf(ArcadeDBError);
      expect((err as ArcadeDBError).status).toBe(409);
      expect((err as ArcadeDBError).error).toBe("Query terminated");

      expect(await root.listQueries({ tag })).toEqual([]);
      expect((await root.terminateQuery(query.id)).status).toBe("not found");
    });
  });

  it("terminating a script inside a transaction ends the transaction", async () => {
    await withDatabase(async (name) => {
      const tag = unique("ts-tx-");
      const outcome = await root
        .db(name)
        .transaction(async (tx) => {
          const pending = tx.command({ language: "sqlscript", command: LONG_LOOP, queryTag: tag });
          pending.catch(() => undefined); // awaited below; keep it from reading as unhandled meanwhile
          const query = await waitForQuery({ tag });
          expect(query.sessionId).toBeDefined();

          const open = (await root.listTransactions()).find((t) => t.id === query.sessionId);
          expect(open).toMatchObject({ busy: true, database: name });
          expect(open?.runningQueries).toContain(query.id);

          const result = await root.terminateQuery(query.id, { waitMs: 5000 });
          // A script is a command, so terminating it ends the session it ran in.
          expect(result).toEqual({
            id: query.id,
            status: "terminated",
            sessionId: query.sessionId,
            sessionOpen: false,
          });
          await pending;
        })
        .then(
          () => undefined,
          (e: unknown) => e,
        );
      expect(isQueryTerminated(outcome)).toBe(true);
    });
  });

  // The server answers a commit naming a session it no longer has with 204, like a real commit, so
  // the callback resolves although its insert was rolled back. The README and terminateTransaction's
  // doc comment warn about it; if this starts failing, update both.
  it("terminateTransaction rolls back, and the owner's commit does not notice", async () => {
    await withDatabase(async (name) => {
      const db = root.db(name);
      await db.command({ language: "sql", command: "CREATE DOCUMENT TYPE Doc" });
      let session = "";
      await db.transaction(async (tx) => {
        await tx.command({ language: "sql", command: "INSERT INTO Doc SET x = 1" });
        const open = (await root.listTransactions()).filter((t) => t.database === name);
        expect(open).toHaveLength(1);
        session = open[0]!.id;
        expect(await root.terminateTransaction(session)).toEqual({ id: session, status: "terminated" });
        const after = await tx.query({ language: "sql", command: "SELECT 1" }).catch((e: unknown) => e);
        expect((after as ArcadeDBError).status).toBe(404);
      });
      const count = await db.query<{ n: number }>({ language: "sql", command: "SELECT count(*) AS n FROM Doc" });
      expect(count.result).toEqual([{ n: 0 }]);
      expect((await root.terminateTransaction(session)).status).toBe("not found");
    });
  });

  it("progress is empty with nothing running", async () => {
    await withDatabase(async (name) => {
      expect(await root.db(name).progress()).toEqual({ result: [] });
    });
  });
});
