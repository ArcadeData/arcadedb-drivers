package arcadedb

import (
	"context"
	"errors"
	"net/http"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"sync"
	"testing"
)

// txCall is one request the transaction fake saw: the operation (begin, commit,
// rollback, query, command) and the arcadedb-session-id header it carried.
type txCall struct {
	op      string
	session string
}

// txFake answers begin with session id "s1" (unless noSession), everything else with
// 204 or an empty envelope, and fails the operations named in fail with a 500.
type txFake struct {
	mu        sync.Mutex
	calls     []txCall
	fail      map[string]bool
	noSession bool
}

func (f *txFake) handler(w http.ResponseWriter, r *http.Request) {
	op := strings.Split(strings.TrimPrefix(r.URL.Path, "/api/v1/"), "/")[0]
	f.mu.Lock()
	f.calls = append(f.calls, txCall{op, r.Header.Get("arcadedb-session-id")})
	fail := f.fail[op]
	f.mu.Unlock()
	if fail {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(500)
		_, _ = w.Write([]byte(`{"error":"` + op + ` failed"}`))
		return
	}
	switch op {
	case "begin":
		if !f.noSession {
			w.Header().Set("arcadedb-session-id", "s1")
		}
		w.WriteHeader(204)
	case "commit", "rollback":
		w.WriteHeader(204)
	default:
		writeJSON(w, `{"result":[]}`)
	}
}

func (f *txFake) seen() []txCall {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]txCall(nil), f.calls...)
}

func newTxFake(t *testing.T, fail ...string) (*txFake, *Database) {
	f := &txFake{fail: map[string]bool{}}
	for _, op := range fail {
		f.fail[op] = true
	}
	return f, fakeServer(t, f.handler).DB("d")
}

func wantCalls(t *testing.T, f *txFake, want ...txCall) {
	t.Helper()
	got := f.seen()
	if len(got) != len(want) {
		t.Fatalf("calls = %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("calls = %v, want %v", got, want)
		}
	}
}

var errX = errors.New("x")

