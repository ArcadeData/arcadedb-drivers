import type { Client } from "openapi-fetch";
import type { components, paths } from "../generated/schema.js";
import { unwrap } from "../internal/unwrap.js";

/** The unwrapped openapi-fetch client, typed against ArcadeDB's OpenAPI schema. */
type RawClient = Client<paths>;

/**
 * Widens `K` back to optional on `T`, preserving each field's contract-derived type.
 *
 * openapi-typescript emits any property carrying an OpenAPI `default` as REQUIRED on the
 * generated TypeScript type - a codegen artifact of how it reads `default`, not a reflection of
 * the contract's own `required` list. `VectorSearchRequest.k`, `HybridSearchRequest.k`, and
 * `FullTextSearchRequest.limit` all carry `default: 10` and are absent from their schema's
 * `required` array, yet the generated type marks each of them required anyway. This is the same
 * class of artifact `buildCommandBody` in `facade/data.ts` documents for `Record<string, never>`:
 * a known codegen quirk gets a narrow, documented workaround here rather than forcing every
 * caller to pass a value the server would default for them. `Partial<Pick<T, K>>` rather than a
 * hand-written `k?: number` so the field's TYPE still tracks the contract - only its optionality
 * is overridden - if the contract ever retypes it.
 */
type WithOptionalDefaults<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>;

/**
 * Body accepted by `db.vector.search()`. `indexName` and `queryVector` are the contract's only
 * required fields. `k` is typed optional here - unlike the generated `VectorSearchRequest`, where
 * it is required only because it carries `default: 10`; see {@link WithOptionalDefaults}. Omit it
 * and the server applies that default.
 */
export type VectorSearchOptions = WithOptionalDefaults<components["schemas"]["VectorSearchRequest"], "k">;
/**
 * Body accepted by `db.vector.hybrid()`. `vectorIndexName` and `queryVector` are the contract's
 * only required fields. `k` is optional here for the same reason as {@link VectorSearchOptions}'s
 * `k` - the server defaults it to 10 when omitted.
 */
export type HybridSearchOptions = WithOptionalDefaults<components["schemas"]["HybridSearchRequest"], "k">;
/**
 * Body accepted by `db.vector.fulltext()`. `queryText` is the contract's only required field.
 * `limit` is optional here for the same reason as {@link VectorSearchOptions}'s `k` - the server
 * defaults it to 10 when omitted.
 */
export type FullTextSearchOptions = WithOptionalDefaults<components["schemas"]["FullTextSearchRequest"], "limit">;

/**
 * The whole response, not just `results`.
 *
 * `truncated` means the server stopped short of the full candidate set, so `results` is
 * incomplete - the same hazard `QueryEnvelope` documents for `query`. A caller reading only
 * `results` works off a partial answer without being told. That is why these three methods
 * return the response object as the server sent it rather than unwrapping to the rows.
 */
export type VectorSearchResult = components["schemas"]["VectorSearchResponse"];
/** As {@link VectorSearchResult}; also carries `fused`, `fusionStrategy` and the per-leg breakdown. */
export type HybridSearchResult = components["schemas"]["HybridSearchResponse"];
/**
 * As {@link VectorSearchResult}, with one asymmetry worth knowing: `FullTextSearchResponse` has
 * **no `truncated` field** in the contract, while the vector and hybrid responses do. Absence of
 * `truncated` here is the contract's shape, not a server that forgot to send it, so there is no
 * value to default and nothing this client can assert about completeness either way.
 */
export type FullTextSearchResult = components["schemas"]["FullTextSearchResponse"];

/**
 * Executes `POST /api/v1/vector/{database}/search` - kNN over a named vector index.
 *
 * `efSearch` and the result-limit bounds are validated SERVER-side; this client sends what it is
 * given and does not pre-validate, so a rejection for an out-of-range `efSearch` arrives as an
 * `ArcadeDBError` from the server rather than as a local throw.
 *
 * `body` is cast to the generated `VectorSearchRequest`: `opts` (`VectorSearchOptions`) widens `k`
 * back to optional (see {@link WithOptionalDefaults}), so it no longer structurally matches the
 * generated type openapi-fetch expects here. The cast only undoes that codegen artifact - it does
 * not widen `indexName` or `queryVector`, so removing either from the contract still fails `tsc`
 * here rather than only failing on the wire.
 */
export async function vectorSearch(client: RawClient, database: string, opts: VectorSearchOptions): Promise<VectorSearchResult> {
  return unwrap(
    client.POST("/api/v1/vector/{database}/search", {
      params: { path: { database } },
      body: opts as components["schemas"]["VectorSearchRequest"],
    }),
  );
}

/**
 * Executes `POST /api/v1/vector/{database}/hybrid` - combined vector and full-text retrieval.
 * Bounds are server-validated; see {@link vectorSearch}. `body` is cast for the same reason as
 * {@link vectorSearch}'s: `opts` widens `k` back to optional.
 */
export async function hybridSearch(client: RawClient, database: string, opts: HybridSearchOptions): Promise<HybridSearchResult> {
  return unwrap(
    client.POST("/api/v1/vector/{database}/hybrid", {
      params: { path: { database } },
      body: opts as components["schemas"]["HybridSearchRequest"],
    }),
  );
}

/**
 * Executes `POST /api/v1/vector/{database}/fulltext`. Bounds are server-validated; see
 * {@link vectorSearch}. `body` is cast for the same reason as {@link vectorSearch}'s: `opts`
 * widens `limit` back to optional.
 */
export async function fullTextSearch(client: RawClient, database: string, opts: FullTextSearchOptions): Promise<FullTextSearchResult> {
  return unwrap(
    client.POST("/api/v1/vector/{database}/fulltext", {
      params: { path: { database } },
      body: opts as components["schemas"]["FullTextSearchRequest"],
    }),
  );
}
