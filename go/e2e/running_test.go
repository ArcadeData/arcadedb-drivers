package e2e

import (
	"context"
	"fmt"
	"slices"
	"testing"
	"time"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb"
)

// longLoop runs until it is terminated. SQL SLEEP would not do: it only notices a terminate
// when it ends, so it is answered "terminating" rather than "terminated".
const longLoop = "LET i = 0; WHILE ($i < 1000000000) { LET i = $i + 1; } RETURN $i"

// waitForQuery polls ListQueries until a statement with the tag is running. It waits for the
// statement itself, not just its request: the server lists a request as soon as it is admitted,
// with the request line as its text and no language, and fills both in a moment later.
func waitForQuery(t *testing.T, srv *arcadedb.Server, opts arcadedb.ListQueriesOptions) arcadedb.RunningQuery {
	t.Helper()
	deadline := time.Now().Add(15 * time.Second)
	for time.Now().Before(deadline) {
		qs, err := srv.ListQueries(context.Background(), opts)
		if err != nil {
			t.Fatal(err)
		}
		for _, q := range qs {
			if q.Language != "" {
				return q
			}
		}
		time.Sleep(100 * time.Millisecond)
	}
	t.Fatalf("no running query matched %+v", opts)
	return arcadedb.RunningQuery{}
}

func TestListAndTerminateQueriesByTag(t *testing.T) {
	ctx := context.Background()
	srv := newServer(t)
	db := newDatabase(t)
	tag := fmt.Sprintf("e2e running %d", dbCounter.Add(1)) // a space, to cross the rest-of-line parse

	done := make(chan error, 1)
	go func() {
		_, err := db.Command(ctx, arcadedb.SQLScript, longLoop, nil, arcadedb.WithQueryTag(tag))
		done <- err
	}()

	q := waitForQuery(t, srv, arcadedb.ListQueriesOptions{Database: db.Name(), Tag: tag})
	if q.Tag != tag || q.Database != db.Name() || q.Language != "sqlscript" || q.Text != longLoop || q.SessionID != "" {
		t.Fatalf("listed %+v", q)
	}

	results, err := srv.TerminateQueriesByTag(ctx, tag, arcadedb.TerminateOptions{Wait: 5 * time.Second})
	if err != nil {
		t.Fatal(err)
	}
	if len(results) != 1 || results[0].ID != q.ID || results[0].Status != arcadedb.QueryTerminated {
		t.Fatalf("terminate = %+v", results)
	}

	select {
	case err := <-done:
		if !arcadedb.IsQueryTerminated(err) {
			t.Fatalf("the terminated request returned %v, want the 409 IsQueryTerminated matches", err)
		}
		if ae := asArcadeDBError(t, err); ae.Status != 409 || ae.ErrorMessage != "Query terminated" {
			t.Fatalf("got %#v", ae)
		}
	case <-time.After(15 * time.Second):
		t.Fatal("the terminated request did not return")
	}

	// Gone from the list, and terminating it again is "not found".
	if qs, err := srv.ListQueries(ctx, arcadedb.ListQueriesOptions{Tag: tag}); err != nil || len(qs) != 0 {
		t.Fatalf("after terminate: %+v %v", qs, err)
	}
	r, err := srv.TerminateQuery(ctx, q.ID, arcadedb.TerminateOptions{})
	if err != nil || r.Status != arcadedb.QueryNotFound {
		t.Fatalf("terminate again = %+v %v", r, err)
	}
}

