package arcadedbgrpc

import (
	"context"
	"errors"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"sync"
	"testing"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc/generated"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/proto"
)

// txCall is one request the transaction fake saw: the RPC's short name, the request's
// Database field (BeginTransaction's own; empty for Commit and Rollback, which carry none)
// and a copy of the TransactionContext it carried (nil when it carried none).
type txCall struct {
	op string
	db string
	tx *generated.TransactionContext
}

// txService answers BeginTransaction with id (default "t1"), Commit with
// success=true, committed=true (unless notCommitted), and every bindable RPC with an empty
// reply. A non-nil error in fail is returned by the RPC of that name.
type txService struct {
	generated.UnimplementedArcadeDbServiceServer
	mu           sync.Mutex
	calls        []txCall
	fail         map[string]error
	id           string
	notCommitted string // when non-empty, Commit answers committed=false with this message
}

func newTxService() *txService { return &txService{fail: map[string]error{}, id: "t1"} }

func (s *txService) rec(op, db string, tx *generated.TransactionContext) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if tx != nil {
		tx = proto.Clone(tx).(*generated.TransactionContext)
	}
	s.calls = append(s.calls, txCall{op, db, tx})
	return s.fail[op]
}

func (s *txService) seen() []txCall {
	s.mu.Lock()
	defer s.mu.Unlock()
	return append([]txCall(nil), s.calls...)
}

func (s *txService) ops() []string {
	var ops []string
	for _, c := range s.seen() {
		ops = append(ops, c.op)
	}
	return ops
}

func (s *txService) BeginTransaction(_ context.Context, r *generated.BeginTransactionRequest) (*generated.BeginTransactionResponse, error) {
	if err := s.rec("BeginTransaction", r.GetDatabase(), nil); err != nil {
		return nil, err
	}
	return &generated.BeginTransactionResponse{TransactionId: s.id}, nil
}

func (s *txService) CommitTransaction(_ context.Context, r *generated.CommitTransactionRequest) (*generated.CommitTransactionResponse, error) {
	if err := s.rec("CommitTransaction", "", r.GetTransaction()); err != nil {
		return nil, err
	}
	if s.notCommitted != "" {
		return &generated.CommitTransactionResponse{Success: true, Committed: false, Message: s.notCommitted}, nil
	}
	return &generated.CommitTransactionResponse{Success: true, Committed: true}, nil
}

func (s *txService) RollbackTransaction(_ context.Context, r *generated.RollbackTransactionRequest) (*generated.RollbackTransactionResponse, error) {
	if err := s.rec("RollbackTransaction", "", r.GetTransaction()); err != nil {
		return nil, err
	}
	return &generated.RollbackTransactionResponse{Success: true, RolledBack: true}, nil
}

func (s *txService) ExecuteQuery(_ context.Context, r *generated.ExecuteQueryRequest) (*generated.ExecuteQueryResponse, error) {
	return &generated.ExecuteQueryResponse{}, s.rec("ExecuteQuery", r.GetDatabase(), r.GetTransaction())
}

func (s *txService) ExecuteCommand(_ context.Context, r *generated.ExecuteCommandRequest) (*generated.ExecuteCommandResponse, error) {
	return &generated.ExecuteCommandResponse{}, s.rec("ExecuteCommand", r.GetDatabase(), r.GetTransaction())
}

func (s *txService) CreateRecord(_ context.Context, r *generated.CreateRecordRequest) (*generated.CreateRecordResponse, error) {
	return &generated.CreateRecordResponse{}, s.rec("CreateRecord", r.GetDatabase(), r.GetTransaction())
}

func (s *txService) UpdateRecord(_ context.Context, r *generated.UpdateRecordRequest) (*generated.UpdateRecordResponse, error) {
	return &generated.UpdateRecordResponse{}, s.rec("UpdateRecord", r.GetDatabase(), r.GetTransaction())
}

func (s *txService) DeleteRecord(_ context.Context, r *generated.DeleteRecordRequest) (*generated.DeleteRecordResponse, error) {
	return &generated.DeleteRecordResponse{}, s.rec("DeleteRecord", r.GetDatabase(), r.GetTransaction())
}