func TestTransactionCommitsOnNil(t *testing.T) {
	f, db := newTxFake(t)
	err := db.Transaction(context.Background(), func(tx *Database) error {
		_, err := tx.Query(context.Background(), SQL, "SELECT 1", nil)
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	wantCalls(t, f, txCall{"begin", ""}, txCall{"query", "s1"}, txCall{"commit", "s1"})
}

func TestTransactionOuterHandleNotInTransaction(t *testing.T) {
	f, db := newTxFake(t)
	err := db.Transaction(context.Background(), func(tx *Database) error {
		if tx == db {
			t.Error("fn received the outer handle")
		}
		_, err := db.Query(context.Background(), SQL, "SELECT 1", nil)
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	if db.sessionParam() != nil {
		t.Fatal("outer handle gained a session id")
	}
	wantCalls(t, f, txCall{"begin", ""}, txCall{"query", ""}, txCall{"commit", "s1"})
}

func TestTransactionRollsBackOnError(t *testing.T) {
	f, db := newTxFake(t)
	err := db.Transaction(context.Background(), func(*Database) error { return errX })
	if !errors.Is(err, errX) {
		t.Fatalf("err = %v", err)
	}
	var te *TxError
	if errors.As(err, &te) {
		t.Fatalf("successful rollback still wrapped: %v", err)
	}
	wantCalls(t, f, txCall{"begin", ""}, txCall{"rollback", "s1"})
}

func TestTransactionRollbackFailureWrapsInTxError(t *testing.T) {
	f, db := newTxFake(t, "rollback")
	err := db.Transaction(context.Background(), func(*Database) error { return errX })
	var te *TxError
	if !errors.As(err, &te) {
		t.Fatalf("err = %T %v, want *TxError", err, err)
	}
	if !errors.Is(err, errX) {
		t.Fatalf("errors.Is(err, errX) = false: %v", err)
	}
	var ae *ArcadeDBError
	if errors.As(err, &ae) {
		t.Fatalf("errors.As found the rollback's error through Unwrap: %v", ae)
	}
	if !errors.As(te.RollbackErr, &ae) || ae.Status != 500 {
		t.Fatalf("RollbackErr = %v", te.RollbackErr)
	}
	if msg := err.Error(); !strings.Contains(msg, "x") || !strings.Contains(msg, "rollback failed") {
		t.Fatalf("Error() = %q, want both messages", msg)
	}
	wantCalls(t, f, txCall{"begin", ""}, txCall{"rollback", "s1"})
}

func TestTransactionRePanics(t *testing.T) {
	f, db := newTxFake(t)
	defer func() {
		if r := recover(); r != "boom" {
			t.Fatalf("recover() = %v, want boom", r)
		}
		wantCalls(t, f, txCall{"begin", ""}, txCall{"rollback", "s1"})
	}()
	_ = db.Transaction(context.Background(), func(*Database) error { panic("boom") })
	t.Fatal("Transaction returned instead of re-panicking")
}

func TestTransactionPanicWinsOverRollbackFailure(t *testing.T) {
	f, db := newTxFake(t, "rollback")
	defer func() {
		if r := recover(); r != "boom" {
			t.Fatalf("recover() = %v, want boom", r)
		}
		wantCalls(t, f, txCall{"begin", ""}, txCall{"rollback", "s1"})
	}()
	_ = db.Transaction(context.Background(), func(*Database) error { panic("boom") })
	t.Fatal("Transaction returned instead of re-panicking")
}

func TestTransactionRollsBackOnGoexit(t *testing.T) {
	f, db := newTxFake(t)
	done := make(chan struct{})
	go func() {
		defer close(done)
		_ = db.Transaction(context.Background(), func(*Database) error {
			runtime.Goexit()
			return nil
		})
	}()
	<-done
	wantCalls(t, f, txCall{"begin", ""}, txCall{"rollback", "s1"})
}

func TestTransactionCommitFailureRollsBackAndReturnsCommitError(t *testing.T) {
	f, db := newTxFake(t, "commit")
	err := db.Transaction(context.Background(), func(*Database) error { return nil })
	var ae *ArcadeDBError
	if !errors.As(err, &ae) || ae.Status != 500 || ae.ErrorMessage != "commit failed" {
		t.Fatalf("err = %v, want the commit's *ArcadeDBError", err)
	}
	var te *TxError
	if errors.As(err, &te) {
		t.Fatalf("commit error wrapped in TxError: %v", err)
	}
	wantCalls(t, f, txCall{"begin", ""}, txCall{"commit", "s1"}, txCall{"rollback", "s1"})
}

func TestTransactionMissingSessionHeader(t *testing.T) {
	f, db := newTxFake(t)
	f.noSession = true
	called := false
	err := db.Transaction(context.Background(), func(*Database) error { called = true; return nil })
	if called {
		t.Fatal("fn called without a session id")
	}
	var ae *ArcadeDBError
	if !errors.As(err, &ae) || ae.Status != 204 || !strings.Contains(ae.ErrorMessage, "did not return a session id") {
		t.Fatalf("err = %v", err)
	}
	wantCalls(t, f, txCall{"begin", ""})
}

func TestTransactionBeginFailureSkipsFn(t *testing.T) {
	f, db := newTxFake(t, "begin")
	called := false
	err := db.Transaction(context.Background(), func(*Database) error { called = true; return nil })
	var ae *ArcadeDBError
	if called || !errors.As(err, &ae) || ae.Status != 500 {
		t.Fatalf("called = %v, err = %v", called, err)
	}
	wantCalls(t, f, txCall{"begin", ""})
}

func TestTransactionRollsBackAfterContextCancel(t *testing.T) {
	f, db := newTxFake(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	err := db.Transaction(ctx, func(*Database) error {
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
	wantCalls(t, f, txCall{"begin", ""}, txCall{"rollback", "s1"})
}

func TestTransactionNestedBeginSendsSession(t *testing.T) {
	f, db := newTxFake(t)
	err := db.Transaction(context.Background(), func(tx *Database) error {
		return tx.Transaction(context.Background(), func(*Database) error { return nil })
	})
	if err != nil {
		t.Fatal(err)
	}
	got := f.seen()
	if len(got) < 2 || got[1] != (txCall{"begin", "s1"}) {
		t.Fatalf("nested begin = %v, want it to carry the outer session", got)
	}
}

// Under default semantics (Go 1.21+) panic(nil) recovers as *runtime.PanicNilError, so it
// is re-panicked like any other value, after the rollback.
func TestTransactionPanicNilRePanicsPanicNilError(t *testing.T) {
	f, db := newTxFake(t)
	defer func() {
		r := recover()
		if _, ok := r.(*runtime.PanicNilError); !ok {
			t.Fatalf("recover() = %T %v, want *runtime.PanicNilError", r, r)
		}
		wantCalls(t, f, txCall{"begin", ""}, txCall{"rollback", "s1"})
	}()
	_ = db.Transaction(context.Background(), func(*Database) error { panic(nil) })
	t.Fatal("Transaction returned instead of re-panicking")
}

// Under GODEBUG=panicnil=1, panic(nil) recovers as nil, which is indistinguishable from
// runtime.Goexit in the deferred function. Transaction then returns normally, and must not
// return nil: a nil return reads as committed while the transaction was rolled back. The
// setting is process-wide, so the check runs in a child process of this test binary.
func TestTransactionPanicNilUnderPanicnil1ReturnsError(t *testing.T) {
	if os.Getenv("ARCADEDB_TX_PANICNIL_CHILD") == "1" {
		f, db := newTxFake(t)
		err := db.Transaction(context.Background(), func(*Database) error { panic(nil) })
		if err == nil || !strings.Contains(err.Error(), "rolled back") {
			t.Fatalf("err = %v, want an error saying the transaction was rolled back", err)
		}
		wantCalls(t, f, txCall{"begin", ""}, txCall{"rollback", "s1"})
		return
	}
	cmd := exec.Command(os.Args[0], "-test.run=^TestTransactionPanicNilUnderPanicnil1ReturnsError$", "-test.v")
	cmd.Env = append(os.Environ(), "ARCADEDB_TX_PANICNIL_CHILD=1", "GODEBUG=panicnil=1")
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("child under GODEBUG=panicnil=1 failed: %v\n%s", err, out)
	}
}

// A transaction handle refuses a batch load: the batch endpoint takes no session id, so
// the load would run outside the transaction and commit on its own.
func TestBatchLoadRefusesTransactionHandle(t *testing.T) {
	f, db := newTxFake(t)
	iterated := false
	err := db.Transaction(context.Background(), func(tx *Database) error {
		_, err := tx.BatchLoad(context.Background(),
			func(func(VertexRow) bool) { iterated = true }, nil, nil)
		if !errors.Is(err, ErrBatchInTransaction) {
			t.Errorf("BatchLoad err = %v, want ErrBatchInTransaction", err)
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if iterated {
		t.Fatal("the vertex sequence was iterated")
	}
	wantCalls(t, f, txCall{"begin", ""}, txCall{"commit", "s1"})
}

func TestBatchLoadStreamRefusesTransactionHandle(t *testing.T) {
	f, db := newTxFake(t)
	iterated := false
	err := db.Transaction(context.Background(), func(tx *Database) error {
		var errs []error
		events := 0
		for ev, err := range tx.BatchLoadStream(context.Background(),
			func(func(VertexRow) bool) { iterated = true }, nil, nil) {
			if err != nil {
				errs = append(errs, err)
			} else if ev != nil {
				events++
			}
		}
		if len(errs) != 1 || !errors.Is(errs[0], ErrBatchInTransaction) || events != 0 {
			t.Errorf("errs = %v, events = %d, want ErrBatchInTransaction once and no events", errs, events)
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if iterated {
		t.Fatal("the vertex sequence was iterated")
	}
	wantCalls(t, f, txCall{"begin", ""}, txCall{"commit", "s1"})
}