func TestTerminateQueryInsideATransaction(t *testing.T) {
	ctx := context.Background()
	srv := newServer(t)
	db := newDatabase(t)
	tag := fmt.Sprintf("e2e-tx-%d", dbCounter.Add(1))

	err := db.Transaction(ctx, func(tx *arcadedb.Database) error {
		done := make(chan error, 1)
		go func() {
			_, err := tx.Command(ctx, arcadedb.SQLScript, longLoop, nil, arcadedb.WithQueryTag(tag))
			done <- err
		}()
		q := waitForQuery(t, srv, arcadedb.ListQueriesOptions{Tag: tag})
		if q.SessionID == "" {
			t.Errorf("a statement in a transaction listed no session: %+v", q)
		}

		txs, err := srv.ListTransactions(ctx)
		if err != nil {
			return err
		}
		i := slices.IndexFunc(txs, func(o arcadedb.OpenTransaction) bool { return o.ID == q.SessionID })
		if i < 0 || !txs[i].Busy || txs[i].Database != db.Name() || !slices.Contains(txs[i].RunningQueries, q.ID) {
			t.Errorf("transactions = %+v, want %s busy running %s", txs, q.SessionID, q.ID)
		}

		r, err := srv.TerminateQuery(ctx, q.ID, arcadedb.TerminateOptions{Wait: 5 * time.Second})
		if err != nil {
			return err
		}
		// A script is a command, so terminating it ends the session it ran in.
		if r.Status != arcadedb.QueryTerminated || r.SessionID != q.SessionID || r.SessionOpen == nil || *r.SessionOpen {
			t.Errorf("terminate = %+v", r)
		}
		return <-done
	})
	if !arcadedb.IsQueryTerminated(err) {
		t.Fatalf("Transaction returned %v, want the terminated statement's 409", err)
	}
}

// Terminating a transaction rolls back what it wrote. The client that owned it is not told at
// commit: the server answers a commit naming a session it no longer has with 204, the same as
// a real commit, so Transaction returns nil for work that is gone. Measured on
// 26.11.1-SNAPSHOT; the READMEs warn about it. Only a statement sent after the terminate
// sees the session is gone (404).
func TestTerminateTransaction(t *testing.T) {
	ctx := context.Background()
	srv := newServer(t)
	db := newDatabase(t)
	mustCommand(t, db, "CREATE DOCUMENT TYPE Doc")

	var session string
	err := db.Transaction(ctx, func(tx *arcadedb.Database) error {
		if _, err := tx.Command(ctx, arcadedb.SQL, "INSERT INTO Doc SET x = 1", nil); err != nil {
			return err
		}
		txs, err := srv.ListTransactions(ctx)
		if err != nil {
			return err
		}
		i := slices.IndexFunc(txs, func(o arcadedb.OpenTransaction) bool { return o.Database == db.Name() })
		if i < 0 {
			t.Fatalf("no open transaction on %s in %+v", db.Name(), txs)
		}
		session = txs[i].ID
		r, err := srv.TerminateTransaction(ctx, session, arcadedb.TerminateOptions{})
		if err != nil {
			return err
		}
		if r.Status != arcadedb.QueryTerminated || r.ID != session {
			t.Errorf("terminate = %+v", r)
		}
		_, err = tx.Command(ctx, arcadedb.SQL, "SELECT 1", nil)
		if ae := asArcadeDBError(t, err); ae.Status != 404 {
			t.Errorf("a statement after the terminate: %#v", ae)
		}
		return nil
	})
	if err != nil {
		t.Fatalf("Transaction = %v; the server's 204 for a commit of a vanished session has changed, update the READMEs", err)
	}
	env, err := db.Query(ctx, arcadedb.SQL, "SELECT count(*) AS n FROM Doc", nil)
	if err != nil {
		t.Fatal(err)
	}
	if n := env.Result[0]["n"]; n != float64(0) {
		t.Fatalf("count = %v, want the terminated transaction's insert rolled back", n)
	}
	r, err := srv.TerminateTransaction(ctx, session, arcadedb.TerminateOptions{})
	if err != nil || r.Status != arcadedb.QueryNotFound {
		t.Fatalf("terminate again = %+v %v", r, err)
	}
}

func TestProgressWithNothingRunning(t *testing.T) {
	db := newDatabase(t)
	p, err := db.Progress(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if p.Result == nil || len(p.Result) != 0 {
		t.Fatalf("progress = %+v", p)
	}
}
