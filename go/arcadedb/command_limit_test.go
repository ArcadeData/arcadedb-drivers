package arcadedb

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"testing"
)

// WithLimit goes to Command and CommandStream as well as to Query (issue #151). These
// assignments are the compile-time half of that: they stop compiling if WithLimit stops
// being either kind of option.
var (
	_ QueryOption   = WithLimit(1)
	_ CommandOption = WithLimit(1)
)

func TestCommandSendsLimitWhenGiven(t *testing.T) {
	var got map[string]any
	srv := fakeServer(t, captureBody(t, `{}`, &got, nil))
	if _, err := srv.DB("d").Command(context.Background(), SQL, "select from V", nil, WithLimit(-1)); err != nil {
		t.Fatal(err)
	}
	if got["limit"] != float64(-1) {
		t.Fatalf("limit = %v, body = %v", got["limit"], got)
	}
}

func TestCommandSendsLimitInsideATransaction(t *testing.T) {
	var got map[string]any
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api/v1/begin/d":
			w.Header().Set("arcadedb-session-id", "AS-1")
			w.WriteHeader(http.StatusNoContent)
		case "/api/v1/commit/d":
			w.WriteHeader(http.StatusNoContent)
		default:
			captureBody(t, `{}`, &got, nil)(w, r)
		}
	})
	err := srv.DB("d").Transaction(context.Background(), func(tx *Database) error {
		_, err := tx.Command(context.Background(), SQL, "select from V", nil, WithLimit(50000))
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	if got["limit"] != float64(50000) {
		t.Fatalf("limit = %v, body = %v", got["limit"], got)
	}
}

func TestCommandStreamSendsLimitWhenGiven(t *testing.T) {
	var got map[string]any
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		if err := json.Unmarshal(b, &got); err != nil {
			t.Errorf("request body not JSON: %v", err)
		}
		w.Header().Set("Content-Type", "application/x-ndjson")
		_, _ = io.WriteString(w, "{\"stats\":{\"limit\":-1,\"returned\":0,\"truncated\":false}}\n")
	})
	for _, err := range srv.DB("d").CommandStream(context.Background(), SQL, "select from V", nil, WithLimit(-1)) {
		if err != nil {
			t.Fatal(err)
		}
	}
	if got["limit"] != float64(-1) {
		t.Fatalf("limit = %v, body = %v", got["limit"], got)
	}
}
