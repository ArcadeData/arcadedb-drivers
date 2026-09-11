import { describe, expect, it, vi } from "vitest";
import { ArcadeDBError, createClient } from "../src/index.js";

function jsonResponse(body: unknown, status: number, extraHeaders: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...extraHeaders },
  });
}

function noContent(status = 204, extraHeaders: Record<string, string> = {}): Response {
  return new Response(null, { status, headers: extraHeaders });
}

describe("ArcadeDBDatabase.query", () => {
  it("returns the whole envelope, including truncated, and does not unwrap to result", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({ result: [{ name: "a" }], limit: 100, returned: 1, truncated: true }, 200),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const envelope = await server.db("mydb").query({ language: "sql", command: "SELECT FROM V" });

    expect(envelope).toEqual({ result: [{ name: "a" }], limit: 100, returned: 1, truncated: true });
  });

  it("POSTs to /api/v1/query/{database} with language, command and params in the body", async () => {
    let capturedRequest: Request | undefined;
    const fetchMock = vi.fn(async (request: Request) => {
      capturedRequest = request;
      return jsonResponse({ result: [], limit: 100, returned: 0, truncated: false }, 200);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await server.db("mydb").query({ language: "cypher", command: "MATCH (n) RETURN n", params: { x: 1 } });

    expect(capturedRequest?.method).toBe("POST");
    expect(new URL(capturedRequest!.url).pathname).toBe("/api/v1/query/mydb");
    await expect(capturedRequest!.clone().json()).resolves.toEqual({
      language: "cypher",
      command: "MATCH (n) RETURN n",
      params: { x: 1 },
    });
  });

  it("sends limit in the body when supplied (I11: QueryOptions.limit)", async () => {
    let capturedBody: unknown;
    const fetchMock = vi.fn(async (request: Request) => {
      capturedBody = await request.clone().json();
      return jsonResponse({ result: [], limit: 5, returned: 0, truncated: true }, 200);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await server.db("mydb").query({ language: "sql", command: "SELECT FROM V", limit: 5 });

    expect(capturedBody).toEqual({ language: "sql", command: "SELECT FROM V", limit: 5 });
  });

  it("sends no arcadedb-session-id header outside a transaction", async () => {
    let capturedHeader: string | null = null;
    const fetchMock = vi.fn(async (request: Request) => {
      capturedHeader = request.headers.get("arcadedb-session-id");
      return jsonResponse({ result: [], limit: 100, returned: 0, truncated: false }, 200);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await server.db("mydb").query({ language: "sql", command: "SELECT FROM V" });

    expect(capturedHeader).toBeNull();
  });
});

describe("ArcadeDBDatabase.command", () => {
  it("returns the whole envelope, not just the rows", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({ result: [{ "@rid": "#1:0" }], limit: -1, returned: 1, truncated: false }, 200),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const envelope = await server.db("mydb").command({ language: "sql", command: "CREATE VERTEX V" });

    expect(envelope).toEqual({ result: [{ "@rid": "#1:0" }], limit: -1, returned: 1, truncated: false });
  });

  it("POSTs to /api/v1/command/{database} with language, command and params in the body", async () => {
    let capturedBody: unknown;
    const fetchMock = vi.fn(async (request: Request) => {
      capturedBody = await request.clone().json();
      return jsonResponse({ result: [], limit: -1, returned: 0, truncated: false }, 200);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await server.db("mydb").command({ language: "sql", command: "CREATE VERTEX V", params: { name: "x" } });

    expect(capturedBody).toEqual({ language: "sql", command: "CREATE VERTEX V", params: { name: "x" } });
  });
});

describe("ArcadeDBDatabase.transaction", () => {
  it("issues begin, then the body's calls, then commit, threading the session id onto every call", async () => {
    const calls: { url: string; sessionHeader: string | null }[] = [];
    const fetchMock = vi.fn(async (request: Request) => {
      const url = new URL(request.url).pathname;
      calls.push({ url, sessionHeader: request.headers.get("arcadedb-session-id") });
      if (url === "/api/v1/begin/mydb") {
        return noContent(204, { "arcadedb-session-id": "sess-123" });
      }
      if (url === "/api/v1/query/mydb") {
        return jsonResponse({ result: [], limit: 100, returned: 0, truncated: false }, 200);
      }
      if (url === "/api/v1/command/mydb") {
        return jsonResponse({ result: [], limit: -1, returned: 0, truncated: false }, 200);
      }
      if (url === "/api/v1/commit/mydb") {
        return noContent();
      }
      throw new Error(`unexpected request to ${url}`);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await server.db("mydb").transaction(async (tx) => {
      await tx.query({ language: "sql", command: "SELECT FROM V" });
      await tx.command({ language: "sql", command: "CREATE VERTEX V" });
    });

    expect(calls.map((c) => c.url)).toEqual([
      "/api/v1/begin/mydb",
      "/api/v1/query/mydb",
      "/api/v1/command/mydb",
      "/api/v1/commit/mydb",
    ]);
    // The session-threading assertion that matters: every call issued through the
    // handle passed to `fn` must carry the session id `begin` returned - including commit
    // itself (M8: a header regression on commit/rollback stayed invisible before this).
    expect(calls[1].sessionHeader).toBe("sess-123");
    expect(calls[2].sessionHeader).toBe("sess-123");
    expect(calls[3].sessionHeader).toBe("sess-123");
  });

  it("returns the body's resolved value", async () => {
    const fetchMock = vi.fn(async (request: Request) => {
      const url = new URL(request.url).pathname;
      if (url === "/api/v1/begin/mydb") return noContent(204, { "arcadedb-session-id": "sess-ret" });
      if (url === "/api/v1/commit/mydb") return noContent();
      throw new Error(`unexpected request to ${url}`);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const result = await server.db("mydb").transaction(async () => "the-answer");

    expect(result).toBe("the-answer");
  });

  it("rolls back, not commits, when the body throws, and re-throws the original error", async () => {
    const calls: { url: string; sessionHeader: string | null }[] = [];
    const fetchMock = vi.fn(async (request: Request) => {
      const url = new URL(request.url).pathname;
      calls.push({ url, sessionHeader: request.headers.get("arcadedb-session-id") });
      if (url === "/api/v1/begin/mydb") return noContent(204, { "arcadedb-session-id": "sess-456" });
      if (url === "/api/v1/rollback/mydb") return noContent();
      throw new Error(`unexpected request to ${url}`);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const boom = new Error("boom from body");
    let caught: unknown;
    try {
      await server.db("mydb").transaction(async () => {
        throw boom;
      });
    } catch (err) {
      caught = err;
    }

    expect(caught).toBe(boom);
    expect(calls.map((c) => c.url)).toEqual(["/api/v1/begin/mydb", "/api/v1/rollback/mydb"]);
    // M8: the rollback call must also carry the session header, not just query/command.
    expect(calls[1].sessionHeader).toBe("sess-456");
  });

  it("rolls back even when the body throws synchronously (not merely a rejected promise)", async () => {
    const calls: string[] = [];
    const fetchMock = vi.fn(async (request: Request) => {
      const url = new URL(request.url).pathname;
      calls.push(url);
      if (url === "/api/v1/begin/mydb") return noContent(204, { "arcadedb-session-id": "sess-789" });
      if (url === "/api/v1/rollback/mydb") return noContent();
      throw new Error(`unexpected request to ${url}`);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const boom = new Error("sync boom");
    let caught: unknown;
    try {
      await server.db("mydb").transaction((): Promise<void> => {
        throw boom;
      });
    } catch (err) {
      caught = err;
    }

    expect(caught).toBe(boom);
    expect(calls).toEqual(["/api/v1/begin/mydb", "/api/v1/rollback/mydb"]);
  });

  it("surfaces a failing commit as ArcadeDBError and issues a best-effort rollback (I3)", async () => {
    const calls: string[] = [];
    const fetchMock = vi.fn(async (request: Request) => {
      const url = new URL(request.url).pathname;
      calls.push(url);
      if (url === "/api/v1/begin/mydb") return noContent(204, { "arcadedb-session-id": "sess-commit-fail" });
      if (url === "/api/v1/commit/mydb") return jsonResponse({ error: "commit failed" }, 500);
      if (url === "/api/v1/rollback/mydb") return noContent();
      throw new Error(`unexpected request to ${url}`);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    let caught: unknown;
    try {
      await server.db("mydb").transaction(async () => "ok");
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(ArcadeDBError);
    expect((caught as ArcadeDBError).status).toBe(500);
    // I3: a failed commit must not leak the server-side session - a rollback must follow it.
    expect(calls).toEqual(["/api/v1/begin/mydb", "/api/v1/commit/mydb", "/api/v1/rollback/mydb"]);
  });

  it("surfaces the body's own error, not the rollback's, when both the body throws and the rollback fails (I2)", async () => {
    const fetchMock = vi.fn(async (request: Request) => {
      const url = new URL(request.url).pathname;
      if (url === "/api/v1/begin/mydb") return noContent(204, { "arcadedb-session-id": "sess-both-fail" });
      if (url === "/api/v1/rollback/mydb") return jsonResponse({ error: "rollback failed" }, 500);
      throw new Error(`unexpected request to ${url}`);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const boom = new Error("the caller's real failure");
    let caught: unknown;
    try {
      await server.db("mydb").transaction(async () => {
        throw boom;
      });
    } catch (err) {
      caught = err;
    }

    // The BODY's error surfaces, not the rollback's - this is the assertion I2 exists to protect.
    expect(caught).toBe(boom);
    expect((caught as Error).message).toBe("the caller's real failure");
    // The rollback failure is not silently lost either: it is attached as `cause`.
    expect((caught as Error).cause).toBeInstanceOf(ArcadeDBError);
    expect(((caught as Error).cause as ArcadeDBError).status).toBe(500);
    expect(((caught as Error).cause as ArcadeDBError).error).toBe("rollback failed");
  });

  it("surfaces a frozen error as itself, not a TypeError, when both the body throws and the rollback fails", async () => {
    // A frozen Error is non-extensible: `err.cause = rollbackErr` throws
    // `TypeError: Cannot add property cause, object is not extensible` in strict-mode ESM.
    // Libraries that intern sentinel errors freeze them, so this is not a contrived input.
    const fetchMock = vi.fn(async (request: Request) => {
      const url = new URL(request.url).pathname;
      if (url === "/api/v1/begin/mydb") return noContent(204, { "arcadedb-session-id": "sess-frozen" });
      if (url === "/api/v1/rollback/mydb") return jsonResponse({ error: "rollback failed" }, 500);
      throw new Error(`unexpected request to ${url}`);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const boom = Object.freeze(new Error("frozen sentinel failure"));
    let caught: unknown;
    try {
      await server.db("mydb").transaction(async () => {
        throw boom;
      });
    } catch (err) {
      caught = err;
    }

    // The frozen error itself surfaces - not a TypeError from the failed `cause` assignment.
    expect(caught).toBe(boom);
    expect((caught as Error).message).toBe("frozen sentinel failure");
    expect((caught as Error).cause).toBeUndefined();
  });

  it("does not overwrite a caller-set cause when the rollback also fails", async () => {
    const fetchMock = vi.fn(async (request: Request) => {
      const url = new URL(request.url).pathname;
      if (url === "/api/v1/begin/mydb") return noContent(204, { "arcadedb-session-id": "sess-cause" });
      if (url === "/api/v1/rollback/mydb") return jsonResponse({ error: "rollback failed" }, 500);
      throw new Error(`unexpected request to ${url}`);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const originalCause = new Error("the caller's own causal chain");
    const boom = new Error("the caller's real failure", { cause: originalCause });
    let caught: unknown;
    try {
      await server.db("mydb").transaction(async () => {
        throw boom;
      });
    } catch (err) {
      caught = err;
    }

    // The caller's own `cause` survives - it is not replaced by the rollback's error.
    expect(caught).toBe(boom);
    expect((caught as Error).cause).toBe(originalCause);
  });
});

describe("the 200 response union (ArcadeData/arcadedb#7306)", () => {
  it("returns the buffered envelope unchanged when the server answers application/json", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({ result: [{ name: "a" }], limit: 100, returned: 1, truncated: false }, 200),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const envelope = await server.db("mydb").query({ language: "sql", command: "SELECT FROM V" });

    expect(envelope).toEqual({ result: [{ name: "a" }], limit: 100, returned: 1, truncated: false });
  });

  it("throws rather than returning an empty envelope when a 200 carries an ndjson event", async () => {
    // This client never sends `Accept: application/x-ndjson`, so this shape is
    // unreachable in practice. The point of the assertion is that if it ever
    // becomes reachable, the caller learns about it instead of silently
    // receiving `{ result: [], limit: -1, returned: 0, truncated: false }`.
    const fetchMock = vi.fn(async () => jsonResponse({ record: { name: "a" } }, 200));
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await expect(server.db("mydb").query({ language: "sql", command: "SELECT FROM V" })).rejects.toThrow(
      ArcadeDBError,
    );
  });

  it("throws on an ndjson stats trailer reaching command()", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({ stats: { limit: 100, returned: 1, truncated: false } }, 200),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await expect(
      server.db("mydb").command({ language: "sql", command: "UPDATE V SET x = 1" }),
    ).rejects.toThrow(ArcadeDBError);
  });

  it("treats an empty 200 body as the buffered envelope, not as an ndjson event", async () => {
    // Every field of QueryResponse is optional and every field of
    // NdJsonQueryEvent is too, so `{}` satisfies both. It is the encoding this
    // client asked for that breaks the tie.
    const fetchMock = vi.fn(async () => jsonResponse({}, 200));
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const envelope = await server.db("mydb").query({ language: "sql", command: "SELECT FROM V" });

    expect(envelope).toEqual({ result: [], limit: -1, returned: 0, truncated: false });
  });
});
