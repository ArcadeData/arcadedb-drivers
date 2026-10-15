import { describe, expect, it, vi } from "vitest";
import { ArcadeDBError, createClient } from "../src/index.js";

const BASE = "http://db.test";

interface Sent {
  method: string;
  url: URL;
  body: unknown;
}

/** A client whose fetch answers every request with `status`/`body` and records what it was sent. */
function recording(status: number, body: unknown) {
  const sent: Sent[] = [];
  const fetchMock = vi.fn(async (input: Request) => {
    const text = await input.text();
    sent.push({ method: input.method, url: new URL(input.url), body: text ? JSON.parse(text) : undefined });
    return new Response(body === undefined ? null : JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    });
  });
  const server = createClient({ baseUrl: BASE, fetch: fetchMock as unknown as typeof fetch });
  return { server, sent, last: () => sent[sent.length - 1]! };
}

async function caught(p: Promise<unknown>): Promise<ArcadeDBError> {
  try {
    await p;
  } catch (err) {
    expect(err).toBeInstanceOf(ArcadeDBError);
    return err as ArcadeDBError;
  }
  throw new Error("expected the call to throw");
}

describe("sqlscript", () => {
  it("reaches the wire as the command language", async () => {
    const { server, last } = recording(200, { result: [], limit: -1, returned: 0, truncated: false });
    await server.db("db").command({ language: "sqlscript", command: "LET a = 1; RETURN $a" });
    expect((last().body as { language: string }).language).toBe("sqlscript");
  });
});

describe("databases and server commands", () => {
  it.each([
    ["createDatabase", "create database tenant_a"],
    ["dropDatabase", "drop database tenant_a"],
  ] as const)("%s sends a server command", async (method, command) => {
    // The server's real answer: a string result where the contract declares an array.
    const { server, last } = recording(200, { result: "ok" });
    await expect(server[method]("tenant_a")).resolves.toBeUndefined();
    expect(last().method).toBe("POST");
    expect(last().url.pathname).toBe("/api/v1/server");
    expect(last().body).toEqual({ command, language: "sql" });
  });

  it.each(["createDatabase", "dropDatabase"] as const)("%s throws ArcadeDBError", async (method) => {
    const { server } = recording(400, { error: "Cannot execute command", detail: "Database 'db' already exists" });
    const err = await caught(server[method]("db"));
    expect(err.status).toBe(400);
    expect(err.detail).toBe("Database 'db' already exists");
  });

  it.each(["", " ", " db", "db ", "\tdb", "db\n"])(
    "refuses database name %j before any request",
    async (name) => {
      const { server, sent } = recording(200, { result: "ok" });
      await expect(server.createDatabase(name)).rejects.toThrow(RangeError);
      await expect(server.dropDatabase(name)).rejects.toThrow(RangeError);
      expect(sent).toHaveLength(0);
    },
  );

  it("sends a database name with an embedded space as given", async () => {
    const { server, last } = recording(200, { result: "ok" });
    await server.createDatabase("a b");
    expect((last().body as { command: string }).command).toBe("create database a b");
  });

  it("serverCommand returns the whole parsed body", async () => {
    const { server, last } = recording(200, { result: ["a", "b"] });
    await expect(server.serverCommand("list databases")).resolves.toEqual({ result: ["a", "b"] });
    expect(last().body).toEqual({ command: "list databases", language: "sql" });
  });

  it.each([
    [400, "Server command not valid"],
    [403, "Security error"],
    [503, "x"],
  ])("serverCommand throws ArcadeDBError on %i", async (status, message) => {
    const { server } = recording(status, { error: message });
    const err = await caught(server.serverCommand("whatever"));
    expect([err.status, err.error]).toEqual([status, message]);
  });
});