func (s *txService) LookupByRid(_ context.Context, r *generated.LookupByRidRequest) (*generated.LookupByRidResponse, error) {
	return &generated.LookupByRidResponse{}, s.rec("LookupByRid", r.GetDatabase(), r.GetTransaction())
}

func (s *txService) VectorSearch(_ context.Context, r *generated.VectorSearchRequest) (*generated.VectorSearchResponse, error) {
	return &generated.VectorSearchResponse{}, s.rec("VectorSearch", r.GetDatabase(), r.GetTransaction())
}

func (s *txService) HybridSearch(_ context.Context, r *generated.HybridSearchRequest) (*generated.HybridSearchResponse, error) {
	return &generated.HybridSearchResponse{}, s.rec("HybridSearch", r.GetDatabase(), r.GetTransaction())
}

func (s *txService) FullTextSearch(_ context.Context, r *generated.FullTextSearchRequest) (*generated.FullTextSearchResponse, error) {
	return &generated.FullTextSearchResponse{}, s.rec("FullTextSearch", r.GetDatabase(), r.GetTransaction())
}

func (s *txService) TimeSeriesLatest(_ context.Context, r *generated.TimeSeriesLatestRequest) (*generated.TimeSeriesLatestResponse, error) {
	return &generated.TimeSeriesLatestResponse{}, s.rec("TimeSeriesLatest", r.GetDatabase(), r.GetTransaction())
}

func (s *txService) StreamQuery(r *generated.StreamQueryRequest, ss grpc.ServerStreamingServer[generated.QueryResult]) error {
	if err := s.rec("StreamQuery", r.GetDatabase(), r.GetTransaction()); err != nil {
		return err
	}
	return ss.Send(recs("#1:0"))
}

func (s *txService) TimeSeriesQuery(r *generated.TimeSeriesQueryRequest, ss grpc.ServerStreamingServer[generated.TimeSeriesQueryResult]) error {
	if err := s.rec("TimeSeriesQuery", r.GetDatabase(), r.GetTransaction()); err != nil {
		return err
	}
	return ss.Send(&generated.TimeSeriesQueryResult{Last: true})
}

func wantOps(t *testing.T, s *txService, want ...string) {
	t.Helper()
	got := s.ops()
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Fatalf("calls = %v, want %v", got, want)
	}
}

// wantBound fails unless c carried database "d" and exactly TransactionContext{"t1", "d"}:
// every other field, the inline begin/commit/rollback flags included, at its zero value.
func wantBound(t *testing.T, c txCall) {
	t.Helper()
	want := &generated.TransactionContext{TransactionId: "t1", Database: "d"}
	if c.op != "CommitTransaction" && c.op != "RollbackTransaction" && c.db != "d" {
		t.Errorf("%s: Database = %q, want \"d\"", c.op, c.db)
	}
	if !proto.Equal(c.tx, want) {
		t.Errorf("%s: Transaction = %v, want %v", c.op, c.tx, want)
	}
}

// stale is the transaction context a caller's request arrives with in the binding tests:
// another transaction's id, another database, and an inline begin flag.
func stale() *generated.TransactionContext {
	return &generated.TransactionContext{TransactionId: "stale", Database: "other", Begin: true, Rollback: true}
}

var errX = errors.New("x")

