package arcadedb

import (
	"encoding/json"
	"fmt"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

// QueryLanguage names a query language the server accepts in the "language" field of a
// query or command request.
type QueryLanguage string

const (
	SQL     QueryLanguage = "sql"
	Cypher  QueryLanguage = "cypher"
	Gremlin QueryLanguage = "gremlin"
	GraphQL QueryLanguage = "graphql"
	Mongo   QueryLanguage = "mongo"
)

// QueryEnvelope is the whole result envelope Query and Command return, not just the rows.
//
// Truncated means the serializer's row cap stopped mid-serialization with rows still
// pending, so Result is incomplete: a caller that reads Result and ignores Truncated can
// silently work off a partial answer.
//
// Result, Limit, Returned and Truncated each take a default when the server omits them:
// an empty (non-nil) slice, -1 (uncapped), 0 and false. Those defaults are the most
// reassuring possible reading of "the server did not say": they assert a completeness the
// server never claimed. Today's server always sends all four, but that is a property of
// the implementation, not a guarantee the type enforces, so do not read Truncated == false
// as proof of completeness when the server may have omitted it. The generated model is not
// returned instead because it cannot tell an omitted field from a zero one, and a
// pointer-typed model would leave callers one careless dereference from a panic.
type QueryEnvelope struct {
	Result    []map[string]any
	Limit     int
	Returned  int
	Truncated bool
}

// QueryOption tunes a Query call.
type QueryOption func(*queryOptions)

type queryOptions struct {
	limit *int
}

// WithLimit caps the rows the server serializes into the response; -1 means no cap. Left
// unset, a LIMIT stated by the query is honoured and only a query stating none is capped
// by the server default. Command does not accept it.
func WithLimit(n int) QueryOption {
	return func(o *queryOptions) { o.limit = &n }
}

// buildQueryRequest never sets Serializer: the server then picks the record serializer,
// which is the only one whose result QueryEnvelope can represent.
func buildQueryRequest(lang QueryLanguage, command string, params map[string]any, opts ...QueryOption) generated.QueryRequest {
	var o queryOptions
	for _, opt := range opts {
		opt(&o)
	}
	l := string(lang)
	req := generated.QueryRequest{Command: command, Language: &l, Limit: o.limit}
	if params != nil {
		req.Params = &params
	}
	return req
}

// buildCommandRequest deliberately has no limit parameter, as in the other drivers.
func buildCommandRequest(lang QueryLanguage, command string, params map[string]any) generated.CommandRequest {
	req := generated.CommandRequest{Command: command, Language: string(lang)}
	if params != nil {
		req.Params = &params
	}
	return req
}

// toEnvelope converts a parsed response into the public envelope, flattening the result
// union. A graph-serializer result ({vertices, edges}) cannot be represented and is
// rejected as *ArcadeDBError with status 200: the server answered in a shape this client
// cannot model, and callers already catch *ArcadeDBError around Query and Command. It
// cannot arrive today because no request sets a serializer, but that is a property of the
// request builder, not of the contract. Defaults for omitted fields are applied by
// envelopeFromBody, which can see which keys were present.
func toEnvelope(qr *generated.QueryResponse) (QueryEnvelope, error) {
	env := QueryEnvelope{Result: []map[string]any{}, Limit: qr.Limit, Returned: qr.Returned, Truncated: qr.Truncated}
	if qr.Result == nil {
		return env, nil
	}
	rows, err := qr.Result.AsQueryResponseResult0()
	if err != nil {
		if _, gerr := qr.Result.AsQueryResponseResult1(); gerr == nil {
			return QueryEnvelope{}, &ArcadeDBError{
				Status:       200,
				ErrorMessage: "the server answered with a graph-serializer result object, but this call expected rows",
				Detail:       "QueryResponse.result is {vertices, edges}, which QueryEnvelope cannot represent. This client never asks for a graph serializer.",
			}
		}
		return QueryEnvelope{}, fmt.Errorf("arcadedb: decode result rows: %w", err)
	}
	if rows != nil {
		env.Result = rows
	}
	return env, nil
}

// envelopeFromBody builds the envelope from a checked response. The generated model types
// limit, returned and truncated as plain values, so an omitted key is indistinguishable
// from a zero; the raw body is probed for key presence to apply the documented defaults.
func envelopeFromBody(typed *generated.QueryResponse, body []byte) (QueryEnvelope, error) {
	qr, err := decodeBody(typed, body)
	if err != nil {
		return QueryEnvelope{}, err
	}
	if qr == nil {
		return QueryEnvelope{Result: []map[string]any{}, Limit: -1}, nil
	}
	env, err := toEnvelope(qr)
	if err != nil {
		return QueryEnvelope{}, err
	}
	var present map[string]json.RawMessage
	_ = json.Unmarshal(body, &present)
	if _, ok := present["limit"]; !ok {
		env.Limit = -1
	}
	return env, nil
}
