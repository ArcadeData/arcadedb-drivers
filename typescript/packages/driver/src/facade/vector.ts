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
 * The graph-expansion leg of `db.vector.hybrid()` - `HybridSearchRequest.expand` widened the same
 * way {@link WithOptionalDefaults} widens a top-level field, except `maxDepth` sits one level
 * inside `expand`, so applying {@link WithOptionalDefaults} to `HybridSearchRequest` itself (as
 * {@link HybridSearchOptions} does for `k`) does not reach it - that application only widens
 * `HybridSearchRequest`'s own top-level properties, and `expand` is one of those properties, not a
 * property of it. Applying {@link WithOptionalDefaults} again, to the `expand` object type itself,
 * is what reaches `maxDepth`.
 */
type HybridSearchExpand = WithOptionalDefaults<NonNullable<components["schemas"]["HybridSearchRequest"]["expand"]>, "maxDepth">;

/**
 * Body accepted by `db.vector.hybrid()`. `vectorIndexName` and `queryVector` are the contract's
 * only required fields. `k` is optional here for the same reason as {@link VectorSearchOptions}'s
 * `k` - the server defaults it to 10 when omitted. `expand.maxDepth` is optional for the same
 * reason, one level down; see {@link HybridSearchExpand}.
 *
 * `weights` is widened from the generated `Record<string, never>`: the contract declares it as a
 * bare `{"type": "object"}` with no properties, which openapi-typescript renders as "no property
 * may ever hold a value" - a caller cannot populate the field at all. `Record<string, number>` is
 * the real constraint the generated emptiness could not carry - the contract's own description
 * says the values are numbers, that only `vector`, `fulltext` and `expand` are accepted as keys,
 * and that a weight for a leg the request does not otherwise ask for is refused rather than
 * ignored. That last part is server-validated, not local: this type does not narrow the key set to
 * those three, both because the contract does not declare them as named properties and because
 * this facade does not invent a shape the contract has not committed to (the same reasoning
 * `buildCommandBody` in `facade/data.ts` documents for its own `Record<string, never>` widening).
 *
 * With `k`, `expand.maxDepth` and `weights` handled, every `default`-forced-required property and
 * every untyped-object property across `VectorSearchRequest`, `HybridSearchRequest` and
 * `FullTextSearchRequest` is accounted for - this is the last one. A future contract change that
 * adds another `default` or another bare `{"type": "object"}` to one of these three schemas will
 * need the same treatment; nothing here detects that automatically.
 */
export type HybridSearchOptions = Omit<WithOptionalDefaults<components["schemas"]["HybridSearchRequest"], "k">, "weights" | "expand"> & {
  weights?: Record<string, number>;
  expand?: HybridSearchExpand;
};

/**
 * Body accepted by `db.vector.fulltext()`. `queryText` is the contract's only required field.
 * `limit` is optional here for the same reason as {@link VectorSearchOptions}'s `k` - the server
 * defaults it to 10 when omitted.
 */
export type FullTextSearchOptions = WithOptionalDefaults<components["schemas"]["FullTextSearchRequest"], "limit">;

/**
 * Retypes a hit's `properties` on a vector/hybrid/full-text search response; every other field -
 * `results` itself included - keeps exactly the type `R` gives it.
 *
 * `VectorSearchResponse`, `HybridSearchResponse` and `FullTextSearchResponse` all carry no
 * `required` list in the contract, and each hit's `properties` is a bare `{"type": "object"}` with
 * no declared keys, which openapi-typescript renders as `Record<string, never>` - the same
 * "untyped object" artifact `HybridSearchOptions.weights` documents above, but read coming back
 * rather than sent going out. Every value of an empty record is typed `never`, and `never` is
 * assignable to everything, so the generated shape let `hit.properties.name` compile as any type
 * at all and hand back whatever the server actually sent - a silent failure, not a refusal to
 * compile.
 *
 * `T` defaults to `Record<string, unknown>` and that default, not the generic parameter itself, is
 * what closes the hazard. With it, `hit.properties.name` reads as `unknown`, so
 * `const score: number = hit.properties.name` stops compiling for every caller of
 * `db.vector.search` / `.hybrid` / `.fulltext` - nobody has to opt in for the unchecked read to
 * start failing. A caller who does know their row shape can still pass it -
 * `db.vector.search<{ name: string }>(...)` - and get `hit.properties.name: string` for real; the
 * default only means that passing nothing is no longer unsound.
 */
type WithTypedProperties<R extends { results?: readonly { properties?: unknown }[] }, T> = Omit<R, "results"> & {
  results?: (Omit<NonNullable<R["results"]>[number], "properties"> & { properties?: T })[];
};

