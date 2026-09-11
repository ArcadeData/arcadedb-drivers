import { describe, expect, it, vi } from "vitest";
import { ArcadeDBError, createClient } from "../src/index.js";

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

describe("db.vector.search", () => {
  it("POSTs to /api/v1/vector/{database}/search with the request body unaltered", async () => {
    let captured: Request | undefined;
    const fetchMock = vi.fn(async (request: Request) => {
      captured = request;
      return jsonResponse({ results: [], count: 0, truncated: false }, 200);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await server.db("mydb").vector.search({ indexName: "v_idx", queryVector: [0.1, 0.2], k: 5 });

    expect(captured?.method).toBe("POST");
    expect(new URL(captured!.url).pathname).toBe("/api/v1/vector/mydb/search");
    await expect(captured!.clone().json()).resolves.toEqual({ indexName: "v_idx", queryVector: [0.1, 0.2], k: 5 });
  });

  it("returns the whole response, including truncated, and does not unwrap to results (D-M5-2)", async () => {
    const body = { results: [{ rid: "#1:0", score: 0.9 }], count: 1, truncated: true, scoring: "cosine", indexName: "v_idx", sparse: false, candidateLimit: 100 };
    const fetchMock = vi.fn(async () => jsonResponse(body, 200));
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const result = await server.db("mydb").vector.search({ indexName: "v_idx", queryVector: [0.1] });

    expect(result).toEqual(body);
  });

  it("throws ArcadeDBError on a non-2xx", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ error: "no such index" }, 400));
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await expect(server.db("mydb").vector.search({ indexName: "nope", queryVector: [0.1] })).rejects.toThrow(ArcadeDBError);
  });

  it("percent-encodes a database name with a slash in the path", async () => {
    let captured: Request | undefined;
    const fetchMock = vi.fn(async (request: Request) => {
      captured = request;
      return jsonResponse({ results: [] }, 200);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await server.db("od/db").vector.search({ indexName: "v_idx", queryVector: [0.1] });

    expect(new URL(captured!.url).pathname).toBe("/api/v1/vector/od%2Fdb/search");
  });
});

describe("db.vector.hybrid", () => {
  it("POSTs to /api/v1/vector/{database}/hybrid and returns the whole response", async () => {
    let captured: Request | undefined;
    const body = { results: [], count: 0, truncated: false, fused: true, fusionStrategy: "rrf", vectorIndexName: "v_idx", fulltextIndexName: "ft_idx" };
    const fetchMock = vi.fn(async (request: Request) => {
      captured = request;
      return jsonResponse(body, 200);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const result = await server.db("mydb").vector.hybrid({ vectorIndexName: "v_idx", queryVector: [0.1], fulltextQuery: "cat" });

    expect(new URL(captured!.url).pathname).toBe("/api/v1/vector/mydb/hybrid");
    expect(result).toEqual(body);
  });
});

describe("db.vector.fulltext", () => {
  it("POSTs to /api/v1/vector/{database}/fulltext and returns the whole response", async () => {
    let captured: Request | undefined;
    const body = { results: [{ rid: "#2:1" }], count: 1, indexName: "ft_idx", similarity: "bm25" };
    const fetchMock = vi.fn(async (request: Request) => {
      captured = request;
      return jsonResponse(body, 200);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const result = await server.db("mydb").vector.fulltext({ queryText: "cat" });

    expect(new URL(captured!.url).pathname).toBe("/api/v1/vector/mydb/fulltext");
    expect(result).toEqual(body);
  });

  it("has no truncated field in its contract, unlike search and hybrid (D-M5-2)", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ results: [], count: 0 }, 200));
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const result = await server.db("mydb").vector.fulltext({ queryText: "cat" });

    expect("truncated" in result).toBe(false);
  });
});
