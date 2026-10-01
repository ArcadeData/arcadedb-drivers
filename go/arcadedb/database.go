package arcadedb

import (
	"context"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

// Database is a handle on one database of a Server. Obtain it with Server.DB; it holds no
// connection of its own.
type Database struct {
	srv       *Server
	name      string
	sessionID string
}

// Name returns the database name.
func (d *Database) Name() string { return d.name }

// sessionParam returns the arcadedb-session-id value for generated calls, or nil outside
// a transaction.
func (d *Database) sessionParam() *string {
	if d.sessionID == "" {
		return nil
	}
	s := d.sessionID
	return &s
}

// Query runs a read-oriented statement and returns the whole result envelope. Outside a
// Transaction it sends no session header. See QueryEnvelope for why Truncated matters.
func (d *Database) Query(ctx context.Context, lang QueryLanguage, command string, params map[string]any, opts ...QueryOption) (QueryEnvelope, error) {
	resp, err := d.srv.raw.ExecuteQueryPostWithResponse(ctx, d.name,
		&generated.ExecuteQueryPostParams{ArcadedbSessionId: d.sessionParam()},
		buildQueryRequest(lang, command, params, opts...))
	if err != nil {
		return QueryEnvelope{}, err
	}
	if err := checkResponse(resp.HTTPResponse, resp.Body); err != nil {
		return QueryEnvelope{}, err
	}
	return envelopeFromBody(resp.JSON200, resp.Body)
}

// Command runs a statement that may change data. It never sends a row limit; use Query
// with WithLimit to cap a read.
func (d *Database) Command(ctx context.Context, lang QueryLanguage, command string, params map[string]any) (QueryEnvelope, error) {
	resp, err := d.srv.raw.ExecuteCommandWithResponse(ctx, d.name,
		&generated.ExecuteCommandParams{ArcadedbSessionId: d.sessionParam()},
		buildCommandRequest(lang, command, params))
	if err != nil {
		return QueryEnvelope{}, err
	}
	if err := checkResponse(resp.HTTPResponse, resp.Body); err != nil {
		return QueryEnvelope{}, err
	}
	return envelopeFromBody(resp.JSON200, resp.Body)
}
