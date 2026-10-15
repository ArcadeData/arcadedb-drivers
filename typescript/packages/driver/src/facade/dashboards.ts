import type { Client } from "openapi-fetch";
import type { components, operations, paths } from "../generated/schema.js";
import { unwrap } from "../internal/unwrap.js";

/** The unwrapped openapi-fetch client, typed against ArcadeDB's OpenAPI schema. */
type RawClient = Client<paths>;

// ---- Grafana ----

export type GrafanaQueryOptions = components["schemas"]["GrafanaQueryRequest"];
export type GrafanaQueryResponse = components["schemas"]["GrafanaQueryResponse"];

/**
 * Executes `POST /api/v1/ts/{database}/grafana/query`: one query per `targets` entry, results
 * keyed by each target's `refId`, in the Grafana DataFrame format. Returns the whole response
 * unaltered, including per-target `error` entries for targets the server could not resolve.
 */
export async function queryGrafana(client: RawClient, database: string, opts: GrafanaQueryOptions): Promise<GrafanaQueryResponse> {
  return unwrap(
    client.POST("/api/v1/ts/{database}/grafana/query", {
      params: { path: { database } },
      body: opts,
    }),
  );
}

// ---- PromQL ----

export type PromQLQueryOptions = operations["promQLQuery"]["parameters"]["query"];
export type PromQLQueryRangeOptions = operations["promQLQueryRange"]["parameters"]["query"];
export type PromQLSeriesOptions = operations["promQLSeries"]["parameters"]["query"];
export type PromQLLabelValuesOptions = operations["promQLLabelValues"]["parameters"]["query"];
export type PromQLLabelsResponse = components["schemas"]["PromQLLabelsResponse"];
export type PromQLSeriesResponse = components["schemas"]["PromQLSeriesResponse"];

/** One instant sample: a label set (including `__name__`) plus a single `[timestamp, value]` pair. */
export interface PromQLVectorSample {
  metric: Record<string, string>;
  value: unknown[];
}

/** One range series: a label set (including `__name__`) plus samples ordered by timestamp. */
export interface PromQLMatrixSeries {
  metric: Record<string, string>;
  values: unknown[][];
}

/**
 * `PromQLDataResponse.data.result` is generated (see `schema.d.ts`) as an `anyOf` of three
 * shapes, flattened by openapi-typescript into a plain, non-discriminated union:
 *
 * ```ts
 * result?: { metric: {...}; value: unknown[] }[]
 *        | { metric: {...}; values: unknown[][] }[]
 *        | unknown[];
 * resultType?: "vector" | "matrix" | "scalar";
 * ```
 *
 * `resultType` and `result` are sibling properties of one object type, not a discriminated
 * union, so narrowing on `resultType` does not narrow `result` there without a cast. `anyOf`
 * rather than `oneOf` is deliberate on the server side: an empty result array validates against
 * every array branch, and a matrix result with exactly two series is an outer array of length 2
 * that also matches the scalar branch.
 *
 * This re-declares the same fields as an actual discriminated union keyed on `resultType`, so a
 * caller can narrow (`data.resultType === "vector"`) and reach the matching `result` shape
 * without a cast. It is a retype, not a reinterpretation: every field name and value is exactly
 * what the server sends, unchanged.
 */
export type PromQLResult =
  | { resultType: "vector"; result: PromQLVectorSample[] }
  | { resultType: "matrix"; result: PromQLMatrixSeries[] }
  | { resultType: "scalar"; result: unknown[] };

export interface PromQLDataResponse {
  /** Always 'success' on a 200. */
  status?: string;
  data?: PromQLResult;
}

/**
 * The one boundary cast this namespace takes: openapi-typescript cannot emit a discriminated
 * union for an `anyOf` (see the `PromQLResult` doc comment). The runtime shape is unchanged -
 * `resultType` and a matching `result` always travel together on the wire - so this widens the
 * compile-time type only, never the data itself, and it happens once here rather than at every
 * call site.
 */
function toPromQLDataResponse(data: components["schemas"]["PromQLDataResponse"]): PromQLDataResponse {
  return data as unknown as PromQLDataResponse;
}

/**
 * Anchors the hand-declared `PromQLResult`/`PromQLVectorSample`/`PromQLMatrixSeries` types (above)
 * back to what `openapi-typescript` actually generates for `PromQLDataResponse.data`. Those hand
 * types exist because the generator flattens the server's `anyOf` into an anonymous,
 * non-discriminated union with no usable name to import - see `PromQLResult`'s doc comment. That
 * makes them a hand-maintained description of a server payload: if the contract's PromQL branch
 * shapes ever change, the boundary cast above absorbs the difference silently and this client
 * would misrepresent the server's data with nothing to catch it.
 *
 * Two independent things are anchored below, and each catches a different kind of drift - neither
 * substitutes for the other:
 *  - the SHAPE of the `vector`/`matrix` elements (this block): a rename, drop, or type change on
 *    `metric`/`value`/`values` breaks `tsc`;
 *  - the SET of `resultType` branches (further below): a fourth branch added to the contract (for
 *    example PromQL's own `"string"` type, which Prometheus itself has and ArcadeDB does not emit
 *    today) or one removed breaks `tsc`. Element-shape anchoring alone does not catch this - it has
 *    nothing to say about a `resultType` value neither union mentions.
 *
 * The element-shape checks:
 *  - the generated vector/matrix element shapes are extracted from the `result` union via
 *    `Extract`, keyed on each branch's distinguishing field (`value` vs `values`) since the
 *    generator does not preserve `resultType` as a discriminant;
 *  - each generated element type must extend its hand-declared counterpart (catches the generator
 *    dropping or renaming a field our hand type still claims);
 *  - each hand-declared element type must extend its generated counterpart (catches the generator
 *    adding a new required field our hand type does not carry, or narrowing a field's type).
 * Together the two directions require structural equality, not just one-way compatibility -
 * one-way alone would pass trivially because every array type is assignable to the `unknown[]`
 * scalar branch that is also part of the generated union.
 */
