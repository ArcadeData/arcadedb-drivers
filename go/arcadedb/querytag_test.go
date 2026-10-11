package arcadedb

import (
	"context"
	"io"
	"net/http"
	"strings"
	"sync"
	"testing"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

const queryTagHeader = "X-ArcadeDB-Query-Tag"

// tagRecorder records the query-tag header of every request, keyed by the first path
// segment after /api/v1/ (query, command, begin, commit, rollback, batch), and answers each
// the way the endpoint would on success.
type tagRecorder struct {
	mu   sync.Mutex
	seen []tagSeen
}

type tagSeen struct {
	op      string
	present bool
	value   string
}

func (rec *tagRecorder) handler(w http.ResponseWriter, r *http.Request) {
	_, _ = io.Copy(io.Discard, r.Body)
	op := strings.Split(strings.TrimPrefix(r.URL.Path, "/api/v1/"), "/")[0]
	_, present := r.Header[http.CanonicalHeaderKey(queryTagHeader)]
	rec.mu.Lock()
	rec.seen = append(rec.seen, tagSeen{op, present, r.Header.Get(queryTagHeader)})
	rec.mu.Unlock()
	switch {
	case op == "begin":
		w.Header().Set("arcadedb-session-id", "s1")
		w.WriteHeader(http.StatusNoContent)
	case op == "commit" || op == "rollback":
		w.WriteHeader(http.StatusNoContent)
	case r.Header.Get("Accept") == "application/x-ndjson" && op == "batch":
		w.Header().Set("Content-Type", "application/x-ndjson")
		_, _ = io.WriteString(w, "{\"summary\":{}}\n")
	case r.Header.Get("Accept") == "application/x-ndjson":
		w.Header().Set("Content-Type", "application/x-ndjson")
		_, _ = io.WriteString(w, "{\"stats\":{}}\n")
	default:
		writeJSON(w, `{"result":[],"limit":-1,"returned":0,"truncated":false}`)
	}
}

func (rec *tagRecorder) calls() []tagSeen {
	rec.mu.Lock()
	defer rec.mu.Unlock()
	return append([]tagSeen(nil), rec.seen...)
}

func newTagRecorder(t *testing.T) (*tagRecorder, *Database) {
	rec := &tagRecorder{}
	return rec, fakeServer(t, rec.handler).DB("d")
}

func drainSeq2[K, V any](seq func(func(K, V) bool)) {
	for range seq {
	}
}

func TestQueryTagSentOnEveryTaggableCall(t *testing.T) {
	ctx := context.Background()
	calls := map[string]func(db *Database) error{
		"query": func(db *Database) error {
			_, err := db.Query(ctx, SQL, "select", nil, WithQueryTag("nightly"))
			return err
		},
		"command": func(db *Database) error {
			_, err := db.Command(ctx, SQL, "select", nil, WithQueryTag("nightly"))
			return err
		},
		"query stream": func(db *Database) error {
			drainSeq2(db.QueryStream(ctx, SQL, "select", nil, WithQueryTag("nightly")))
			return nil
		},
		"command stream": func(db *Database) error {
			drainSeq2(db.CommandStream(ctx, SQL, "select", nil, WithQueryTag("nightly")))
			return nil
		},
		"batch": func(db *Database) error {
			_, err := db.BatchLoad(ctx, nil, nil, &generated.ExecuteBatchParams{XArcadeDBQueryTag: ptr("nightly")})
			return err
		},
		"batch stream": func(db *Database) error {
			drainSeq2(db.BatchLoadStream(ctx, nil, nil, &generated.ExecuteBatchParams{XArcadeDBQueryTag: ptr("nightly")}))
			return nil
		},
	}
	for name, call := range calls {
		t.Run(name, func(t *testing.T) {
			rec, db := newTagRecorder(t)
			if err := call(db); err != nil {
				t.Fatal(err)
			}
			got := rec.calls()
			if len(got) != 1 || got[0].value != "nightly" {
				t.Fatalf("seen = %+v", got)
			}
		})
	}
}

func TestQueryTagNotSentWhenUnsetOrEmpty(t *testing.T) {
	ctx := context.Background()
	rec, db := newTagRecorder(t)
	if _, err := db.Query(ctx, SQL, "select", nil); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Query(ctx, SQL, "select", nil, WithQueryTag("")); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Command(ctx, SQL, "select", nil, WithQueryTag("")); err != nil {
		t.Fatal(err)
	}
	drainSeq2(db.QueryStream(ctx, SQL, "select", nil))
	if _, err := db.BatchLoad(ctx, nil, nil, &generated.ExecuteBatchParams{XArcadeDBQueryTag: ptr("")}); err != nil {
		t.Fatal(err)
	}
	drainSeq2(db.BatchLoadStream(ctx, nil, nil, &generated.ExecuteBatchParams{XArcadeDBQueryTag: ptr("")}))
	if err := db.Transaction(ctx, func(*Database) error { return nil }, WithQueryTag("")); err != nil {
		t.Fatal(err)
	}
	for _, s := range rec.calls() {
		if s.present {
			t.Fatalf("%s sent the header: %+v", s.op, rec.calls())
		}
	}
}

// The tag goes on begin only: the server applies it to every statement of the session that
// carries no tag of its own, so commit, rollback and untagged statements send none, while a
// statement with its own tag still sends it.
func TestQueryTagOnTransactionBeginOnly(t *testing.T) {
	ctx := context.Background()
	rec, db := newTagRecorder(t)
	err := db.Transaction(ctx, func(tx *Database) error {
		if _, err := tx.Query(ctx, SQL, "select", nil); err != nil {
			return err
		}
		_, err := tx.Command(ctx, SQL, "select", nil, WithQueryTag("own"))
		return err
	}, WithQueryTag("session-tag"))
	if err != nil {
		t.Fatal(err)
	}
	want := []tagSeen{
		{"begin", true, "session-tag"},
		{"query", false, ""},
		{"command", true, "own"},
		{"commit", false, ""},
	}
	got := rec.calls()
	if len(got) != len(want) {
		t.Fatalf("seen = %+v", got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("call %d = %+v, want %+v (all: %+v)", i, got[i], want[i], got)
		}
	}
}

func TestQueryTagDoesNotModifyCallerBatchParams(t *testing.T) {
	_, db := newTagRecorder(t)
	p := &generated.ExecuteBatchParams{XArcadeDBQueryTag: ptr("")}
	if _, err := db.BatchLoad(context.Background(), nil, nil, p); err != nil {
		t.Fatal(err)
	}
	if p.XArcadeDBQueryTag == nil || *p.XArcadeDBQueryTag != "" {
		t.Fatalf("params modified: %+v", p)
	}
}
