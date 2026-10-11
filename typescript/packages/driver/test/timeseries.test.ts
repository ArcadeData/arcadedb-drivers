import { describe, expect, it, vi } from "vitest";
import { ArcadeDBError, createClient, TimeSeriesWriteError } from "../src/index.js";

function jsonResponse(body: unknown, status: number, extraHeaders: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...extraHeaders },
  });
}

function noContent(status = 204, extraHeaders: Record<string, string> = {}): Response {
  return new Response(null, { status, headers: extraHeaders });
}

describe("db.ts.write", () => {
  it("POSTs the line protocol body as text/plain, not JSON, to /api/v1/ts/{database}/write", async () => {
    let capturedRequest: Request | undefined;
    const fetchMock = vi.fn(async (request: Request) => {
      capturedRequest = request;
      return noContent();
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await server.db("mydb").ts.write({ lineProtocol: "cpu,host=a value=1 1700000000000000000" });

    expect(capturedRequest?.method).toBe("POST");
    expect(new URL(capturedRequest!.url).pathname).toBe("/api/v1/ts/mydb/write");
    expect(capturedRequest?.headers.get("content-type")).toBe("text/plain");
    await expect(capturedRequest!.clone().text()).resolves.toBe("cpu,host=a value=1 1700000000000000000");
  });

  it("sends precision as a query parameter when supplied", async () => {
    let capturedRequest: Request | undefined;
    const fetchMock = vi.fn(async (request: Request) => {
      capturedRequest = request;
      return noContent();
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await server.db("mydb").ts.write({ lineProtocol: "cpu value=1 1700000000", precision: "s" });

    expect(new URL(capturedRequest!.url).searchParams.get("precision")).toBe("s");
  });
});

describe("db.ts.query", () => {
  it("narrows to the raw shape via the `rows` property, without a cast, when the response carries rows", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({ type: "cpu", columns: ["time", "value"], count: 1, rows: [[1700000000, 42]] }, 200),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const result = await server.db("mydb").ts.query({ type: "cpu" });

    if ("rows" in result) {
      expect(result.rows).toEqual([[1700000000, 42]]);
      expect(result.columns).toEqual(["time", "value"]);
    } else {
      throw new Error("expected the raw (rows) branch, got the aggregated branch");
    }
  });

  it("narrows to the aggregated shape via the `buckets` property, without a cast, when the response carries buckets", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(
        { type: "cpu", aggregations: ["value_avg"], count: 1, buckets: [{ timestamp: 1700000000, values: [21] }] },
        200,
      ),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const result = await server.db("mydb").ts.query({
      type: "cpu",
      aggregation: { bucketInterval: 60, requests: [{ field: "value", type: "AVG" }] },
    });

    if ("buckets" in result) {
      expect(result.buckets).toEqual([{ timestamp: 1700000000, values: [21] }]);
      expect(result.aggregations).toEqual(["value_avg"]);
    } else {
      throw new Error("expected the aggregated (buckets) branch, got the raw branch");
    }
  });

  it("POSTs the query definition as JSON to /api/v1/ts/{database}/query", async () => {
    let capturedRequest: Request | undefined;
    let capturedBody: unknown;
    const fetchMock = vi.fn(async (request: Request) => {
      capturedRequest = request;
      capturedBody = await request.clone().json();
      return jsonResponse({ type: "cpu", columns: [], count: 0, rows: [] }, 200);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await server.db("mydb").ts.query({ type: "cpu", from: 1, to: 2 });

    expect(capturedRequest?.method).toBe("POST");
    expect(new URL(capturedRequest!.url).pathname).toBe("/api/v1/ts/mydb/query");
    expect(capturedBody).toEqual({ type: "cpu", from: 1, to: 2 });
  });
});

describe("db.ts.write failures (issue #117)", () => {
  const BODY = {
    error: "2 samples dropped",
    written: 3,
    dropped: 2,
    requestId: "body-req",
    unknownTypes: ["nope"],
    nonTimeSeriesTypes: ["Person"],
    unavailableTypes: [],
    undeclaredKeys: ["humidity"],
  };

  it("raises TimeSeriesWriteError on a 400, carrying written, dropped and the reason lists", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(BODY, 400, { "X-Request-Id": "header-req", "X-ArcadeDB-Commit-Index": "5" }));
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    let caught: unknown;
    try {
      await server.db("mydb").ts.write({ lineProtocol: "nope value=1" });
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(TimeSeriesWriteError);
    expect(caught).toBeInstanceOf(ArcadeDBError);
    const err = caught as TimeSeriesWriteError;
    expect(err.status).toBe(400);
    expect(err.error).toBe("2 samples dropped");
    expect(err.requestId).toBe("header-req");
    expect(err.commitIndex).toBe(5);
    expect(err.written).toBe(3);
    expect(err.dropped).toBe(2);
    expect(err.unknownTypes).toEqual(["nope"]);
    expect(err.nonTimeSeriesTypes).toEqual(["Person"]);
    expect(err.unavailableTypes).toEqual([]);
    expect(err.undeclaredKeys).toEqual(["humidity"]);
  });

  it("raises a plain ArcadeDBError on any other non-2xx status, with Retry-After read", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ error: "not ready" }, 503, { "Retry-After": "9" }));
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    let caught: unknown;
    try {
      await server.db("mydb").ts.write({ lineProtocol: "cpu value=1" });
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(ArcadeDBError);
    expect(caught).not.toBeInstanceOf(TimeSeriesWriteError);
    expect((caught as ArcadeDBError).status).toBe(503);
    expect((caught as ArcadeDBError).retryAfter).toBe(9);
  });

  it("raises a plain ArcadeDBError on a 400 whose body is not a JSON object", async () => {
    const fetchMock = vi.fn(async () => new Response("bad line protocol", { status: 400, headers: { "content-type": "text/plain" } }));
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    let caught: unknown;
    try {
      await server.db("mydb").ts.write({ lineProtocol: "garbage" });
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(ArcadeDBError);
    expect(caught).not.toBeInstanceOf(TimeSeriesWriteError);
    expect((caught as ArcadeDBError).status).toBe(400);
  });
});