describe("users", () => {
  it("createUser sends name, password and databases", async () => {
    const { server, last } = recording(201, { result: "User 'alice' created" });
    await server.createUser("alice", "secret-pw", { databases: { tenant_a: ["admin"] } });
    expect(last().method).toBe("POST");
    expect(last().url.pathname).toBe("/api/v1/server/users");
    expect(last().body).toEqual({ name: "alice", password: "secret-pw", databases: { tenant_a: ["admin"] } });
  });

  it("createUser without databases sends none", async () => {
    const { server, last } = recording(201, { result: "ok" });
    await server.createUser("bob", "secret-pw");
    expect(last().body).toEqual({ name: "bob", password: "secret-pw" });
  });

  it.each([
    [400, "User password must be at least 8 characters"],
    [403, "Security error"],
    [409, "User already exists"],
  ])("createUser throws ArcadeDBError on %i", async (status, message) => {
    const { server } = recording(status, { error: message });
    const err = await caught(server.createUser("alice", "pw"));
    expect(err.status).toBe(status);
  });

  it("updateUser sends only what changes, naming the user in the query", async () => {
    const { server, last } = recording(200, { result: "ok" });
    await server.updateUser("alice", { password: "new-secret" });
    expect(last().method).toBe("PUT");
    expect(last().url.searchParams.get("name")).toBe("alice");
    expect(last().body).toEqual({ password: "new-secret" });
  });

  it("updateUser with empty databases clears them, and with nothing sends an empty body", async () => {
    const { server, sent } = recording(200, { result: "ok" });
    await server.updateUser("alice", { databases: {} });
    await server.updateUser("alice");
    expect(sent.map((s) => s.body)).toEqual([{ databases: {} }, {}]);
  });

  it("dropUser names the user in the query", async () => {
    const { server, last } = recording(200, { result: "ok" });
    await server.dropUser("a b");
    expect(last().method).toBe("DELETE");
    expect(last().url.searchParams.get("name")).toBe("a b");
  });

  it("updateUser and dropUser on a missing user throw 404", async () => {
    const { server } = recording(404, { error: "User 'ghost' not found" });
    expect((await caught(server.updateUser("ghost", { password: "x".repeat(8) }))).status).toBe(404);
    expect((await caught(server.dropUser("ghost"))).status).toBe(404);
  });

  it("listUsers returns the users", async () => {
    const users = [
      { name: "root", databases: { "*": ["admin"] } },
      { name: "alice", databases: {} },
    ];
    const { server, last } = recording(200, { result: users });
    await expect(server.listUsers()).resolves.toEqual(users);
    expect(last().method).toBe("GET");
  });

  it("listUsers throws ArcadeDBError", async () => {
    const { server } = recording(403, { error: "Security error" });
    expect((await caught(server.listUsers())).status).toBe(403);
  });
});

describe("groups", () => {
  const groupList = {
    result: {
      version: 1,
      databases: {
        "*": { groups: { admin: { access: ["updateSecurity"], readTimeout: -1, resultSetLimit: -1, types: {} } } },
      },
    },
  };

  it("listGroups keys by database, then group", async () => {
    const { server } = recording(200, groupList);
    const groups = await server.listGroups();
    expect(groups["*"]!["admin"]!.access).toEqual(["updateSecurity"]);
    expect(groups["*"]!["admin"]!.readTimeout).toBe(-1);
  });

  it("saveGroup sends only what is given", async () => {
    const { server, sent } = recording(200, { result: "ok" });
    await server.saveGroup("tenant_a", "reader", { resultSetLimit: 100 });
    await server.saveGroup("tenant_a", "writer");
    expect(sent.map((s) => s.body)).toEqual([
      { database: "tenant_a", name: "reader", resultSetLimit: 100 },
      { database: "tenant_a", name: "writer" },
    ]);
    expect(sent[0]!.url.pathname).toBe("/api/v1/server/groups");
  });

  it("deleteGroup names database and group in the query", async () => {
    const { server, last } = recording(200, { result: "ok" });
    await server.deleteGroup("tenant_a", "reader");
    expect(last().method).toBe("DELETE");
    expect([last().url.searchParams.get("database"), last().url.searchParams.get("name")]).toEqual([
      "tenant_a",
      "reader",
    ]);
  });

  it("every group call throws ArcadeDBError", async () => {
    const { server } = recording(404, { error: "Group 'x' not found" });
    for (const call of [() => server.listGroups(), () => server.saveGroup("db", "x"), () => server.deleteGroup("db", "x")]) {
      expect((await caught(call())).status).toBe(404);
    }
  });
});
