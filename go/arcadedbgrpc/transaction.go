package arcadedbgrpc

import (
	"context"
	"errors"
	"fmt"
	"iter"
	"strings"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc/generated"
	"google.golang.org/grpc"
	"google.golang.org/protobuf/proto"
)

// errPanicNilOrGoexit is what Transaction returns when fn neither returned nor panicked
// with a recoverable value: panic(nil) under GODEBUG=panicnil=1.
var errPanicNilOrGoexit = errors.New("arcadedbgrpc: transaction callback panicked with nil or exited; rolled back")

// TxError is returned by Transaction when fn failed AND the rollback that followed also
// failed. Err is the error fn returned; RollbackErr is the rollback's failure.
//
// Unwrap returns only Err, so errors.Is, errors.As and status.Code see the error the
// caller's own code produced, while the rollback failure stays inspectable on the struct.
// errors.Join is deliberately not used: it unwraps to both errors, so status.Code or
// errors.As could match the rollback's status error instead of the one fn returned.
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

// Transaction runs fn inside a server-side transaction on database.
//
// It calls BeginTransaction and hands fn a *TxHandle bound to the transaction id the
// server returned. Only calls made through that handle take part in the transaction;
// calls made through c, or through c.Raw(), run outside it, exactly as they would outside
// fn. A blank transaction id is ErrNoTransactionID, returned before fn runs.
//
// A callback rather than a Begin()-returning handle because Go has no with or
// try-with-resources: a handle depends on every caller remembering to end it on every
// path, which is the leaked-transaction footgun (ArcadeData/arcadedb#5042), while a
// callback makes it structurally impossible.
//
// The contract has three clauses, as in the Go HTTP client:
//
//  1. fn returns nil: the transaction is committed with CommitTransaction.
//  2. fn returns an error or panics: the transaction is rolled back, then the error is
//     returned or the panic re-raised with its original value. If that rollback also
//     fails, the result is a *TxError{Err, RollbackErr} whose Unwrap returns only Err.
//     On a panic a failed rollback is discarded and the original panic value wins. The
//     re-panic happens in a deferred function, so its stack trace starts there.
//  3. The commit fails: a best-effort rollback is issued (its own error discarded) so the
//     server does not hold the transaction until it reaps it, then the commit's status
//     error is returned unwrapped.
//
// A fourth case is ported from the Python client: a commit that answers committed=false
// with no error status, which is how the server answers a commit for a transaction it
// has already reaped (success=true, committed=false). Transaction returns an error
// wrapping ErrNotCommitted and carrying the server's message; reporting success would
// silently lose fn's writes. The check reads committed, not success. No rollback follows,
// since there is no live transaction left to roll back.
//
// Both rollbacks run under context.WithoutCancel(ctx): the commonest reason fn fails is
// that ctx was cancelled or timed out, and a rollback bound to that ctx would never reach
// the server. The commit uses ctx itself.
//
// If fn ends its goroutine with runtime.Goexit (t.FailNow in a test, for instance) the
// transaction is rolled back and Goexit continues; it is never mistaken for a nil return
// and never committed. panic(nil) is re-raised as the *runtime.PanicNilError it recovers
// as by default; under GODEBUG=panicnil=1 it recovers as nil, which cannot be told apart
// from Goexit, so Transaction rolls back and returns a non-nil error rather than nil,
// which would read as committed.
//
// RPC failures, from BeginTransaction, CommitTransaction or a handle call fn returns, are
// grpc-go status errors, unwrapped.
func (c *Client) Transaction(ctx context.Context, database string, fn func(tx *TxHandle) error) (err error) {
	begun, err := c.raw.BeginTransaction(ctx, &generated.BeginTransactionRequest{Database: database})
	if err != nil {
		return err
	}
	id := begun.GetTransactionId()
	if strings.TrimSpace(id) == "" {
		return fmt.Errorf("%w for database %q: refusing to run the callback outside a real transaction",
			ErrNoTransactionID, database)
	}
	tx := &TxHandle{raw: c.raw, database: database, id: id}

	// returned distinguishes fn returning from fn panicking or calling runtime.Goexit;
	// in the latter two the deferred function runs with returned still false.
	returned := false
	defer func() {
		if returned {
			return
		}
		r := recover()
		_ = tx.rollback(context.WithoutCancel(ctx))
		if r != nil {
			panic(r)
		}
		// r == nil: runtime.Goexit, or panic(nil) under GODEBUG=panicnil=1 (by default it
		// recovers as *runtime.PanicNilError and is re-raised above). For Goexit the
		// goroutine continues exiting and the result is never seen; for panic(nil) the
		// call returns, and it must not return nil, which would read as committed.
		err = errPanicNilOrGoexit
	}()
	fnErr := fn(tx)
	returned = true

	if fnErr != nil {
		if rbErr := tx.rollback(context.WithoutCancel(ctx)); rbErr != nil {
			return &TxError{Err: fnErr, RollbackErr: rbErr}
		}
		return fnErr
	}
	committed, err := c.raw.CommitTransaction(ctx, &generated.CommitTransactionRequest{Transaction: tx.txContext()})
	if err != nil {
		_ = tx.rollback(context.WithoutCancel(ctx))
		return err
	}
	if !committed.GetCommitted() {
		msg := committed.GetMessage()
		if msg == "" {
			msg = "no message from server"
		}
		return fmt.Errorf("%w: commit for database %q (transaction_id=%s) did not take effect: %s",
			ErrNotCommitted, database, id, msg)
	}
	return nil
}

