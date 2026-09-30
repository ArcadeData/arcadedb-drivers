package arcadedb

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"sort"
	"testing"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

// captureBody serves an empty envelope and records the request body and headers.
func captureBody(t *testing.T, resp string, got *map[string]any, hdr *http.Header) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		m := map[string]any{}
		if err := json.Unmarshal(b, &m); err != nil {
			t.Errorf("request body not JSON: %v", err)
		}
		*got = m
		if hdr != nil {
			*hdr = r.Header.Clone()
		}
		writeJSON(w, resp)
	}
}

func keys(m map[string]any) []string {
	var out []string
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func TestQueryBodyOmitsUnsetFields(t *testing.T) {
	var got map[string]any
	srv := fakeServer(t, captureBody(t, `{}`, &got, nil))
	if _, err := srv.DB("d").Query(context.Background(), SQL, "select 1", nil); err != nil {
		t.Fatal(err)
	}
	k := keys(got)
	if len(k) != 2 || k[0] != "command" || k[1] != "language" {
		t.Fatalf("body keys = %v, want [command language]", k)
	}
	if got["language"] != "sql" {
		t.Fatalf("language = %v", got["language"])
	}
}

func TestQueryBodyCarriesParamsAndLimit(t *testing.T) {
	var got map[string]any
	srv := fakeServer(t, captureBody(t, `{}`, &got, nil))
	_, err := srv.DB("d").Query(context.Background(), Cypher, "q", map[string]any{"a": 1}, WithLimit(-1))
	if err != nil {
		t.Fatal(err)
	}
	if got["limit"] != float64(-1) {
		t.Fatalf("limit = %v", got["limit"])
	}
	if p, _ := got["params"].(map[string]any); p["a"] != float64(1) {
		t.Fatalf("params = %v", got["params"])
	}
	if _, ok := got["serializer"]; ok {
		t.Fatal("serializer must never be sent")
	}
}

func TestCommandNeverSendsLimit(t *testing.T) {
	var got map[string]any
	srv := fakeServer(t, captureBody(t, `{}`, &got, nil))
	if _, err := srv.DB("d").Command(context.Background(), SQL, "create vertex type V", nil); err != nil {
		t.Fatal(err)
	}
	if _, ok := got["limit"]; ok {
		t.Fatal("command sent limit")
	}
	if got["language"] != "sql" || got["command"] != "create vertex type V" {
		t.Fatalf("body = %v", got)
	}
}

func TestEnvelopeDefaults(t *testing.T) {
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) { writeJSON(w, `{}`) })
	env, err := srv.DB("d").Query(context.Background(), SQL, "x", nil)
	if err != nil {
		t.Fatal(err)
	}
	if env.Result == nil || len(env.Result) != 0 || env.Limit != -1 || env.Returned != 0 || env.Truncated {
		t.Fatalf("env = %+v", env)
	}
}

func TestEnvelopeReadsTruncated(t *testing.T) {
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, `{"result":[{"a":1}],"limit":1,"returned":1,"truncated":true}`)
	})
	env, err := srv.DB("d").Command(context.Background(), SQL, "x", nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(env.Result) != 1 || env.Result[0]["a"] != float64(1) || env.Limit != 1 || env.Returned != 1 || !env.Truncated {
		t.Fatalf("env = %+v", env)
	}
}

func TestEnvelopeRejectsGraphShape(t *testing.T) {
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, `{"result":{"vertices":[],"edges":[]}}`)
	})
	_, err := srv.DB("d").Query(context.Background(), SQL, "x", nil)
	var ae *ArcadeDBError
	if !errors.As(err, &ae) || ae.Status != 200 {
		t.Fatalf("err = %v, want *ArcadeDBError status 200", err)
	}
}

func TestToEnvelopeRejectsGraphShapeDirectly(t *testing.T) {
	var qr generated.QueryResponse
	if err := json.Unmarshal([]byte(`{"result":{"vertices":[],"edges":[]},"limit":1}`), &qr); err != nil {
		t.Fatal(err)
	}
	if _, err := toEnvelope(&qr); err == nil {
		t.Fatal("expected error")
	}
}

func TestQueryNon2xxIsArcadeDBError(t *testing.T) {
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(400)
		_, _ = w.Write([]byte(`{"error":"bad"}`))
	})
	_, err := srv.DB("d").Command(context.Background(), SQL, "x", nil)
	var ae *ArcadeDBError
	if !errors.As(err, &ae) || ae.Status != 400 || ae.ErrorMessage != "bad" {
		t.Fatalf("err = %v", err)
	}
}

func TestQueryOutsideTransactionSendsNoSessionHeader(t *testing.T) {
	var got map[string]any
	var hdr http.Header
	srv := fakeServer(t, captureBody(t, `{}`, &got, &hdr))
	if _, err := srv.DB("d").Query(context.Background(), SQL, "x", nil); err != nil {
		t.Fatal(err)
	}
	if _, ok := hdr["Arcadedb-Session-Id"]; ok {
		t.Fatalf("session header sent: %v", hdr)
	}
}

func TestQuerySendsSessionHeaderInsideTransaction(t *testing.T) {
	var got map[string]any
	var hdr http.Header
	srv := fakeServer(t, captureBody(t, `{}`, &got, &hdr))
	db := srv.DB("d")
	db.sessionID = "AS-1"
	if _, err := db.Query(context.Background(), SQL, "x", nil); err != nil {
		t.Fatal(err)
	}
	if hdr.Get("arcadedb-session-id") != "AS-1" {
		t.Fatalf("hdr = %v", hdr)
	}
}

func TestDecodeBodyTreatsNullLikeEmpty(t *testing.T) {
	for _, b := range []string{"null", "  null\n", ""} {
		out, err := decodeBody[generated.QueryResponse](nil, []byte(b))
		if out != nil || err != nil {
			t.Fatalf("%q -> %v, %v", b, out, err)
		}
	}
}
