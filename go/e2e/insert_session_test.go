package e2e

import (
	"context"
	"errors"
	"testing"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb"
)

func insertSchema(t *testing.T) *arcadedb.Database {
	t.Helper()
	db := newDatabase(t)
	mustCommand(t, db, "CREATE DOCUMENT TYPE Person IF NOT EXISTS")
	return db
}

func people(names ...string) []map[string]any {
	out := make([]map[string]any, len(names))
	for i, n := range names {
		out[i] = map[string]any{"name": n}
	}
	return out
}

// The point of the control frames: the caller sees each acknowledgement and only then
// decides whether to commit. Nothing is durable until it does.
func TestInsertSessionCommitAfterAcks(t *testing.T) {
	ctx := context.Background()
	db := insertSchema(t)

	var seen []int64
	s, err := db.InsertSession(ctx, arcadedb.WithInsertTargetType("Person"),
		arcadedb.WithOnInsertAck(func(a arcadedb.InsertAck) { seen = append(seen, a.ChunkSeq) }))
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	if s.SessionID() == "" || s.TransactionMode() != "per_stream" {
		t.Fatalf("session id %q mode %q", s.SessionID(), s.TransactionMode())
	}
	if ack, err := s.SendChunk(ctx, people("a", "b")); err != nil || ack.Inserted != 2 {
		t.Fatalf("ack = %+v, %v", ack, err)
	}
	if ack, err := s.SendChunk(ctx, people("c")); err != nil || ack.Inserted != 1 {
		t.Fatalf("ack = %+v, %v", ack, err)
	}
	if len(seen) != 2 || seen[0] != 1 || seen[1] != 2 {
		t.Fatalf("callback saw %v", seen)
	}
	if n := count(t, db, "Person"); n != 0 {
		t.Fatalf("%v rows visible before commit", n)
	}
	res, err := s.Commit(ctx)
	if err != nil || res.Outcome != "commit" || res.Summary.Inserted != 3 {
		t.Fatalf("result = %+v, %v", res, err)
	}
	if n := count(t, db, "Person"); n != 3 {
		t.Fatalf("%v rows after commit, want 3", n)
	}
}

func TestInsertSessionRollback(t *testing.T) {
	ctx := context.Background()
	db := insertSchema(t)
	s, err := db.InsertSession(ctx, arcadedb.WithInsertTargetType("Person"))
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	if _, err := s.SendChunk(ctx, people("a", "b")); err != nil {
		t.Fatal(err)
	}
	if res, err := s.Rollback(ctx); err != nil || res.Outcome != "rollback" {
		t.Fatalf("result = %+v, %v", res, err)
	}
	if n := count(t, db, "Person"); n != 0 {
		t.Fatalf("%v rows after rollback", n)
	}
}

