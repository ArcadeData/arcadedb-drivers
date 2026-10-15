import { GenericContainer, Wait } from "testcontainers";
import type { StartedTestContainer } from "testcontainers";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { ArcadeDBError, basicAuth, createClient } from "../packages/driver/src/index.js";
import type { ArcadeDBServer } from "../packages/driver/src/index.js";

// Same image pin as data-plane.test.ts, for the same reason: the client under test and the
// server it runs against come from the same contract-defining release. See that file's comment
// for the full argument.
const DEFAULT_ARCADEDB_IMAGE = "arcadedata/arcadedb:26.11.1-SNAPSHOT";
const ARCADEDB_IMAGE = process.env.ARCADEDB_DOCKER_IMAGE ?? DEFAULT_ARCADEDB_IMAGE;

const ROOT_PASSWORD = "playwithdata";

let container: StartedTestContainer;
let baseUrl: string;
let root: ArcadeDBServer;
let counter = 0;

const unique = (prefix: string): string => `${prefix}${++counter}${Math.random().toString(36).slice(2, 8)}`;

async function rejected(p: Promise<unknown>): Promise<ArcadeDBError> {
  try {
    await p;
  } catch (err) {
    expect(err).toBeInstanceOf(ArcadeDBError);
    return err as ArcadeDBError;
  }
  throw new Error("expected the call to throw");
}

beforeAll(async () => {
  container = await new GenericContainer(ARCADEDB_IMAGE)
    .withEnvironment({ JAVA_OPTS: `-Darcadedb.server.rootPassword=${ROOT_PASSWORD}` })
    // Exposed-but-not-bound, same reason as data-plane.test.ts: avoid clashing with a local
    // ArcadeDB already bound to host port 2480.
    .withExposedPorts(2480)
    .withWaitStrategy(Wait.forHttp("/api/v1/ready", 2480).forStatusCodeMatching((statusCode) => statusCode === 204))
    .withStartupTimeout(60_000)
    .start();
  baseUrl = `http://${container.getHost()}:${container.getMappedPort(2480)}`;
  root = createClient({ baseUrl, auth: basicAuth("root", ROOT_PASSWORD) });
}, 90_000);

afterAll(async () => {
  await container?.stop();
});

describe("server administration", () => {
  it("creates and drops a database; an existing name is a 400, not a 409", async () => {
    const name = unique("tsadmin");
    await root.createDatabase(name);
    expect(await root.exists(name)).toBe(true);

    const dup = await rejected(root.createDatabase(name));
    expect(dup.status).toBe(400);
    expect(dup.detail).toContain("already exists");

    await root.dropDatabase(name);
    expect(await root.exists(name)).toBe(false);
    expect((await rejected(root.dropDatabase(name))).status).toBe(400);
  });

  it("serverCommand returns the whole body", async () => {
    const name = unique("tslist");
    await root.createDatabase(name);
    try {
      const body = await root.serverCommand("list databases");
      expect(body["result"]).toContain(name);
    } finally {
      await root.dropDatabase(name);
    }
  });

  // The use case behind issue #122: a database per tenant, and a user who sees only theirs.
  it("isolates a user to its tenant database", async () => {
    const tenant = unique("tstenant");
    const other = unique("tsother");
    const user = unique("tsuser");
    await root.createDatabase(tenant);
    await root.createDatabase(other);
    try {
      await root.createUser(user, "first-password", { databases: { [tenant]: ["admin"] } });
      try {
        const listed = (await root.listUsers()).find((u) => u.name === user);
        expect(listed?.databases).toEqual({ [tenant]: ["admin"] });

        // 409 since ArcadeData/arcadedb#10076; earlier servers answered 403 "Security error".
        const dup = await rejected(root.createUser(user, "first-password"));
        expect(dup.status).toBe(409);
        expect(dup.message).toContain("already exists");

        const asUser = createClient({ baseUrl, auth: basicAuth(user, "first-password") });
        const visible = await asUser.listDatabases();
        expect(visible).toContain(tenant);
        expect(visible).not.toContain(other);

        await root.updateUser(user, { password: "second-password" });
        await createClient({ baseUrl, auth: basicAuth(user, "second-password") }).listDatabases();
      } finally {
        await root.dropUser(user);
      }
      expect((await rejected(root.dropUser(user))).status).toBe(404);
      expect((await rejected(root.updateUser(user, { password: "third-password" }))).status).toBe(404);
    } finally {
      await root.dropDatabase(tenant);
      await root.dropDatabase(other);
    }
  });

  it("saves, lists and deletes a group", async () => {
    const db = unique("tsgroups");
    await root.createDatabase(db);
    try {
      await root.saveGroup(db, "reader", { resultSetLimit: 10 });
      expect((await root.listGroups())[db]?.["reader"]?.resultSetLimit).toBe(10);
      await root.deleteGroup(db, "reader");
      expect((await root.listGroups())[db]?.["reader"]).toBeUndefined();
    } finally {
      await root.dropDatabase(db);
    }
  });

  it("runs a sqlscript", async () => {
    const name = unique("tsscript");
    await root.createDatabase(name);
    try {
      const db = root.db(name);
      await db.command({
        language: "sqlscript",
        command: "CREATE DOCUMENT TYPE TsScript; INSERT INTO TsScript SET x = 1; INSERT INTO TsScript SET x = 2;",
      });
      const env = await db.query({ language: "sql", command: "SELECT count(*) AS n FROM TsScript" });
      expect(env.result).toEqual([{ n: 2 }]);
    } finally {
      await root.dropDatabase(name);
    }
  });
});
