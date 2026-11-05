// List and terminate running work, and `progress` (issue #124). Bodies are copied from a live
// 26.11.1-SNAPSHOT server.
import { describe, expect, it, vi } from "vitest";
import { ArcadeDBError, createClient, isQueryTerminated } from "../src/index.js";
import type { QueryStatus } from "../src/index.js";

const BASE = "http://db.test";

interface Sent {
  method: string;
  url: URL;
  body: unknown;
}

/** A client whose fetch answers with `answer()` and records what it was sent. */
function recording(status: number, body: unknown) {
  const sent: Sent[] = [];
  let next = { status, body };
  const fetchMock = vi.fn(async (input: Request) => {
    const text = await input.text();
    sent.push({ method: input.method, url: new URL(input.url), body: text ? JSON.parse(text) : undefined });
    return new Response(next.body === undefined ? null : JSON.stringify(next.body), {
      status: next.status,
      headers: { "content-type": "application/json" },
    });
  });
  const server = createClient({ baseUrl: BASE, fetch: fetchMock as unknown as typeof fetch });
  return {
    server,
    sent,
    last: () => sent[sent.length - 1]!,
    answer: (s: number, b: unknown) => {
      next = { status: s, body: b };
    },
  };
}

const QUERY_ROW = {
  id: "q5-1f6d4564",
  database: "p",
  user: "root",
  protocol: "http",
  language: "sql",
  text: "SLEEP 20000",
  startedAt: 1792137065792,
  elapsedMs: 1507,
  terminating: false,
  sessionId: "AS-1",
  tag: "tagA",
  clientAddress: "/192.168.65.1:18259",
  server: "ArcadeDB_0",
};

describe("listQueries", () => {
  it.each([
    [{}, "list queries"],
    [{ database: "p" }, "list queries database p"],
    [{ tag: "a b" }, "list queries tag a b"],
    [{ database: "p", tag: "nightly" }, "list queries database p tag nightly"],
    [{ database: "", tag: "" }, "list queries"],
  ])("sends %j as %s and returns the rows", async (opts, command) => {
    const { server, last } = recording(200, { result: [QUERY_ROW] });
    const got = await server.listQueries(opts);
    expect(last().method).toBe("POST");
    expect(last().url.pathname).toBe("/api/v1/server");
    expect(last().body).toEqual({ command, language: "sql" });
    expect(got).toEqual([QUERY_ROW]);
  });
});

describe("terminateQuery", () => {
  it.each(["terminated", "completed", "terminating", "not found"] satisfies QueryStatus[])(
    "returns the %s status",
    async (status) => {
      const { server, last } = recording(200, { result: { id: "q6", status } });
      expect(await server.terminateQuery("q6")).toEqual({ id: "q6", status });
      expect(last().body).toEqual({ command: "terminate query q6", language: "sql" });
    },
  );

  it("passes the session fields through", async () => {
    const result = { id: "q6", status: "terminating", sessionId: "AS-262f", sessionOpen: true };
    const { server } = recording(200, { result });
    expect(await server.terminateQuery("q6")).toEqual(result);
  });

  it.each([
    [undefined, undefined],
    [0, undefined],
    [-1, undefined],
    [3000, 3000],
    [0.2, 1],
    [1.5, 2],
  ])("sends waitMs %s as wait %s", async (waitMs, wait) => {
    const { server, last } = recording(200, { result: [] });
    expect(await server.terminateQueriesByTag("t", waitMs === undefined ? {} : { waitMs })).toEqual([]);
    expect(last().body).toEqual({ command: "terminate queries tag t", language: "sql", ...(wait ? { wait } : {}) });
  });
});

describe("terminateQueriesByTag", () => {
  it("sends the tag as given and returns each answer", async () => {
    const result = [
      { id: "q1", status: "terminated" },
      { id: "q2", status: "completed" },
    ];
    const { server, last } = recording(200, { result });
    expect(await server.terminateQueriesByTag(`it's "q"`, { waitMs: 1000 })).toEqual(result);
    expect(last().body).toEqual({ command: `terminate queries tag it's "q"`, language: "sql", wait: 1000 });
  });
});

describe("transactions", () => {
  it("lists and terminates them", async () => {
    const row = {
      id: "AS-4c9d",
      user: "root",
      database: "p",
      idleMs: 1522,
      busy: true,
      runningQueries: ["q16"],
      server: "ArcadeDB_0",
    };
    const { server, last, answer } = recording(200, { result: [row] });
    expect(await server.listTransactions()).toEqual([row]);
    expect(last().body).toEqual({ command: "list transactions", language: "sql" });

    answer(200, { result: { id: "AS-4c9d", status: "terminated" } });
    expect(await server.terminateTransaction("AS-4c9d", { waitMs: 2000 })).toEqual({ id: "AS-4c9d", status: "terminated" });
    expect(last().body).toEqual({ command: "terminate transaction AS-4c9d", language: "sql", wait: 2000 });
  });
});