// A session left open by a defer is rolled back, never left holding a transaction.
func TestInsertSessionCloseRollsBack(t *testing.T) {
	ctx := context.Background()
	db := insertSchema(t)
	s, err := db.InsertSession(ctx, arcadedb.WithInsertTargetType("Person"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := s.SendChunk(ctx, people("a")); err != nil {
		t.Fatal(err)
	}
	_ = s.Close()
	if n := count(t, db, "Person"); n != 0 {
		t.Fatalf("%v rows after Close", n)
	}
}

// The session joins the transaction of the handle Transaction gives the callback; that
// transaction's commit is what makes the rows durable.
func TestInsertSessionJoinsTransaction(t *testing.T) {
	ctx := context.Background()
	db := insertSchema(t)

	err := db.Transaction(ctx, func(tx *arcadedb.Database) error {
		s, err := tx.InsertSession(ctx, arcadedb.WithInsertTargetType("Person"), arcadedb.WithJoinCurrentTransaction())
		if err != nil {
			return err
		}
		defer s.Close()
		if s.TransactionMode() != "none" || s.ExternalTransactionID() == "" {
			t.Errorf("mode %q external %q", s.TransactionMode(), s.ExternalTransactionID())
		}
		if ack, err := s.SendChunk(ctx, people("a", "b")); err != nil || ack.Inserted != 2 {
			t.Errorf("ack = %+v, %v", ack, err)
		}
		res, err := s.Commit(ctx)
		if err != nil {
			return err
		}
		if res.Outcome != arcadedb.InsertOutcomeDetached || !res.Summary.ExternalTransaction {
			t.Errorf("result = %+v", res)
		}
		if n := count(t, db, "Person"); n != 0 {
			t.Errorf("%v rows visible before the transaction commits", n)
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if n := count(t, db, "Person"); n != 2 {
		t.Fatalf("%v rows after the transaction, want 2", n)
	}

	// And the transaction's rollback undoes what the joined session wrote.
	sentinel := errors.New("undo")
	err = db.Transaction(ctx, func(tx *arcadedb.Database) error {
		s, err := tx.InsertSession(ctx, arcadedb.WithInsertTargetType("Person"), arcadedb.WithJoinCurrentTransaction())
		if err != nil {
			return err
		}
		defer s.Close()
		if _, err := s.SendChunk(ctx, people("x", "y")); err != nil {
			return err
		}
		if _, err := s.Commit(ctx); err != nil {
			return err
		}
		return sentinel
	})
	if !errors.Is(err, sentinel) {
		t.Fatal(err)
	}
	if n := count(t, db, "Person"); n != 2 {
		t.Fatalf("%v rows after the rolled-back transaction, want 2", n)
	}
}

func TestInsertSessionJoinWithoutTransaction(t *testing.T) {
	db := insertSchema(t)
	if _, err := db.InsertSession(context.Background(), arcadedb.WithJoinCurrentTransaction()); !errors.Is(err, arcadedb.ErrNoTransactionToJoin) {
		t.Fatalf("err = %v", err)
	}
}

// A chunk refused as a whole surfaces as an error and leaves the session usable, its
// sequence number unspent; a row the server cannot apply is tallied, not refused.
func TestInsertSessionRefusedChunk(t *testing.T) {
	ctx := context.Background()
	db := insertSchema(t)
	s, err := db.InsertSession(ctx, arcadedb.WithInsertTargetType("Person"))
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()

	_, err = s.SendChunk(ctx, people("a", "b", "c", "d", "e"))
	var serr *arcadedb.InsertSessionError
	if !errors.As(err, &serr) {
		t.Fatalf("err = %v", err)
	}
	if s.LastChunkSeq() != 0 || !s.IsOpen() {
		t.Fatalf("refused chunk spent a sequence number or closed the session: seq %d open %v", s.LastChunkSeq(), s.IsOpen())
	}

	ack, err := s.SendChunk(ctx, []map[string]any{{"name": "a"}, {"@class": "NoSuchType"}})
	if err != nil {
		t.Fatal(err)
	}
	if ack.ChunkSeq != 1 || ack.Inserted != 1 || ack.Failed != 1 {
		t.Fatalf("ack = %+v", ack)
	}
	if _, err := s.Commit(ctx); err != nil {
		t.Fatal(err)
	}
	if n := count(t, db, "Person"); n != 1 {
		t.Fatalf("%v rows, want 1", n)
	}
}

// A per_batch chunk whose own transaction fails to commit (here on a unique index) is
// acknowledged, not refused, and the server keeps its watermark: the client must not spend
// the sequence number, and the next chunk replaces that attempt under the same one.
func TestInsertSessionWholeChunkFailure(t *testing.T) {
	ctx := context.Background()
	db := newDatabase(t)
	mustCommand(t, db, "CREATE DOCUMENT TYPE Account IF NOT EXISTS")
	mustCommand(t, db, "CREATE PROPERTY Account.name IF NOT EXISTS STRING")
	mustCommand(t, db, "CREATE INDEX IF NOT EXISTS ON Account (name) UNIQUE")
	mustCommand(t, db, "INSERT INTO Account SET name = 'taken'")

	s, err := db.InsertSession(ctx, arcadedb.WithInsertTargetType("Account"),
		arcadedb.WithInsertTransactionMode(arcadedb.InsertPerBatch))
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()

	ack, err := s.SendChunk(ctx, people("taken"))
	if err != nil {
		t.Fatal(err)
	}
	if !ack.WholeChunkFailed || ack.Failed != 1 || ack.Received != 1 || s.LastChunkSeq() != 0 {
		t.Fatalf("ack = %+v, last seq %d", ack, s.LastChunkSeq())
	}

	ack, err = s.SendChunk(ctx, people("fresh"))
	if err != nil {
		t.Fatal(err)
	}
	if ack.ChunkSeq != 1 || ack.Inserted != 1 || ack.WholeChunkFailed || ack.Replay {
		t.Fatalf("replay ack = %+v", ack)
	}
	if _, err := s.Commit(ctx); err != nil {
		t.Fatal(err)
	}
	if n := count(t, db, "Account"); n != 2 {
		t.Fatalf("%v rows, want 2", n)
	}
}
