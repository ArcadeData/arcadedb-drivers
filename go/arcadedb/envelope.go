package arcadedb

import (
	"encoding/json"
	"fmt"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

// QueryLanguage names a query language the server accepts in the "language" field of a
// query or command request.
type QueryLanguage string

// The languages the server accepts. Each constant's value is the exact string sent in the
// request's "language" field; a language the server does not have enabled is refused by the
// server, not by this client. QueryLanguage is a plain string type, so any other value the
// server understands can be passed as QueryLanguage("...").
const (
	SQL QueryLanguage = "sql"
	// SQLScript runs several SQL statements, separated by ";", as one script.
	SQLScript QueryLanguage = "sqlscript"
	Cypher    QueryLanguage = "cypher"
	Gremlin   QueryLanguage = "gremlin"
	GraphQL   QueryLanguage = "graphql"
	Mongo     QueryLanguage = "mongo"
)

// QueryEnvelope is the whole result envelope Query and Command return, not just the rows.
//
// Truncated means the serializer's row cap stopped mid-serialization with rows still
// pending, so Result is incomplete: a caller that reads Result and ignores Truncated can
// silently work off a partial answer.
//
// The contract marks limit, returned and truncated required, so a conforming server always
// sends them; result is optional. Each field still takes a default when a server omits it
// anyway: an empty (non-nil) slice, -1 (uncapped), 0 and false. Those defaults are the most
// reassuring possible reading of "the server did not say": they assert a completeness the
// server never claimed, so against a server that breaks the contract by omitting truncated,
// Truncated == false is no proof of completeness. The generated model is not returned
// instead because it cannot tell an omitted field from a zero one, and a pointer-typed
// model would leave callers one careless dereference from a panic.
//
// Result's rows are decoded with encoding/json, so every number is a float64 and an integer
// above 2^53 loses precision.
//
// Explain and ExplainPlan carry the execution plan of an EXPLAIN or PROFILE statement, or
// of any statement run with profileExecution: Explain as indented text, one line per step,
// and ExplainPlan as the same plan in structured form. The server sends both or neither.
// When they are present Result is empty and Returned is 0, because the plan is the answer
// and is not repeated as a row, so an empty Result there does not mean "no rows matched".
// They are plain values rather than pointers for the reason the other fields are: Explain
// is "" and ExplainPlan nil when the server sent no plan, and a real plan is never empty.
type QueryEnvelope struct {
	Result      []map[string]any
	Limit       int
	Returned    int
	Truncated   bool
	Explain     string
	ExplainPlan map[string]any
}

// QueryOption tunes a Query or QueryStream call. WithLimit and WithQueryTag are QueryOptions.
//
// QueryOption, CommandOption and TransactionOption are sealed interfaces rather than one
// func type so that an option goes only where it means something: WithQueryTag is all
// three, WithLimit is a QueryOption and a CommandOption, and passing it to Transaction does
// not compile.
type QueryOption interface{ applyQuery(*callOptions) }

// CommandOption tunes a Command or CommandStream call. WithLimit and WithQueryTag are
// CommandOptions.
type CommandOption interface{ applyCommand(*callOptions) }

// TransactionOption tunes a Transaction call. WithQueryTag and WithIsolationLevel are
// TransactionOptions.
type TransactionOption interface{ applyTransaction(*callOptions) }

type callOptions struct {
	limit     *int
	queryTag  string
	isolation *IsolationLevel // nil when WithIsolationLevel was not given, so "" is refused
}

// LimitOption is what WithLimit returns: a QueryOption and a CommandOption at once.
type LimitOption struct{ n int }

func (l LimitOption) applyQuery(o *callOptions)   { n := l.n; o.limit = &n }
func (l LimitOption) applyCommand(o *callOptions) { n := l.n; o.limit = &n }

// WithLimit caps the rows the server serializes into the response; -1 means no cap. Left
// unset, a LIMIT stated by the statement is honoured and only one stating none is capped
// by the server default. It applies to Query, QueryStream, Command and CommandStream. Up
// to 0.3.0 it returned a QueryOption and Command did not accept it, so a command result
// past the server default came back truncated with no way to lift the cap (issue #151).
func WithLimit(n int) LimitOption { return LimitOption{n: n} }

// QueryTagOption is what WithQueryTag returns: a QueryOption, a CommandOption and a
// TransactionOption at once.
type QueryTagOption struct{ tag string }

func (q QueryTagOption) applyQuery(o *callOptions)       { o.queryTag = q.tag }
func (q QueryTagOption) applyCommand(o *callOptions)     { o.queryTag = q.tag }
func (q QueryTagOption) applyTransaction(o *callOptions) { o.queryTag = q.tag }

// WithQueryTag labels the work a call runs with the X-ArcadeDB-Query-Tag request header: an
// opaque label the server lists under `list queries` and that `terminate queries tag
// <label>` stops. It applies to Query, QueryStream, Command, CommandStream and Transaction.
// An empty tag sends no header. (BatchLoad and BatchLoadStream take the tag through
// generated.ExecuteBatchParams.XArcadeDBQueryTag instead, beside the endpoint's other
// options.)
//
// On Transaction the tag is sent with the begin request only, never with the commit or
// rollback and never repeated on the statements fn runs: the server labels every statement
// of the transaction session that carries no tag of its own with it. A statement inside fn
// passed its own WithQueryTag still sends that one, and the server uses it instead.
//
// The tag is not validated here. The contract allows at most 256 printable characters, but
// that is the server's rule and it is not enforced by a refusal callers can count on (a
// 26.11.1-SNAPSHOT server accepted 257); repeating it client-side would only drift from the
// server's the first time it changes.
func WithQueryTag(tag string) QueryTagOption { return QueryTagOption{tag: tag} }

// queryTagParam returns the header value for a generated params struct, or nil when no
// tag (or an empty one) was given, so no header is sent.
func queryTagParam(tag string) *string {
	if tag == "" {
		return nil
	}
	return &tag
}

func queryCallOptions(opts []QueryOption) callOptions {
	var o callOptions
	for _, opt := range opts {
		opt.applyQuery(&o)
	}
	return o
}

func commandCallOptions(opts []CommandOption) callOptions {
	var o callOptions
	for _, opt := range opts {
		opt.applyCommand(&o)
	}
	return o
}

// buildQueryRequest never sets Serializer: the server then picks the record serializer,
// which is the only one whose result QueryEnvelope can represent.
func buildQueryRequest(lang QueryLanguage, command string, params map[string]any, o callOptions) generated.QueryRequest {
	l := string(lang)
	req := generated.QueryRequest{Command: command, Language: &l, Limit: o.limit}
	if params != nil {
		req.Params = &params
	}
	return req
}

func buildCommandRequest(lang QueryLanguage, command string, params map[string]any, o callOptions) generated.CommandRequest {
	req := generated.CommandRequest{Command: command, Language: string(lang), Limit: o.limit}
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
	if qr.Explain != nil {
		env.Explain = *qr.Explain
	}
	if qr.ExplainPlan != nil {
		env.ExplainPlan = *qr.ExplainPlan
	}
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
