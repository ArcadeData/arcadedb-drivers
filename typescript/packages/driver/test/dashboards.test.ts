import { describe, expect, it, vi } from "vitest";
import { createClient } from "../src/index.js";

function jsonResponse(body: unknown, status: number, extraHeaders: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...extraHeaders },
  });
}

describe("db.grafana.query", () => {
  it("POSTs targets to /api/v1/ts/{database}/grafana/query and returns results keyed by refId", async () => {
    let capturedBody: unknown;
    const fetchMock = vi.fn(async (request: Request) => {
      capturedBody = await request.clone().json();
      return jsonResponse(
        { results: { A: { frames: [{ schema: { fields: [{ name: "time", type: "time" }] }, data: { values: [[1700000000]] } }] } } },
        200,
      );
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const response = await server.db("mydb").grafana.query({ targets: [{ refId: "A", type: "cpu" }] });

    expect(new URL(fetchMock.mock.calls[0][0].url).pathname).toBe("/api/v1/ts/mydb/grafana/query");
    expect(capturedBody).toEqual({ targets: [{ refId: "A", type: "cpu" }] });
    expect(response.results?.A?.frames?.[0]?.data?.values).toEqual([[1700000000]]);
  });
});

// The three tests below assert the runtime passthrough of each `resultType` branch's payload -
// that is all vitest (transpile-only, types stripped before the test runs) can actually verify.
// The "narrows without a cast" claim is a compile-time property of `PromQLResult` being a real
// discriminated union: `if (data.resultType === "vector") data.result` has type
// `PromQLVectorSample[]` with no cast needed. That property is real - `PromQLResult`'s own doc
// comment explains it - but nothing in THIS file checks it: `packages/driver/tsconfig.json` only
// `include`s "src", and the type-aware eslint block (`no-floating-promises` etc.) is scoped to
// `packages/driver/src/**/*.ts`, so test files here are never type-checked at all, let alone for
// this specific narrowing. Deleting the whole discriminated-union apparatus and replacing it with
// an untyped `any` would leave these tests byte-identical at runtime and still green.
describe("db.promql.query", () => {
  it("returns the vector-branch payload (metric, value) when resultType is vector", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(
        { status: "success", data: { resultType: "vector", result: [{ metric: { __name__: "up" }, value: [1700000000, "1"] }] } },
        200,
      ),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const response = await server.db("mydb").promql.query({ query: "up" });
    const data = response.data;

    if (data !== undefined && data.resultType === "vector") {
      expect(data.result[0].metric).toEqual({ __name__: "up" });
      expect(data.result[0].value).toEqual([1700000000, "1"]);
    } else {
      throw new Error("expected the vector branch");
    }
  });

  it("returns the matrix-branch payload (metric, values) when resultType is matrix", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(
        {
          status: "success",
          data: {
            resultType: "matrix",
            result: [{ metric: { __name__: "up" }, values: [[1700000000, "1"], [1700000060, "1"]] }],
          },
        },
        200,
      ),
    );
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const response = await server.db("mydb").promql.queryRange({ query: "up", start: "0", end: "60", step: "60" });
    const data = response.data;

    if (data !== undefined && data.resultType === "matrix") {
      expect(data.result[0].metric).toEqual({ __name__: "up" });
      expect(data.result[0].values).toEqual([[1700000000, "1"], [1700000060, "1"]]);
    } else {
      throw new Error("expected the matrix branch");
    }
  });

  it("returns the scalar-branch payload ([timestamp, value]) when resultType is scalar", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ status: "success", data: { resultType: "scalar", result: [1700000000, "42"] } }, 200));
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const response = await server.db("mydb").promql.query({ query: "scalar(up)" });
    const data = response.data;

    if (data !== undefined && data.resultType === "scalar") {
      expect(data.result).toEqual([1700000000, "42"]);
    } else {
      throw new Error("expected the scalar branch");
    }
  });

  it("sends query, time and lookback_delta as query parameters", async () => {
    let capturedUrl: URL | undefined;
    const fetchMock = vi.fn(async (request: Request) => {
      capturedUrl = new URL(request.url);
      return jsonResponse({ status: "success", data: { resultType: "vector", result: [] } }, 200);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await server.db("mydb").promql.query({ query: "up", time: "1700000000", lookback_delta: "5m" });

    expect(capturedUrl?.pathname).toBe("/api/v1/ts/mydb/prom/api/v1/query");
    expect(capturedUrl?.searchParams.get("query")).toBe("up");
    expect(capturedUrl?.searchParams.get("time")).toBe("1700000000");
    expect(capturedUrl?.searchParams.get("lookback_delta")).toBe("5m");
  });
});

describe("db.promql.labels", () => {
  it("GETs /api/v1/ts/{database}/prom/api/v1/labels and returns sorted label names", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ status: "success", data: ["__name__", "host"] }, 200));
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const response = await server.db("mydb").promql.labels();

    expect(new URL(fetchMock.mock.calls[0][0].url).pathname).toBe("/api/v1/ts/mydb/prom/api/v1/labels");
    expect(response.data).toEqual(["__name__", "host"]);
  });
});

describe("db.promql.series", () => {
  it("GETs /api/v1/ts/{database}/prom/api/v1/series with repeated match[] parameters", async () => {
    let capturedUrl: URL | undefined;
    const fetchMock = vi.fn(async (request: Request) => {
      capturedUrl = new URL(request.url);
      return jsonResponse({ status: "success", data: [{ __name__: "up", host: "a" }] }, 200);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const response = await server.db("mydb").promql.series({ "match[]": ["up", "cpu"] });

    expect(capturedUrl?.pathname).toBe("/api/v1/ts/mydb/prom/api/v1/series");
    expect(capturedUrl?.searchParams.getAll("match[]")).toEqual(["up", "cpu"]);
    expect(response.data).toEqual([{ __name__: "up", host: "a" }]);
  });
});

describe("db.promql.labelValues", () => {
  it("GETs /api/v1/ts/{database}/prom/api/v1/label/{name}/values with the range", async () => {
    let capturedUrl: URL | undefined;
    const fetchMock = vi.fn(async (request: Request) => {
      capturedUrl = new URL(request.url);
      return jsonResponse({ status: "success", data: ["cpu", "memory"] }, 200);
    });
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    const response = await server.db("mydb").promql.labelValues("__name__", { start: "1700000000" });

    expect(capturedUrl?.pathname).toBe("/api/v1/ts/mydb/prom/api/v1/label/__name__/values");
    expect(capturedUrl?.searchParams.get("start")).toBe("1700000000");
    expect(capturedUrl?.searchParams.has("end")).toBe(false);
    expect(response.data).toEqual(["cpu", "memory"]);
  });

  it("percent-encodes the label name exactly once", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ status: "success", data: [] }, 200));
    const server = createClient({ baseUrl: "https://example.com", fetch: fetchMock as unknown as typeof fetch });

    await server.db("mydb").promql.labelValues("a/b c");

    expect(new URL(fetchMock.mock.calls[0][0].url).pathname).toBe("/api/v1/ts/mydb/prom/api/v1/label/a%2Fb%20c/values");
  });
});
