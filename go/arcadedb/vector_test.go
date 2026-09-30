package arcadedb

import (
	"context"
	"errors"
	"net/http"
	"testing"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

func TestVectorSearchPassesRequestThrough(t *testing.T) {
	var got map[string]any
	var hdr http.Header
	srv := fakeServer(t, captureBody(t, `{"count":0,"results":[]}`, &got, &hdr))
	_, err := srv.DB("d").Vector().Search(context.Background(),
		generated.VectorSearchRequest{IndexName: "idx", QueryVector: []float32{1, 2}})
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := got["k"]; ok {
		t.Fatalf("unset K must be omitted, body = %v", got)
	}
	if got["indexName"] != "idx" {
		t.Fatalf("body = %v", got)
	}
	if hdr.Get("arcadedb-session-id") != "" {
		t.Fatal("session header sent outside a transaction")
	}
}

func TestVectorSearchSendsSession(t *testing.T) {
	var got map[string]any
	var hdr http.Header
	srv := fakeServer(t, captureBody(t, `{"count":0,"results":[]}`, &got, &hdr))
	db := srv.DB("d")
	db.sessionID = "S1"
	if _, err := db.Vector().Search(context.Background(),
		generated.VectorSearchRequest{IndexName: "idx", QueryVector: []float32{1}}); err != nil {
		t.Fatal(err)
	}
	if hdr.Get("arcadedb-session-id") != "S1" {
		t.Fatalf("session header = %q", hdr.Get("arcadedb-session-id"))
	}
}

// vectorCalls runs each of the three methods against db, discarding the response.
var vectorCalls = map[string]func(context.Context, *Vector) error{
	"search": func(ctx context.Context, v *Vector) error {
		_, err := v.Search(ctx, generated.VectorSearchRequest{IndexName: "i", QueryVector: []float32{1}})
		return err
	},
	"hybrid": func(ctx context.Context, v *Vector) error {
		_, err := v.Hybrid(ctx, generated.HybridSearchRequest{VectorIndexName: "i", QueryVector: []float32{1}})
		return err
	},
	"fulltext": func(ctx context.Context, v *Vector) error {
		_, err := v.Fulltext(ctx, generated.FullTextSearchRequest{QueryText: "q"})
		return err
	},
}

func TestVectorAllMethodsSendSession(t *testing.T) {
	for name, call := range vectorCalls {
		t.Run(name, func(t *testing.T) {
			var got map[string]any
			var hdr http.Header
			srv := fakeServer(t, captureBody(t, `{"count":0,"results":[]}`, &got, &hdr))
			db := srv.DB("d")
			db.sessionID = "S1"
			if err := call(context.Background(), db.Vector()); err != nil {
				t.Fatal(err)
			}
			if hdr.Get("arcadedb-session-id") != "S1" {
				t.Fatalf("session header = %q", hdr.Get("arcadedb-session-id"))
			}
		})
	}
}

func TestVectorAllMethodsEmptyBodyIsError(t *testing.T) {
	for name, call := range vectorCalls {
		t.Run(name, func(t *testing.T) {
			srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusOK) })
			if err := call(context.Background(), srv.DB("d").Vector()); err == nil {
				t.Fatal("empty 2xx body must be an error")
			}
		})
	}
}

func TestHybridReturnsTruncated(t *testing.T) {
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, `{"count":0,"truncated":true,"fused":false,"results":[]}`)
	})
	resp, err := srv.DB("d").Vector().Hybrid(context.Background(),
		generated.HybridSearchRequest{VectorIndexName: "i", QueryVector: []float32{1}})
	if err != nil {
		t.Fatal(err)
	}
	if !resp.Truncated {
		t.Fatal("hybrid truncated lost")
	}
}

func TestVectorSearchReturnsWholeResponse(t *testing.T) {
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, `{"count":1,"truncated":true,"candidateLimit":40,"indexName":"idx","scoring":"distance_lower_is_better:COSINE","results":[{"rid":"#1:0","distance":0.5,"properties":{}}]}`)
	})
	resp, err := srv.DB("d").Vector().Search(context.Background(),
		generated.VectorSearchRequest{IndexName: "idx", QueryVector: []float32{1}})
	if err != nil {
		t.Fatal(err)
	}
	if resp.Count != 1 || resp.CandidateLimit != 40 || len(resp.Results) != 1 || resp.Scoring == "" {
		t.Fatalf("resp = %+v", resp)
	}
	if !resp.Truncated {
		t.Fatalf("truncated lost: %v", resp.Truncated)
	}
}

func TestVectorNon2xx(t *testing.T) {
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte(`{"error":"bad","detail":"nope"}`))
	})
	db := srv.DB("d").Vector()
	ctx := context.Background()
	var ae *ArcadeDBError
	if _, err := db.Search(ctx, generated.VectorSearchRequest{}); !errors.As(err, &ae) || ae.Status != 400 {
		t.Fatalf("search err = %v", err)
	}
	if _, err := db.Hybrid(ctx, generated.HybridSearchRequest{}); !errors.As(err, &ae) {
		t.Fatalf("hybrid err = %v", err)
	}
	if _, err := db.Fulltext(ctx, generated.FullTextSearchRequest{}); !errors.As(err, &ae) {
		t.Fatalf("fulltext err = %v", err)
	}
}

func TestVectorEmptyBodyIsError(t *testing.T) {
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusOK) })
	if _, err := srv.DB("d").Vector().Search(context.Background(), generated.VectorSearchRequest{}); err == nil {
		t.Fatal("empty 2xx body must be an error")
	}
}

func TestHybridAndFulltextRoutes(t *testing.T) {
	var paths []string
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		paths = append(paths, r.Method+" "+r.URL.Path)
		writeJSON(w, `{"count":0,"results":[],"fused":false}`)
	})
	v := srv.DB("d").Vector()
	ctx := context.Background()
	if _, err := v.Hybrid(ctx, generated.HybridSearchRequest{VectorIndexName: "i", QueryVector: []float32{1}}); err != nil {
		t.Fatal(err)
	}
	if _, err := v.Fulltext(ctx, generated.FullTextSearchRequest{QueryText: "java"}); err != nil {
		t.Fatal(err)
	}
	want := []string{"POST /api/v1/vector/d/hybrid", "POST /api/v1/vector/d/fulltext"}
	if len(paths) != 2 || paths[0] != want[0] || paths[1] != want[1] {
		t.Fatalf("paths = %v", paths)
	}
}