func TestTransactionCommits(t *testing.T) {
	s := newTxService()
	c := newFake(t, s, nil)
	err := c.Transaction(context.Background(), "d", func(tx *TxHandle) error {
		_, err := tx.ExecuteQuery(context.Background(), &generated.ExecuteQueryRequest{Query: "SELECT 1"})
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	wantOps(t, s, "BeginTransaction", "ExecuteQuery", "CommitTransaction")
	calls := s.seen()
	if calls[0].db != "d" {
		t.Fatalf("BeginTransaction database = %q, want \"d\"", calls[0].db)
	}
	wantBound(t, calls[1])
	wantBound(t, calls[2])
}

func TestTransactionRollsBackOnError(t *testing.T) {
	s := newTxService()
	c := newFake(t, s, nil)
	err := c.Transaction(context.Background(), "d", func(*TxHandle) error { return errX })
	if !errors.Is(err, errX) {
		t.Fatalf("err = %v", err)
	}
	var te *TxError
	if errors.As(err, &te) {
		t.Fatalf("successful rollback still wrapped: %v", err)
	}
	wantOps(t, s, "BeginTransaction", "RollbackTransaction")
	wantBound(t, s.seen()[1])
}

func TestTransactionRollbackFailureIsTxError(t *testing.T) {
	s := newTxService()
	s.fail["RollbackTransaction"] = status.Error(codes.Internal, "rollback failed")
	c := newFake(t, s, nil)
	fnErr := status.Error(codes.Aborted, "fn failed")
	err := c.Transaction(context.Background(), "d", func(*TxHandle) error { return fnErr })
	var te *TxError
	if !errors.As(err, &te) {
		t.Fatalf("err = %T %v, want *TxError", err, err)
	}
	if !errors.Is(err, fnErr) || te.Err != fnErr {
		t.Fatalf("TxError.Err = %v, want fn's error", te.Err)
	}
	if code := status.Code(err); code != codes.Aborted {
		t.Fatalf("status.Code(err) = %v, want fn's Aborted, not the rollback's Internal", code)
	}
	if code := status.Code(te.RollbackErr); code != codes.Internal {
		t.Fatalf("status.Code(RollbackErr) = %v, want Internal", code)
	}
	if msg := err.Error(); !strings.Contains(msg, "fn failed") || !strings.Contains(msg, "rollback failed") {
		t.Fatalf("Error() = %q, want both messages", msg)
	}
	wantOps(t, s, "BeginTransaction", "RollbackTransaction")
}

func TestTransactionRePanicsOriginalValue(t *testing.T) {
	s := newTxService()
	c := newFake(t, s, nil)
	type boom struct{ n int }
	defer func() {
		if r := recover(); r != (boom{7}) {
			t.Fatalf("recover() = %v, want boom{7}", r)
		}
		wantOps(t, s, "BeginTransaction", "RollbackTransaction")
	}()
	_ = c.Transaction(context.Background(), "d", func(*TxHandle) error { panic(boom{7}) })
	t.Fatal("Transaction returned instead of re-panicking")
}

func TestTransactionPanicWinsOverRollbackFailure(t *testing.T) {
	s := newTxService()
	s.fail["RollbackTransaction"] = status.Error(codes.Internal, "rollback failed")
	c := newFake(t, s, nil)
	defer func() {
		if r := recover(); r != "boom" {
			t.Fatalf("recover() = %v, want boom", r)
		}
		wantOps(t, s, "BeginTransaction", "RollbackTransaction")
	}()
	_ = c.Transaction(context.Background(), "d", func(*TxHandle) error { panic("boom") })
	t.Fatal("Transaction returned instead of re-panicking")
}

func TestTransactionRollsBackOnGoexit(t *testing.T) {
	s := newTxService()
	c := newFake(t, s, nil)
	done := make(chan struct{})
	go func() {
		defer close(done)
		_ = c.Transaction(context.Background(), "d", func(*TxHandle) error {
			runtime.Goexit()
			return nil
		})
	}()
	<-done
	wantOps(t, s, "BeginTransaction", "RollbackTransaction")
}

// Under default semantics panic(nil) recovers as *runtime.PanicNilError and is re-panicked
// like any other value. Under GODEBUG=panicnil=1 it recovers as nil, indistinguishable from
// runtime.Goexit, and Transaction must then return a non-nil error: nil reads as committed.
// The setting is process-wide, so that half runs in a child process of this test binary.
func TestTransactionNilPanicIsAnError(t *testing.T) {
	if os.Getenv("ARCADEDBGRPC_TX_PANICNIL_CHILD") == "1" {
		s := newTxService()
		c := newFake(t, s, nil)
		err := c.Transaction(context.Background(), "d", func(*TxHandle) error { panic(nil) })
		if err == nil || !strings.Contains(err.Error(), "rolled back") {
			t.Fatalf("err = %v, want an error saying the transaction was rolled back", err)
		}
		wantOps(t, s, "BeginTransaction", "RollbackTransaction")
		return
	}

	t.Run("default", func(t *testing.T) {
		s := newTxService()
		c := newFake(t, s, nil)
		defer func() {
			r := recover()
			if _, ok := r.(*runtime.PanicNilError); !ok {
				t.Fatalf("recover() = %T %v, want *runtime.PanicNilError", r, r)
			}
			wantOps(t, s, "BeginTransaction", "RollbackTransaction")
		}()
		_ = c.Transaction(context.Background(), "d", func(*TxHandle) error { panic(nil) })
		t.Fatal("Transaction returned instead of re-panicking")
	})

	t.Run("panicnil=1", func(t *testing.T) {
		cmd := exec.Command(os.Args[0], "-test.run=^TestTransactionNilPanicIsAnError$", "-test.v")
		cmd.Env = append(os.Environ(), "ARCADEDBGRPC_TX_PANICNIL_CHILD=1", "GODEBUG=panicnil=1")
		out, err := cmd.CombinedOutput()
		if err != nil {
			t.Fatalf("child under GODEBUG=panicnil=1 failed: %v\n%s", err, out)
		}
		if !strings.Contains(string(out), "--- PASS: TestTransactionNilPanicIsAnError") {
			t.Fatalf("child did not run the test:\n%s", out)
		}
	})
}

func TestTransactionCommitFailureRollsBack(t *testing.T) {
	s := newTxService()
	commitErr := status.Error(codes.Unavailable, "commit failed")
	s.fail["CommitTransaction"] = commitErr
	c := newFake(t, s, nil)
	err := c.Transaction(context.Background(), "d", func(*TxHandle) error { return nil })
	if status.Code(err) != codes.Unavailable || !strings.Contains(err.Error(), "commit failed") {
		t.Fatalf("err = %v, want the commit's status error", err)
	}
	var te *TxError
	if errors.As(err, &te) {
		t.Fatalf("commit error wrapped in TxError: %v", err)
	}
	wantOps(t, s, "BeginTransaction", "CommitTransaction", "RollbackTransaction")
	wantBound(t, s.seen()[2])
}

func TestTransactionNotCommitted(t *testing.T) {
	s := newTxService()
	s.notCommitted = "reaped"
	c := newFake(t, s, nil)
	err := c.Transaction(context.Background(), "d", func(*TxHandle) error { return nil })
	if !errors.Is(err, ErrNotCommitted) {
		t.Fatalf("err = %v, want ErrNotCommitted", err)
	}
	if !strings.Contains(err.Error(), "reaped") {
		t.Fatalf("err = %q, want the server's message", err)
	}
	wantOps(t, s, "BeginTransaction", "CommitTransaction")
}

func TestTransactionBlankIDIsError(t *testing.T) {
	s := newTxService()
	s.id = "  "
	c := newFake(t, s, nil)
	called := false
	err := c.Transaction(context.Background(), "d", func(*TxHandle) error { called = true; return nil })
	if called {
		t.Fatal("fn called without a transaction id")
	}
	if !errors.Is(err, ErrNoTransactionID) {
		t.Fatalf("err = %v, want ErrNoTransactionID", err)
	}
	wantOps(t, s, "BeginTransaction")
}

func TestTransactionBeginFailureSkipsFn(t *testing.T) {
	s := newTxService()
	s.fail["BeginTransaction"] = status.Error(codes.PermissionDenied, "no")
	c := newFake(t, s, nil)
	called := false
	err := c.Transaction(context.Background(), "d", func(*TxHandle) error { called = true; return nil })
	if called || status.Code(err) != codes.PermissionDenied {
		t.Fatalf("called = %v, err = %v", called, err)
	}
	wantOps(t, s, "BeginTransaction")
}

func TestTransactionRollsBackAfterContextCancel(t *testing.T) {
	s := newTxService()
	c := newFake(t, s, nil)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	err := c.Transaction(ctx, "d", func(*TxHandle) error {
		cancel()
		return ctx.Err()
	})
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("err = %v", err)
	}
	var te *TxError
	if errors.As(err, &te) {
		t.Fatalf("rollback did not reach the server: %v", te.RollbackErr)
	}
	wantOps(t, s, "BeginTransaction", "RollbackTransaction")
}

func TestTxHandleForcesDatabaseAndTransaction(t *testing.T) {
	s := newTxService()
	c := newFake(t, s, nil)
	err := c.Transaction(context.Background(), "d", func(tx *TxHandle) error {
		_, err := tx.ExecuteCommand(context.Background(), &generated.ExecuteCommandRequest{
			Database: "other", Command: "INSERT", Transaction: stale(),
		})
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	wantOps(t, s, "BeginTransaction", "ExecuteCommand", "CommitTransaction")
	got := s.seen()[1]
	wantBound(t, got)
	if got.tx.GetBegin() || got.tx.GetRollback() {
		t.Fatalf("inline flags survived binding: %v", got.tx)
	}
}

func TestTxHandleNilRequestIsBound(t *testing.T) {
	s := newTxService()
	c := newFake(t, s, nil)
	err := c.Transaction(context.Background(), "d", func(tx *TxHandle) error {
		_, err := tx.ExecuteQuery(context.Background(), nil)
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	wantBound(t, s.seen()[1])
}

func TestTxHandleNeverMutatesCallerRequest(t *testing.T) {
	s := newTxService()
	c := newFake(t, s, nil)
	req := &generated.ExecuteQueryRequest{Database: "d", Query: "SELECT 1"}
	err := c.Transaction(context.Background(), "d", func(tx *TxHandle) error {
		_, err := tx.ExecuteQuery(context.Background(), req)
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	if req.Database != "d" || req.Transaction != nil {
		t.Fatalf("caller's request was mutated: Database=%q Transaction=%v", req.Database, req.Transaction)
	}
	// Reusing the same message outside the transaction must not carry the dead id
	// (ArcadeData/arcadedb#5040 reached by aliasing).
	if _, err := c.Raw().ExecuteQuery(context.Background(), req); err != nil {
		t.Fatal(err)
	}
	calls := s.seen()
	if last := calls[len(calls)-1]; last.op != "ExecuteQuery" || last.tx != nil {
		t.Fatalf("reused request carried a transaction: %+v", last)
	}

	// The same holds for a request that arrived carrying its own context: it keeps it.
	own := &generated.ExecuteQueryRequest{Database: "other", Transaction: stale()}
	err = c.Transaction(context.Background(), "d", func(tx *TxHandle) error {
		_, err := tx.ExecuteQuery(context.Background(), own)
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	if own.Database != "other" || !proto.Equal(own.Transaction, stale()) {
		t.Fatalf("caller's request was mutated: %v", own)
	}
}

func TestTxHandleBoundStreams(t *testing.T) {
	s := newTxService()
	c := newFake(t, s, nil)
	sq := &generated.StreamQueryRequest{Database: "other", Query: "SELECT", Transaction: stale()}
	tq := &generated.TimeSeriesQueryRequest{Database: "other", Type: "T", Transaction: stale()}
	err := c.Transaction(context.Background(), "d", func(tx *TxHandle) error {
		n := 0
		for r, err := range tx.StreamQuery(context.Background(), sq) {
			if err != nil {
				return err
			}
			if r.GetRid() != "#1:0" {
				t.Errorf("record = %v", r)
			}
			n++
		}
		for m, err := range tx.TimeSeriesQuery(context.Background(), tq) {
			if err != nil {
				return err
			}
			if !m.GetLast() {
				t.Errorf("message = %v", m)
			}
			n++
		}
		if n != 2 {
			t.Errorf("got %d items, want 2", n)
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	wantOps(t, s, "BeginTransaction", "StreamQuery", "TimeSeriesQuery", "CommitTransaction")
	calls := s.seen()
	wantBound(t, calls[1])
	wantBound(t, calls[2])
	if sq.Database != "other" || !proto.Equal(sq.Transaction, stale()) ||
		tq.Database != "other" || !proto.Equal(tq.Transaction, stale()) {
		t.Fatal("a stream call mutated the caller's request")
	}
}

func TestTxHandleCoversEveryUnaryMethod(t *testing.T) {
	ctx := context.Background()
	cases := []struct {
		op   string
		call func(*TxHandle) error
	}{
		{"ExecuteQuery", func(tx *TxHandle) error {
			_, err := tx.ExecuteQuery(ctx, &generated.ExecuteQueryRequest{Database: "other", Transaction: stale()})
			return err
		}},
		{"ExecuteCommand", func(tx *TxHandle) error {
			_, err := tx.ExecuteCommand(ctx, &generated.ExecuteCommandRequest{Database: "other", Transaction: stale()})
			return err
		}},
		{"CreateRecord", func(tx *TxHandle) error {
			_, err := tx.CreateRecord(ctx, &generated.CreateRecordRequest{Database: "other", Transaction: stale()})
			return err
		}},
		{"UpdateRecord", func(tx *TxHandle) error {
			_, err := tx.UpdateRecord(ctx, &generated.UpdateRecordRequest{Database: "other", Transaction: stale()})
			return err
		}},
		{"DeleteRecord", func(tx *TxHandle) error {
			_, err := tx.DeleteRecord(ctx, &generated.DeleteRecordRequest{Database: "other", Transaction: stale()})
			return err
		}},
		{"LookupByRid", func(tx *TxHandle) error {
			_, err := tx.LookupByRid(ctx, &generated.LookupByRidRequest{Database: "other", Transaction: stale()})
			return err
		}},
		{"VectorSearch", func(tx *TxHandle) error {
			_, err := tx.VectorSearch(ctx, &generated.VectorSearchRequest{Database: "other", Transaction: stale()})
			return err
		}},
		{"HybridSearch", func(tx *TxHandle) error {
			_, err := tx.HybridSearch(ctx, &generated.HybridSearchRequest{Database: "other", Transaction: stale()})
			return err
		}},
		{"FullTextSearch", func(tx *TxHandle) error {
			_, err := tx.FullTextSearch(ctx, &generated.FullTextSearchRequest{Database: "other", Transaction: stale()})
			return err
		}},
		{"TimeSeriesLatest", func(tx *TxHandle) error {
			_, err := tx.TimeSeriesLatest(ctx, &generated.TimeSeriesLatestRequest{Database: "other", Transaction: stale()})
			return err
		}},
	}
	if len(cases) != 10 {
		t.Fatalf("%d cases, want the 10 unary handle methods", len(cases))
	}
	for _, tc := range cases {
		t.Run(tc.op, func(t *testing.T) {
			s := newTxService()
			c := newFake(t, s, nil)
			if err := c.Transaction(ctx, "d", tc.call); err != nil {
				t.Fatal(err)
			}
			wantOps(t, s, "BeginTransaction", tc.op, "CommitTransaction")
			wantBound(t, s.seen()[1])
		})
	}
}

// An RPC error from a handle call passes through as grpc-go's status error, unwrapped.
func TestTxHandleRPCErrorPassesThrough(t *testing.T) {
	s := newTxService()
	s.fail["ExecuteQuery"] = status.Error(codes.InvalidArgument, "bad query")
	c := newFake(t, s, nil)
	var callErr error
	err := c.Transaction(context.Background(), "d", func(tx *TxHandle) error {
		_, callErr = tx.ExecuteQuery(context.Background(), &generated.ExecuteQueryRequest{})
		return callErr
	})
	if status.Code(callErr) != codes.InvalidArgument || status.Code(err) != codes.InvalidArgument {
		t.Fatalf("callErr = %v, err = %v", callErr, err)
	}
	wantOps(t, s, "BeginTransaction", "ExecuteQuery", "RollbackTransaction")
}
