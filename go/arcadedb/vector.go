package arcadedb

import (
	"context"
	"errors"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

// Vector is the vector namespace of a Database: kNN vector search, fused hybrid search
// and full-text search. Obtain it with Database.Vector.
//
// Each method takes the generated request struct and returns the whole generated
// response, never unwrapped to Results. VectorSearchResponse and HybridSearchResponse
// carry Truncated, and a caller reading only the rows would silently work off a partial
// answer if that field were dropped (the same hazard QueryEnvelope documents for Query
// and Command). FullTextSearchResponse carries no Truncated at all, because full-text
// search has no candidate window to overflow; that asymmetry is left as it is rather than
// papered over with a uniform shape.
//
// Truncated on VectorSearchResponse and HybridSearchResponse is a plain bool in the
// generated model, so a response that omits "truncated" decodes as false, the most
// reassuring reading of "the server did not say". The contract marks the field required
// and today's server always sends it, but the generated model cannot tell an omitted
// field from false. Truncated == false is therefore only as good as the server's promise,
// not proof that the result is complete.
//
// Results stay the generated per-hit structs (Rid, Properties, Distance or Score), not
// the []map[string]any rows QueryEnvelope produces. That is a real difference in row
// shape, not an oversight: flattening only the hits would manufacture a third, hybrid
// shape, typed top-level fields next to untyped rows, and would detach Truncated, Count
// and Scoring from the rows they describe.
//
// K (search, hybrid) and Limit (full-text) are pointers and stay nil unless the caller
// sets them: the server applies its own default of 10 when the field is absent from the
// body, so restating that number client-side would be a second, driftable copy of it.
//
// Every call sends the session header when the Database is inside a Transaction.
type Vector struct {
	db *Database
}

// Vector returns the vector namespace. It performs no request.
func (d *Database) Vector() *Vector { return &Vector{db: d} }

var errEmptySearchBody = errors.New("arcadedb: search response had an empty body")

// Search runs a kNN search over a dense (LSM_VECTOR) or sparse (LSM_SPARSE_VECTOR) index.
// Dense hits carry Distance (lower is better); sparse hits carry Score (higher is
// better), and Scoring on the response names which. A filtered search inspects a bounded
// candidate window reported as CandidateLimit, so Truncated means the window was filled
// and more matches may exist: raise K to see them.
func (v *Vector) Search(ctx context.Context, req generated.VectorSearchRequest) (*generated.VectorSearchResponse, error) {
	resp, err := v.db.srv.raw.VectorSearchWithResponse(ctx, v.db.name,
		&generated.VectorSearchParams{ArcadedbSessionId: v.db.sessionParam()}, req)
	if err != nil {
		return nil, err
	}
	if err := checkResponse(resp.HTTPResponse, resp.Body); err != nil {
		return nil, err
	}
	return nonEmpty(decodeBody(resp.JSON200, resp.Body))
}

// Hybrid runs a fused vector, full-text and graph-expansion search. FulltextQuery and
// FulltextIndexName go together: the server refuses half a leg rather than dropping it.
// Fused on the response is false when only one leg produced rows (fusion needs two
// sources), in which case the hits carry that leg's native distance or score.
func (v *Vector) Hybrid(ctx context.Context, req generated.HybridSearchRequest) (*generated.HybridSearchResponse, error) {
	resp, err := v.db.srv.raw.HybridSearchWithResponse(ctx, v.db.name,
		&generated.HybridSearchParams{ArcadedbSessionId: v.db.sessionParam()}, req)
	if err != nil {
		return nil, err
	}
	if err := checkResponse(resp.HTTPResponse, resp.Body); err != nil {
		return nil, err
	}
	return nonEmpty(decodeBody(resp.JSON200, resp.Body))
}

// Fulltext runs a full-text search over a FULL_TEXT index. IndexName wins over TypeName
// when both are set; TypeName alone works only for a type with exactly one full-text
// index. The response has no Truncated: full-text search has no bounded candidate window.
func (v *Vector) Fulltext(ctx context.Context, req generated.FullTextSearchRequest) (*generated.FullTextSearchResponse, error) {
	resp, err := v.db.srv.raw.FullTextSearchWithResponse(ctx, v.db.name,
		&generated.FullTextSearchParams{ArcadedbSessionId: v.db.sessionParam()}, req)
	if err != nil {
		return nil, err
	}
	if err := checkResponse(resp.HTTPResponse, resp.Body); err != nil {
		return nil, err
	}
	return nonEmpty(decodeBody(resp.JSON200, resp.Body))
}

// nonEmpty turns a nil decoded body into an error: a search that succeeded with no body
// has no answer to give, and (nil, nil) would read as "no results".
func nonEmpty[T any](r *T, err error) (*T, error) {
	if err != nil {
		return nil, err
	}
	if r == nil {
		return nil, errEmptySearchBody
	}
	return r, nil
}