type GeneratedPromQLResultField = NonNullable<NonNullable<components["schemas"]["PromQLDataResponse"]["data"]>["result"]>;
type GeneratedPromQLVectorSample = Extract<GeneratedPromQLResultField, { value: unknown }[]>[number];
type GeneratedPromQLMatrixSeries = Extract<GeneratedPromQLResultField, { values: unknown }[]>[number];

type _AssertVectorSampleMatchesGenerated = [GeneratedPromQLVectorSample] extends [PromQLVectorSample]
  ? [PromQLVectorSample] extends [GeneratedPromQLVectorSample]
    ? true
    : never
  : never;
type _AssertMatrixSeriesMatchesGenerated = [GeneratedPromQLMatrixSeries] extends [PromQLMatrixSeries]
  ? [PromQLMatrixSeries] extends [GeneratedPromQLMatrixSeries]
    ? true
    : never
  : never;

const _promQLVectorSampleIsAnchored: _AssertVectorSampleMatchesGenerated = true;
const _promQLMatrixSeriesIsAnchored: _AssertMatrixSeriesMatchesGenerated = true;
void _promQLVectorSampleIsAnchored;
void _promQLMatrixSeriesIsAnchored;

/**
 * Anchors the SET of `resultType` branches `PromQLResult` hand-declares against what the
 * generated schema actually enumerates (see the doc comment above). This is the check that
 * catches a fourth branch appearing in - or one disappearing from - the contract; the
 * element-shape anchors above do not, because they only compare the branches both sides already
 * agree exist.
 */
type GeneratedPromQLResultType = NonNullable<NonNullable<components["schemas"]["PromQLDataResponse"]["data"]>["resultType"]>;

type _AssertResultTypesMatchGenerated = [GeneratedPromQLResultType] extends [PromQLResult["resultType"]]
  ? [PromQLResult["resultType"]] extends [GeneratedPromQLResultType]
    ? true
    : never
  : never;

const _promQLResultTypesAreAnchored: _AssertResultTypesMatchGenerated = true;
void _promQLResultTypesAreAnchored;

/** Executes `GET /api/v1/ts/{database}/prom/api/v1/query`: evaluates a PromQL expression at one instant. */
export async function queryPromQL(client: RawClient, database: string, opts: PromQLQueryOptions): Promise<PromQLDataResponse> {
  const data = await unwrap(
    client.GET("/api/v1/ts/{database}/prom/api/v1/query", {
      params: { path: { database }, query: opts },
    }),
  );
  return toPromQLDataResponse(data);
}

/** Executes `GET /api/v1/ts/{database}/prom/api/v1/query_range`: evaluates a PromQL expression across a range. */
export async function queryRangePromQL(client: RawClient, database: string, opts: PromQLQueryRangeOptions): Promise<PromQLDataResponse> {
  const data = await unwrap(
    client.GET("/api/v1/ts/{database}/prom/api/v1/query_range", {
      params: { path: { database }, query: opts },
    }),
  );
  return toPromQLDataResponse(data);
}

/** Executes `GET /api/v1/ts/{database}/prom/api/v1/labels`: lists every label name, always including `__name__`. */
export async function labelsPromQL(client: RawClient, database: string): Promise<PromQLLabelsResponse> {
  return unwrap(
    client.GET("/api/v1/ts/{database}/prom/api/v1/labels", {
      params: { path: { database } },
    }),
  );
}

/** Executes `GET /api/v1/ts/{database}/prom/api/v1/series`: returns the label sets of series matching the given selectors. */
export async function seriesPromQL(client: RawClient, database: string, opts: PromQLSeriesOptions): Promise<PromQLSeriesResponse> {
  return unwrap(
    client.GET("/api/v1/ts/{database}/prom/api/v1/series", {
      params: { path: { database }, query: opts },
    }),
  );
}
/**
 * Executes `GET /api/v1/ts/{database}/prom/api/v1/label/{name}/values`:
 * lists the values of one label name over the requested time range.
 * Querying '__name__' returns time-series type names.
 */
export async function labelValuesPromQL(
  client: RawClient,
  database: string,
  name: string,
  opts?: PromQLLabelValuesOptions,
): Promise<PromQLLabelsResponse> {
  return unwrap(
    client.GET("/api/v1/ts/{database}/prom/api/v1/label/{name}/values", {
      params: {
        path: { database, name: encodeURIComponent(name) },
        query: opts,
      },
    }),
  );
}