// TxHandle is the handle Transaction passes to its callback. Every call made through it
// carries the transaction's id; calls through the Client or Client.Raw() do not.
//
// Each method takes the generated request and sends a COPY of it, with Database forced to
// the transaction's database and the whole Transaction field REPLACED by
// TransactionContext{TransactionId, Database}. The override is the mechanism that makes
// ArcadeData/arcadedb#5040 (transaction hijack) unrepeatable through this handle: a
// request that arrived naming another database, or carrying another transaction id, leaves
// naming this one. It is a replace, never a merge, so inline begin, commit, rollback,
// read_only or timeout_ms values the caller set are wiped rather than riding into a call
// whose transaction this handle controls; the inline model stays reachable through
// Client.Raw().
//
// The caller's message is never mutated. Binding in place would leave the caller's request
// carrying this transaction's id after the transaction ended, and reusing it, through
// Client.Raw() or in a later transaction, would send that dead id to the server: #5040's
// shape reached by aliasing, in the type built to prevent it.
//
// A request's own Credentials field, where it has one, is passed through as given, never
// bound: which principal may act inside the transaction is the server's to decide.
//
// InsertStream and TimeSeriesWriteStream are deliberately absent, as in the Python client.
// InsertStream on the handle is pending ArcadeData/arcadedb-drivers#46 (the server fix,
// ArcadeData/arcadedb#6607, shipped in 26.9.1); TimeSeriesWriteChunk has no transaction
// field, so a write stream cannot join a transaction at all. Reach either through the
// Client, outside any transaction.
//
// A handle outlives nothing useful: once Transaction returns, its calls carry an id the
// server has committed or rolled back, and the server refuses them. Do not retain it.
type TxHandle struct {
	raw      generated.ArcadeDbServiceClient
	database string
	id       string
}

// txContext returns a fresh TransactionContext naming only this transaction: its id and
// database, every inline flag at its zero value.
func (h *TxHandle) txContext() *generated.TransactionContext {
	return &generated.TransactionContext{TransactionId: h.id, Database: h.database}
}

// binding returns the two values every bound request gets: Database, and a fresh
// Transaction (see txContext). Each method assigns both on its own clone in one statement.
func (h *TxHandle) binding() (string, *generated.TransactionContext) {
	return h.database, h.txContext()
}

func (h *TxHandle) rollback(ctx context.Context) error {
	_, err := h.raw.RollbackTransaction(ctx, &generated.RollbackTransactionRequest{Transaction: h.txContext()})
	return err
}

// clone returns a deep copy of req for binding. A nil request becomes an empty message of
// the same type, so it is still bound rather than sent with no transaction.
//
// The per-method assignment that follows is plain typed Go rather than a protoreflect
// setter: if a regenerated contract renamed or dropped Database or Transaction on one of
// the bound types, the build would fail instead of a call panicking, or worse, being sent
// unbound.
func clone[T proto.Message](req T) T {
	m := req.ProtoReflect()
	if !m.IsValid() {
		return m.Type().New().Interface().(T)
	}
	return proto.Clone(req).(T)
}

// ExecuteQuery is ArcadeDbService.ExecuteQuery, bound to the transaction.
func (h *TxHandle) ExecuteQuery(ctx context.Context, req *generated.ExecuteQueryRequest, opts ...grpc.CallOption) (*generated.ExecuteQueryResponse, error) {
	r := clone(req)
	r.Database, r.Transaction = h.binding()
	return h.raw.ExecuteQuery(ctx, r, opts...)
}

// ExecuteCommand is ArcadeDbService.ExecuteCommand, bound to the transaction.
func (h *TxHandle) ExecuteCommand(ctx context.Context, req *generated.ExecuteCommandRequest, opts ...grpc.CallOption) (*generated.ExecuteCommandResponse, error) {
	r := clone(req)
	r.Database, r.Transaction = h.binding()
	return h.raw.ExecuteCommand(ctx, r, opts...)
}

