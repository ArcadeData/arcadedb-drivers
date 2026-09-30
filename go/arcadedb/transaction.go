package arcadedb

import (
	"context"
	"fmt"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

// sessionHeader carries a transaction's session id: in the begin response, and on every
// request that takes part in the transaction.
const sessionHeader = "arcadedb-session-id"

// TxError is returned by Transaction when fn failed AND the rollback that followed also
// failed. Err is the error fn returned; RollbackErr is the rollback's failure.
//
// Unwrap returns only Err, so errors.Is and errors.As see the error the caller's own code
// produced, while the rollback failure stays inspectable on the struct. This is Go's
// analogue of Python's __cause__ and Java's addSuppressed. errors.Join is deliberately not
// used: it unwraps to both errors, so errors.As(err, &arcadeErr) could match the
// rollback's *ArcadeDBError instead of the one fn returned.
type TxError struct {
	Err         error
	RollbackErr error
}

// Error includes both messages.
func (e *TxError) Error() string {
	return fmt.Sprintf("%v (rollback also failed: %v)", e.Err, e.RollbackErr)
}

// Unwrap returns Err only; see TxError.
func (e *TxError) Unwrap() error { return e.Err }

// Transaction runs fn inside a server-side transaction.
//
// It begins a transaction and calls fn with a SECOND *Database carrying the session id.
// Only calls made through that handle take part in the transaction; calls made through
// the outer handle (the receiver) auto-commit individually, exactly as they would outside
// fn.
//
// A callback rather than a Begin()-returning handle because Go has no with or
// try-with-resources: a handle depends on every caller remembering defer tx.Rollback(),
// while a callback makes leaking a session structurally impossible.
//
// The contract has three clauses:
//
//  1. fn returns nil: the transaction is committed and the commit's result returned.
//  2. fn returns an error or panics: the transaction is rolled back, then the error is
//     returned or the panic re-raised with its original value. If that rollback also
//     fails, the result is a *TxError{Err, RollbackErr} whose Unwrap returns only Err, so
//     errors.As finds the caller's error and never the rollback's (which is why
//     errors.Join is not used). On a panic a failed rollback is discarded and the
//     original panic value wins. The re-panic happens in a deferred function, so the
//     re-raised panic's stack trace starts there rather than at the original panic site.
//  3. The commit fails: a best-effort rollback is issued (its own error discarded) so the
//     session is not left for arcadedb.server.httpTxExpireTimeout to reap, then the
//     commit's error is returned.
//
// Both rollbacks run under context.WithoutCancel(ctx): the commonest reason fn fails is
// that ctx was cancelled or timed out, and a rollback bound to that ctx would never reach
// the server. The commit uses ctx itself.
//
// If fn ends its goroutine with runtime.Goexit (t.FailNow in a test, for instance) the
// transaction is rolled back and Goexit continues; it is never mistaken for a nil return
// and never committed.
//
// A begin that answers 2xx without a session id yields an *ArcadeDBError and fn is not
// called. Calling Transaction on the handle fn received sends that handle's session id
// with the begin, so the server refuses the nesting (409) rather than silently opening an
// independent transaction.
func (d *Database) Transaction(ctx context.Context, fn func(tx *Database) error) error {
	sid, err := d.beginTransaction(ctx)
	if err != nil {
		return err
	}
	tx := &Database{srv: d.srv, name: d.name, sessionID: sid}

	// returned distinguishes fn returning from fn panicking or calling runtime.Goexit;
	// in the latter two the deferred function runs with returned still false.
	returned := false
	defer func() {
		if returned {
			return
		}
		r := recover()
		_ = tx.rollbackTransaction(context.WithoutCancel(ctx))
		if r != nil {
			panic(r)
		}
		// r == nil: runtime.Goexit (panic(nil) recovers as *runtime.PanicNilError since
		// Go 1.21). Returning lets the goroutine continue exiting.
	}()
	fnErr := fn(tx)
	returned = true

	if fnErr != nil {
		if rbErr := tx.rollbackTransaction(context.WithoutCancel(ctx)); rbErr != nil {
			return &TxError{Err: fnErr, RollbackErr: rbErr}
		}
		return fnErr
	}
	if err := tx.commitTransaction(ctx); err != nil {
		_ = tx.rollbackTransaction(context.WithoutCancel(ctx))
		return err
	}
	return nil
}

// beginTransaction returns the new transaction's session id. The endpoint answers 204
// with no body and carries the id in the arcadedb-session-id RESPONSE header, which the
// generator exposes as Headers204; a non-204 2xx leaves that nil, so the raw header is
// the fallback.
func (d *Database) beginTransaction(ctx context.Context) (string, error) {
	resp, err := d.srv.raw.BeginTransactionWithResponse(ctx, d.name,
		&generated.BeginTransactionParams{ArcadedbSessionId: d.sessionParam()})
	if err != nil {
		return "", err
	}
	if err := checkResponse(resp.HTTPResponse, resp.Body); err != nil {
		return "", err
	}
	var sid string
	if h := resp.Headers204; h != nil && h.ArcadedbSessionId != nil {
		sid = *h.ArcadedbSessionId
	} else {
		sid = resp.HTTPResponse.Header.Get(sessionHeader)
	}
	if sid == "" {
		return "", &ArcadeDBError{
			Status:       resp.HTTPResponse.StatusCode,
			ErrorMessage: "beginTransaction did not return a session id",
			RequestID:    resp.HTTPResponse.Header.Get(requestIDHeader),
		}
	}
	return sid, nil
}

// commitTransaction commits the transaction d.sessionID identifies. 204, no body.
func (d *Database) commitTransaction(ctx context.Context) error {
	resp, err := d.srv.raw.CommitTransactionWithResponse(ctx, d.name,
		&generated.CommitTransactionParams{ArcadedbSessionId: d.sessionParam()})
	if err != nil {
		return err
	}
	return checkResponse(resp.HTTPResponse, resp.Body)
}

// rollbackTransaction rolls back the transaction d.sessionID identifies. 204, no body.
func (d *Database) rollbackTransaction(ctx context.Context) error {
	resp, err := d.srv.raw.RollbackTransactionWithResponse(ctx, d.name,
		&generated.RollbackTransactionParams{ArcadedbSessionId: d.sessionParam()})
	if err != nil {
		return err
	}
	return checkResponse(resp.HTTPResponse, resp.Body)
}
