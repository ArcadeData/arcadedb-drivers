import { GenericContainer, Wait } from "testcontainers";
import type { StartedTestContainer } from "testcontainers";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { ArcadeDBError, NotSessionTokenError, basicAuth, createClient } from "../packages/driver/src/index.js";
import type { ArcadeDBServer } from "../packages/driver/src/index.js";

// Same image pin as data-plane.test.ts, for the same reason: the client under test and the
// server it runs against come from the same contract-defining release. See that file's comment
// for the full argument.
const DEFAULT_ARCADEDB_IMAGE = "arcadedata/arcadedb:26.10.2";
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

describe("sessions and API tokens", () => {
  // Issue #123's acceptance path: log in as a user, act as that user with the token alone, log
  // out, and see the token refused.
  it("logs in, queries as the user, logs out", async () => {
    const tenant = unique("tssesstenant");
    const other = unique("tssessother");
    const user = unique("tssessuser");
    await root.createDatabase(tenant);
    await root.createDatabase(other);
    try {
      await root.createUser(user, "session-password", { databases: { [tenant]: ["admin"] } });
      try {
        // 403, not 401: the server answers every failed Basic check so (ArcadeData/arcadedb#10109).
        expect((await rejected(root.loginAs(user, "wrong-password"))).status).toBe(403);

        const login = await root.loginAs(user, "session-password");
        expect(login.user).toBe(user);
        expect(login.token.startsWith("AU-")).toBe(true);

        const asUser = root.withToken(login.token);
        const visible = await asUser.listDatabases();
        expect(visible).toContain(tenant);
        expect(visible).not.toContain(other);
        const env = await asUser.db(tenant).query({ language: "sql", command: "SELECT 1 AS one" });
        expect(env.result).toEqual([{ one: 1 }]);

        expect((await root.listSessions()).some((s) => s.token === login.token && s.user === user)).toBe(true);
        expect((await rejected(asUser.listSessions())).status).toBe(403);

        await expect(root.logout()).rejects.toBeInstanceOf(NotSessionTokenError);
        await asUser.logout();
        expect((await rejected(asUser.listDatabases())).status).toBe(401);
        expect((await rejected(asUser.logout())).status).toBe(401);
      } finally {
        await root.dropUser(user);
      }
    } finally {
      await root.dropDatabase(tenant);
      await root.dropDatabase(other);
    }
  });

  it("creates, uses, lists and deletes an API token", async () => {
    const db = unique("tstokendb");
    const name = unique("tstoken");
    await root.createDatabase(db);
    const created = await root.createAPIToken(name, { database: db });
    try {
      expect(created.token.startsWith("at-")).toBe(true);
      expect(created.token.endsWith(created.tokenSuffix)).toBe(true);
      expect([created.name, created.database, created.expiresAt, created.expired]).toEqual([name, db, null, false]);

      const listed = (await root.listAPITokens()).find((t) => t.name === name);
      expect(listed?.tokenHash).toBe(created.tokenHash);
      expect(listed?.tokenSuffix).toBe(created.tokenSuffix);

      // A taken name is a 409; the doc comment and the README rely on it.
      expect((await rejected(root.createAPIToken(name))).status).toBe(409);

      const withToken = root.withToken(created.token);
      await withToken.listDatabases();
      await expect(withToken.logout()).rejects.toBeInstanceOf(NotSessionTokenError);

      await expect(root.deleteAPIToken(created.token)).rejects.toThrow(RangeError);
      await root.deleteAPIToken(created.tokenHash);
      // 404 is not in the contract's list for deleteApiToken (ArcadeData/arcadedb#10110); measured here.
      expect((await rejected(root.deleteAPIToken(created.tokenHash))).status).toBe(404);
      expect((await rejected(withToken.listDatabases())).status).toBe(401);
    } finally {
      await root.deleteAPIToken(created.tokenHash).catch(() => undefined);
      await root.dropDatabase(db);
    }
  });
});