/**
 * The whole response, not just `results` - and, within a hit, every field but `properties`.
 *
 * `truncated` means the server stopped short of the full candidate set, so `results` is
 * incomplete - the same hazard `QueryEnvelope` documents for `query`. A caller reading only
 * `results` works off a partial answer without being told. That is why these three methods
 * return the response object as the server sent it rather than unwrapping to the rows.
 *
 * `T`, a hit's `properties` type, defaults to `Record<string, unknown>`; see
 * {@link WithTypedProperties} for why that default - not the generic parameter - is what makes an
 * unchecked property read fail to compile, and how to pass a real row type instead.
 */
export type VectorSearchResult<T = Record<string, unknown>> = WithTypedProperties<components["schemas"]["VectorSearchResponse"], T>;
/** As {@link VectorSearchResult}; also carries `fused`, `fusionStrategy` and the per-leg breakdown. */
export type HybridSearchResult<T = Record<string, unknown>> = WithTypedProperties<components["schemas"]["HybridSearchResponse"], T>;
/**
 * As {@link VectorSearchResult}, with one asymmetry worth knowing: `FullTextSearchResponse` has
 * **no `truncated` field** in the contract, while the vector and hybrid responses do. Absence of
 * `truncated` here is the contract's shape, not a server that forgot to send it, so there is no
 * value to default and nothing this client can assert about completeness either way.
 */
export type FullTextSearchResult<T = Record<string, unknown>> = WithTypedProperties<components["schemas"]["FullTextSearchResponse"], T>;

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
 *
 * `T`, forwarded to {@link VectorSearchResult}, types a hit's `properties`; see
 * {@link WithTypedProperties}. The return value is cast to `Promise<VectorSearchResult<T>>` because
 * `T` is opaque inside this function body - nothing here narrows the server's actual JSON to `T`,
 * the caller's annotation is trusted the same way `db.query<T>()`'s is.
 */
export async function vectorSearch<T = Record<string, unknown>>(
  client: RawClient,
  database: string,
  opts: VectorSearchOptions,
): Promise<VectorSearchResult<T>> {
  return unwrap(
    client.POST("/api/v1/vector/{database}/search", {
      params: { path: { database } },
      body: opts as components["schemas"]["VectorSearchRequest"],
    }),
  ) as Promise<VectorSearchResult<T>>;
}

/**
 * Executes `POST /api/v1/vector/{database}/hybrid` - combined vector and full-text retrieval.
 * Bounds are server-validated; see {@link vectorSearch}. `body` is cast because `opts`
 * (`HybridSearchOptions`) widens the generated `HybridSearchRequest` in three places that no
 * longer structurally match it: `k` back to optional, same as {@link vectorSearch}'s cast;
 * `expand.maxDepth` back to optional, one level down (see {@link HybridSearchExpand}); and
 * `weights` from the uninhabitable generated `Record<string, never>` to `Record<string, number>`.
 * As with {@link vectorSearch}, the cast only undoes those three codegen artifacts - it does not
 * touch `vectorIndexName` or `queryVector`, so removing either from the contract still fails `tsc`
 * here rather than only failing on the wire.
 *
 * `T` types a hit's `properties`, forwarded to {@link HybridSearchResult}; see
 * {@link vectorSearch}'s doc comment for why the return value needs its own cast.
 */
export async function hybridSearch<T = Record<string, unknown>>(
  client: RawClient,
  database: string,
  opts: HybridSearchOptions,
): Promise<HybridSearchResult<T>> {
  return unwrap(
    client.POST("/api/v1/vector/{database}/hybrid", {
      params: { path: { database } },
      body: opts as components["schemas"]["HybridSearchRequest"],
    }),
  ) as Promise<HybridSearchResult<T>>;
}

/**
 * Executes `POST /api/v1/vector/{database}/fulltext`. Bounds are server-validated; see
 * {@link vectorSearch}. `body` is cast for the same reason as {@link vectorSearch}'s: `opts`
 * widens `limit` back to optional.
 *
 * `T` types a hit's `properties`, forwarded to {@link FullTextSearchResult}; see
 * {@link vectorSearch}'s doc comment for why the return value needs its own cast.
 */
export async function fullTextSearch<T = Record<string, unknown>>(
  client: RawClient,
  database: string,
  opts: FullTextSearchOptions,
): Promise<FullTextSearchResult<T>> {
  return unwrap(
    client.POST("/api/v1/vector/{database}/fulltext", {
      params: { path: { database } },
      body: opts as components["schemas"]["FullTextSearchRequest"],
    }),
  ) as Promise<FullTextSearchResult<T>>;
}