describe("arguments the server would split or trim", () => {
  it.each([
    ["an empty id", (s: ReturnType<typeof createClient>) => s.terminateQuery("")],
    ["an id with a space", (s: ReturnType<typeof createClient>) => s.terminateQuery("q1 q2")],
    ["an empty tag", (s: ReturnType<typeof createClient>) => s.terminateQueriesByTag("")],
    ["a padded tag", (s: ReturnType<typeof createClient>) => s.terminateQueriesByTag(" t")],
    ["a padded list tag", (s: ReturnType<typeof createClient>) => s.listQueries({ tag: "t\n" })],
    ["a database with a tab", (s: ReturnType<typeof createClient>) => s.listQueries({ database: "a\tb" })],
    ["an empty session id", (s: ReturnType<typeof createClient>) => s.terminateTransaction("")],
    ["a session id with a space", (s: ReturnType<typeof createClient>) => s.terminateTransaction("AS-1 x")],
    ["an id with a control character", (s: ReturnType<typeof createClient>) => s.terminateQuery("q1\x01")],
    ["a tag ending in NUL", (s: ReturnType<typeof createClient>) => s.terminateQueriesByTag("t\x00")],
    ["an infinite waitMs", (s: ReturnType<typeof createClient>) => s.terminateQuery("q1", { waitMs: Infinity })],
    ["a NaN waitMs", (s: ReturnType<typeof createClient>) => s.terminateQueriesByTag("t", { waitMs: NaN })],
  ])("refuses %s unsent", async (_, call) => {
    const { server, sent } = recording(200, { result: [] });
    await expect(call(server)).rejects.toBeInstanceOf(RangeError);
    expect(sent).toHaveLength(0);
  });
});

describe("errors", () => {
  it("throws ArcadeDBError on a non-2xx status and TypeError on a body with no result", async () => {
    const { server, answer } = recording(400, { error: "Server command not valid", detail: "Syntax" });
    await expect(server.terminateQuery("q1")).rejects.toMatchObject({ status: 400 });
    for (const body of [undefined, {}, { result: null }]) {
      answer(200, body);
      await expect(server.listTransactions()).rejects.toBeInstanceOf(TypeError);
    }
  });

  it("isQueryTerminated matches only the terminated 409", async () => {
    const terminated = {
      error: "Query terminated",
      requestId: "ee5d",
      exception: "com.arcadedb.exception.QueryTerminatedException",
      detail: "the commit has been terminated (query q5-1f6d4564, terminated by root)",
    };
    const { server, answer } = recording(409, terminated);
    const err = await server
      .db("p")
      .command({ language: "sql", command: "SLEEP 20000" })
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ArcadeDBError);
    expect(isQueryTerminated(err)).toBe(true);

    answer(409, { error: "Still in flight", exception: "com.arcadedb.server.http.RequestStillInFlightException" });
    const other = await server
      .db("p")
      .command({ language: "sql", command: "SELECT 1" })
      .catch((e: unknown) => e);
    expect(isQueryTerminated(other)).toBe(false);
    expect(isQueryTerminated(new Error("Query terminated"))).toBe(false);
    expect(isQueryTerminated(undefined)).toBe(false);
  });
});

describe("db.progress", () => {
  it("GETs /api/v1/progress/{database}", async () => {
    const body = {
      result: [
        {
          database: "p",
          done: 40,
          elapsedMs: 1200,
          id: 7,
          operation: "CHECK DATABASE",
          percentage: 40,
          startedOn: 1792137065792,
          stepIndex: 1,
          stepName: "pages",
          total: 100,
          totalSteps: 3,
        },
      ],
    };
    const { server, last, answer } = recording(200, body);
    expect(await server.db("p").progress()).toEqual(body);
    expect(last().method).toBe("GET");
    expect(last().url.pathname).toBe("/api/v1/progress/p");

    answer(403, { error: "Security error" });
    await expect(server.db("p").progress()).rejects.toMatchObject({ status: 403 });
  });
});

describe("the white-space rule", () => {
  // Java's trim: at or below U+0020. A no-break space is not white space to the server.
  it("sends a tag ending in a no-break space", async () => {
    const { server, last } = recording(200, { result: [] });
    await server.terminateQueriesByTag("t\u00a0");
    expect(last().body).toEqual({ command: "terminate queries tag t\u00a0", language: "sql" });
  });
});