// CreateRecord is ArcadeDbService.CreateRecord, bound to the transaction.
func (h *TxHandle) CreateRecord(ctx context.Context, req *generated.CreateRecordRequest, opts ...grpc.CallOption) (*generated.CreateRecordResponse, error) {
	r := clone(req)
	r.Database, r.Transaction = h.binding()
	return h.raw.CreateRecord(ctx, r, opts...)
}

// UpdateRecord is ArcadeDbService.UpdateRecord, bound to the transaction.
func (h *TxHandle) UpdateRecord(ctx context.Context, req *generated.UpdateRecordRequest, opts ...grpc.CallOption) (*generated.UpdateRecordResponse, error) {
	r := clone(req)
	r.Database, r.Transaction = h.binding()
	return h.raw.UpdateRecord(ctx, r, opts...)
}

// DeleteRecord is ArcadeDbService.DeleteRecord, bound to the transaction.
func (h *TxHandle) DeleteRecord(ctx context.Context, req *generated.DeleteRecordRequest, opts ...grpc.CallOption) (*generated.DeleteRecordResponse, error) {
	r := clone(req)
	r.Database, r.Transaction = h.binding()
	return h.raw.DeleteRecord(ctx, r, opts...)
}

// LookupByRid is ArcadeDbService.LookupByRid, bound to the transaction.
func (h *TxHandle) LookupByRid(ctx context.Context, req *generated.LookupByRidRequest, opts ...grpc.CallOption) (*generated.LookupByRidResponse, error) {
	r := clone(req)
	r.Database, r.Transaction = h.binding()
	return h.raw.LookupByRid(ctx, r, opts...)
}

// VectorSearch is ArcadeDbService.VectorSearch, bound to the transaction.
func (h *TxHandle) VectorSearch(ctx context.Context, req *generated.VectorSearchRequest, opts ...grpc.CallOption) (*generated.VectorSearchResponse, error) {
	r := clone(req)
	r.Database, r.Transaction = h.binding()
	return h.raw.VectorSearch(ctx, r, opts...)
}

// HybridSearch is ArcadeDbService.HybridSearch, bound to the transaction.
func (h *TxHandle) HybridSearch(ctx context.Context, req *generated.HybridSearchRequest, opts ...grpc.CallOption) (*generated.HybridSearchResponse, error) {
	r := clone(req)
	r.Database, r.Transaction = h.binding()
	return h.raw.HybridSearch(ctx, r, opts...)
}

// FullTextSearch is ArcadeDbService.FullTextSearch, bound to the transaction.
func (h *TxHandle) FullTextSearch(ctx context.Context, req *generated.FullTextSearchRequest, opts ...grpc.CallOption) (*generated.FullTextSearchResponse, error) {
	r := clone(req)
	r.Database, r.Transaction = h.binding()
	return h.raw.FullTextSearch(ctx, r, opts...)
}

// TimeSeriesLatest is ArcadeDbService.TimeSeriesLatest, bound to the transaction. The
// request carries a transaction field for the same reason TimeSeriesQuery's does.
func (h *TxHandle) TimeSeriesLatest(ctx context.Context, req *generated.TimeSeriesLatestRequest, opts ...grpc.CallOption) (*generated.TimeSeriesLatestResponse, error) {
	r := clone(req)
	r.Database, r.Transaction = h.binding()
	return h.raw.TimeSeriesLatest(ctx, r, opts...)
}

// StreamQuery is Client.StreamQuery bound to the transaction, with the same lazy,
// re-rangeable, cancel-on-break and error behaviour. The request is copied and bound when
// StreamQuery is called, not when the sequence is ranged, so later changes to req do not
// reach the server.
func (h *TxHandle) StreamQuery(ctx context.Context, req *generated.StreamQueryRequest, opts ...grpc.CallOption) iter.Seq2[*generated.GrpcRecord, error] {
	r := clone(req)
	r.Database, r.Transaction = h.binding()
	return streamQuery(ctx, h.raw, r, opts)
}

// TimeSeriesQuery is Client.TimeSeriesQuery bound to the transaction, copied and bound when
// called as StreamQuery is. A query naming an open transaction runs on that transaction's
// thread and observes its uncommitted points (ArcadeData/arcadedb#7370).
func (h *TxHandle) TimeSeriesQuery(ctx context.Context, req *generated.TimeSeriesQueryRequest, opts ...grpc.CallOption) iter.Seq2[*generated.TimeSeriesQueryResult, error] {
	r := clone(req)
	r.Database, r.Transaction = h.binding()
	return timeSeriesQuery(ctx, h.raw, r, opts)
}
