import { describe, expect, it, vi } from "vitest";
import {
  ArcadeDBError,
  ArcadeDBServer,
  NotSessionTokenError,
  basicAuth,
  bearerAuth,
  createClient,
} from "../src/index.js";
import type { Middleware } from "../src/index.js";

const BASE = "http://db.test";
const SESSION_TOKEN = "AU-node-6f1c2d3e";
const API_TOKEN = "at-0123456789abcdef";
const HASH = "a".repeat(64);
const DB_LIST = { user: "root", version: "26.11.1", serverName: "s", result: [] as string[] };
const TOKEN_FIELDS = {
  name: "ci",
  database: "tenant_a",
  createdAt: 1_760_000_000_123,
  expiresAt: 0,
  permissions: { types: { "*": { access: ["readRecord"] } } },
  tokenHash: HASH,
  tokenSuffix: "cdef",
};

interface Sent {
  method: string;
  url: URL;
  authorization: string | null;
  body: unknown;
}

type Answer = { status: number; body?: unknown };

/** A fetch that answers by "METHOD path" and records every request. */
function recording(answers: Record<string, Answer>) {
  const sent: Sent[] = [];
  const fetchMock = vi.fn(async (input: Request) => {
    const url = new URL(input.url);
    const text = await input.text();
    sent.push({
      method: input.method,
      url,
      authorization: input.headers.get("Authorization"),
      body: text ? JSON.parse(text) : undefined,
    });
    const answer = answers[`${input.method} ${url.pathname}`];
    if (!answer) throw new Error(`unexpected ${input.method} ${url.pathname}`);
    return new Response(answer.body === undefined ? null : JSON.stringify(answer.body), {
      status: answer.status,
      headers: { "content-type": "application/json" },
    });
  });
  const fetch = fetchMock as unknown as typeof globalThis.fetch;
  const client = (auth?: Middleware) => createClient({ baseUrl: BASE, fetch, ...(auth ? { auth } : {}) });
  return { client, sent, last: () => sent[sent.length - 1]! };
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

const ROOT_BASIC = `Basic ${btoa("root:pw-12345")}`;

describe("login and loginAs", () => {
  it("login uses the client's own credentials", async () => {
    const { client, last } = recording({
      "POST /api/v1/login": { status: 200, body: { token: SESSION_TOKEN, user: "root" } },
    });
    expect(await client(basicAuth("root", "pw-12345")).login()).toEqual({ token: SESSION_TOKEN, user: "root" });
    expect(last().authorization).toBe(ROOT_BASIC);
  });

  it("loginAs sends the given credentials and leaves the client alone", async () => {
    const { client, sent } = recording({
      "POST /api/v1/login": { status: 200, body: { token: SESSION_TOKEN, user: "alice" } },
      "GET /api/v1/databases": { status: 200, body: DB_LIST },
    });
    const srv = client(basicAuth("root", "pw-12345"));
    expect((await srv.loginAs("alice", "alice-pw")).user).toBe("alice");
    await srv.listDatabases();
    expect(sent.map((s) => s.authorization)).toEqual([`Basic ${btoa("alice:alice-pw")}`, ROOT_BASIC]);
  });

  it.each([401, 403, 503])("a refused login throws ArcadeDBError %i", async (status) => {
    const { client } = recording({ "POST /api/v1/login": { status, body: { error: "Security error" } } });
    const srv = client();
    expect((await caught(srv.login())).status).toBe(status);
    expect((await caught(srv.loginAs("alice", "wrong"))).status).toBe(status);
  });

  it("loginAs and withToken need a server built by createClient", async () => {
    const srv = new ArcadeDBServer(createClient({ baseUrl: BASE }).raw);
    await expect(srv.loginAs("alice", "pw")).rejects.toThrow(/createClient/);
    expect(() => srv.withToken(SESSION_TOKEN)).toThrow(/createClient/);
  });
});

describe("withToken", () => {
  it("returns a new server and leaves the original alone", async () => {
    const { client, sent } = recording({ "GET /api/v1/databases": { status: 200, body: DB_LIST } });
    const srv = client(basicAuth("root", "pw-12345"));
    await srv.withToken(SESSION_TOKEN).listDatabases();
    await srv.listDatabases();
    expect(sent.map((s) => s.authorization)).toEqual([`Bearer ${SESSION_TOKEN}`, ROOT_BASIC]);
  });
});

describe("logout", () => {
  it("ends a session token", async () => {
    const { client, last } = recording({ "POST /api/v1/logout": { status: 204 } });
    await client(bearerAuth(SESSION_TOKEN)).logout();
    expect(last().authorization).toBe(`Bearer ${SESSION_TOKEN}`);
  });

  it("ends the token a withToken server presents", async () => {
    const { client, last } = recording({ "POST /api/v1/logout": { status: 204 } });
    await client(basicAuth("root", "pw-12345")).withToken(SESSION_TOKEN).logout();
    expect(last().authorization).toBe(`Bearer ${SESSION_TOKEN}`);
  });

  it.each([
    ["no auth", undefined],
    ["Basic credentials", basicAuth("root", "pw-12345")],
    ["an API token", bearerAuth(API_TOKEN)],
  ])("refuses %s unsent", async (_, auth) => {
    const { client, sent } = recording({ "POST /api/v1/logout": { status: 204 } });
    await expect(client(auth).logout()).rejects.toBeInstanceOf(NotSessionTokenError);
    expect(sent).toHaveLength(0);
  });

  it("a dead token throws 401", async () => {
    const { client } = recording({ "POST /api/v1/logout": { status: 401, body: { error: "Invalid token" } } });
    expect((await caught(client(bearerAuth(SESSION_TOKEN)).logout())).status).toBe(401);
  });
});

describe("listSessions", () => {
  it("maps each session", async () => {
    const { client } = recording({
      "GET /api/v1/sessions": {
        status: 200,
        body: {
          count: 2,
          result: [
            {
              token: SESSION_TOKEN,
              user: "alice",
              createdAt: 1_760_000_000_000,
              lastUpdate: 1_760_000_060_500,
              elapsedMs: 1500,
              sourceIp: "10.0.0.1",
              userAgent: "curl/8",
              country: null,
              city: null,
            },
            {
              token: "AU-other",
              user: "bob",
              issuer: "node-2",
              createdAt: 0,
              lastUpdate: 0,
              elapsedMs: 0,
              sourceIp: null,
              userAgent: null,
              country: "IT",
              city: "Rome",
            },
          ],
        },
      },
    });
    const [alice, bob] = await client().listSessions();
    expect(alice).toEqual({
      token: SESSION_TOKEN,
      user: "alice",
      issuer: undefined,
      createdAt: new Date("2025-10-09T08:53:20.000Z"),
      lastUpdate: new Date("2025-10-09T08:54:20.500Z"),
      elapsedMs: 1500,
      sourceIp: "10.0.0.1",
      userAgent: "curl/8",
      country: null,
      city: null,
    });
    expect([bob!.issuer, bob!.sourceIp, bob!.country, bob!.city]).toEqual(["node-2", null, "IT", "Rome"]);
  });

  it("a non-root user gets 403", async () => {
    const { client } = recording({ "GET /api/v1/sessions": { status: 403, body: { error: "Security error" } } });
    expect((await caught(client().listSessions())).status).toBe(403);
  });
});

describe("API tokens", () => {
  it("createAPIToken sends only what was given", async () => {
    const { client, last } = recording({
      "POST /api/v1/server/api-tokens": { status: 201, body: { result: { ...TOKEN_FIELDS, token: API_TOKEN } } },
    });
    const srv = client();
    await srv.createAPIToken("ci");
    expect(last().body).toEqual({ name: "ci" });
    const created = await srv.createAPIToken("ci", {
      database: "tenant_a",
      expiresAt: new Date("2030-01-01T00:00:00Z"),
      permissions: { types: { "*": { access: ["readRecord"] } } },
    });
    expect(last().body).toEqual({
      name: "ci",
      database: "tenant_a",
      expiresAt: 1_893_456_000_000,
      permissions: { types: { "*": { access: ["readRecord"] } } },
    });
    expect(created).toEqual({
      name: "ci",
      database: "tenant_a",
      createdAt: new Date(1_760_000_000_123),
      expiresAt: null,
      expired: false,
      permissions: { types: { "*": { access: ["readRecord"] } } },
      tokenHash: HASH,
      tokenSuffix: "cdef",
      token: API_TOKEN,
    });
  });

  it.each([
    ["the epoch", new Date(0)],
    ["before the epoch", new Date(-1)],
    ["an invalid date", new Date("not a date")],
  ])("createAPIToken refuses an expiry at %s unsent", async (_, expiresAt) => {
    const { client, sent } = recording({ "POST /api/v1/server/api-tokens": { status: 201 } });
    await expect(client().createAPIToken("ci", { expiresAt })).rejects.toThrow(RangeError);
    expect(sent).toHaveLength(0);
  });

  it.each([400, 409, 412])("a refused createAPIToken throws ArcadeDBError %i", async (status) => {
    const { client } = recording({ "POST /api/v1/server/api-tokens": { status, body: { error: "refused" } } });
    expect((await caught(client().createAPIToken("ci"))).status).toBe(status);
  });

  it("listAPITokens maps expiry and the expired flag", async () => {
    const { client } = recording({
      "GET /api/v1/server/api-tokens": {
        status: 200,
        body: {
          count: 2,
          result: [TOKEN_FIELDS, { ...TOKEN_FIELDS, name: "old", expiresAt: 1_760_000_000_000, expired: true }],
        },
      },
    });
    const [never, old] = await client().listAPITokens();
    expect([never!.expiresAt, never!.expired]).toEqual([null, false]);
    expect([old!.expiresAt, old!.expired]).toEqual([new Date(1_760_000_000_000), true]);
  });

  it("deleteAPIToken sends the hash", async () => {
    const { client, last } = recording({ "DELETE /api/v1/server/api-tokens": { status: 200, body: { result: "ok" } } });
    await client().deleteAPIToken(HASH);
    expect(last().url.searchParams.get("token")).toBe(HASH);
  });

  it.each([API_TOKEN, "", HASH.toUpperCase(), HASH.slice(1), `${HASH}0`, "g".repeat(64), ` ${HASH.slice(1)}`])(
    "deleteAPIToken refuses %j unsent, without repeating it",
    async (arg) => {
      const { client, sent } = recording({ "DELETE /api/v1/server/api-tokens": { status: 200, body: {} } });
      const err = await client()
        .deleteAPIToken(arg)
        .then(
          () => undefined,
          (e: unknown) => e,
        );
      expect(err).toBeInstanceOf(RangeError);
      if (arg) expect((err as Error).message).not.toContain(arg);
      expect(sent).toHaveLength(0);
    },
  );

  it("deleting an unknown hash throws 404", async () => {
    const { client } = recording({
      "DELETE /api/v1/server/api-tokens": { status: 404, body: { error: "Token not found" } },
    });
    expect((await caught(client().deleteAPIToken(HASH))).status).toBe(404);
  });
});
