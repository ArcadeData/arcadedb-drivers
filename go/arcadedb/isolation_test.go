package arcadedb

import (
	"context"
	"errors"
	"io"
	"net/http"
	"testing"
)

// beginBodies serves a transaction and records every /begin request body (issue #152).
func beginBodies(t *testing.T) (*Database, *[]string) {
	var bodies []string
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/v1/begin/d":
			b, _ := io.ReadAll(r.Body)
			bodies = append(bodies, string(b))
			w.Header().Set("arcadedb-session-id", "s1")
			w.WriteHeader(http.StatusNoContent)
		default:
			w.WriteHeader(http.StatusNoContent)
		}
	})
	return srv.DB("d"), &bodies
}

func TestTransactionSendsIsolationLevel(t *testing.T) {
	db, bodies := beginBodies(t)
	for _, level := range []IsolationLevel{RepeatableRead, ReadCommitted} {
		if err := db.Transaction(context.Background(), func(*Database) error { return nil }, WithIsolationLevel(level)); err != nil {
			t.Fatal(err)
		}
	}
	want := []string{`{"isolationLevel":"REPEATABLE_READ"}`, `{"isolationLevel":"READ_COMMITTED"}`}
	if len(*bodies) != 2 || (*bodies)[0] != want[0] || (*bodies)[1] != want[1] {
		t.Fatalf("begin bodies = %q, want %q", *bodies, want)
	}
}

func TestTransactionWithoutIsolationLevelSendsNoLevel(t *testing.T) {
	db, bodies := beginBodies(t)
	if err := db.Transaction(context.Background(), func(*Database) error { return nil }); err != nil {
		t.Fatal(err)
	}
	if len(*bodies) != 1 || (*bodies)[0] != `{}` {
		t.Fatalf("begin bodies = %q, want [{}]", *bodies)
	}
}

func TestTransactionRefusesUnknownIsolationLevelUnsent(t *testing.T) {
	db, bodies := beginBodies(t)
	ran := false
	err := db.Transaction(context.Background(), func(*Database) error { ran = true; return nil }, WithIsolationLevel("SERIALIZABLE"))
	if err == nil || ran || len(*bodies) != 0 {
		t.Fatalf("err = %v, ran = %v, begins = %d", err, ran, len(*bodies))
	}
}

func TestTransactionRefusesEmptyIsolationLevelUnsent(t *testing.T) {
	db, bodies := beginBodies(t)
	err := db.Transaction(context.Background(), func(*Database) error { return nil }, WithIsolationLevel(""))
	if !errors.Is(err, ErrInvalidIsolationLevel) || len(*bodies) != 0 {
		t.Fatalf("err = %v, begins = %d", err, len(*bodies))
	}
}
