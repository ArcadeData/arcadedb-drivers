import type { Client } from "openapi-fetch";
import type { components, paths } from "../generated/schema.js";
import { ArcadeDBError, TimeSeriesWriteError } from "../errors.js";
import { unwrap } from "../internal/unwrap.js";

/** The unwrapped openapi-fetch client, typed against ArcadeDB's OpenAPI schema. */
type RawClient = Client<paths>;

/**
 * Query definition accepted by `db.ts.query()`. Confirmed against the generated `TimeSeriesQueryRequest` schema.
 *
 * A name in `tags` that is not one of the type's declared TAG columns is refused server-side (400,
 * naming the tag and the type's declared TAG columns) rather than dropped - see the README's
 * "Time series" section.
 */
export type TimeSeriesQueryOptions = components["schemas"]["TimeSeriesQueryRequest"];

/**
 * `POST /api/v1/ts/{database}/query` answers with a `oneOf`: `TimeSeriesRawResponse` when the
 * request carried no `aggregation`, `TimeSeriesAggregatedResponse` when it did.
 * openapi-typescript emits this as a genuine union of the two named schemas - not a
 * manufactured type - so callers can narrow with the `in` operator, e.g. `"buckets" in result`
 * or `"rows" in result`, without a cast.
 */
export type TimeSeriesQueryResult = components["schemas"]["TimeSeriesRawResponse"] | components["schemas"]["TimeSeriesAggregatedResponse"];

/** Body accepted by `db.ts.write()`. */
export interface TimeSeriesWriteOptions {
  /** InfluxDB Line Protocol text, one measurement per line. */
  lineProtocol: string;
  /** Unit of the timestamps in `lineProtocol`. Defaults to nanoseconds when omitted. */
  precision?: "ns" | "us" | "ms" | "s";
}

/**
 * Executes `POST /api/v1/ts/{database}/write`. The endpoint takes the line-protocol text as a
 * raw `text/plain` body, not JSON, so the default (JSON) body serializer is overridden with the
 * identity function and the content type is set explicitly. Answers 204 with no body once every
 * sample is applied.
 *
 * Does not go through `unwrap`, because a 400 here is the one failure with a body worth more than
 * the standard error fields: the contract's `TimeSeriesWriteError`, saying how many samples landed
 * and why the rest were dropped. A 400 whose body is a JSON object therefore throws
 * `TimeSeriesWriteError`; every other non-2xx - and a 400 whose body is not an object - throws a
 * plain `ArcadeDBError`, exactly as `unwrap` would.
 */
export async function writeTimeSeries(client: RawClient, database: string, opts: TimeSeriesWriteOptions): Promise<void> {
  const { error, response } = await client.POST("/api/v1/ts/{database}/write", {
    params: { path: { database }, query: { precision: opts.precision } },
    headers: { "Content-Type": "text/plain" },
    body: opts.lineProtocol,
    bodySerializer: (body: string) => body,
  });
  if (response.ok) return;
  if (response.status === 400 && error !== null && typeof error === "object" && !Array.isArray(error)) {
    throw TimeSeriesWriteError.fromResponse(response, error);
  }
  throw ArcadeDBError.fromResponse(response, error);
}

/**
 * Executes `POST /api/v1/ts/{database}/query`. Returns the whole response, unaltered - raw rows
 * or aggregated buckets, depending on whether `opts.aggregation` was set.
 */
export async function queryTimeSeries(client: RawClient, database: string, opts: TimeSeriesQueryOptions): Promise<TimeSeriesQueryResult> {
  return unwrap(
    client.POST("/api/v1/ts/{database}/query", {
      params: { path: { database } },
      body: opts,
    }),
  );
}
