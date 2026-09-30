package arcadedb

import (
	"context"
	"errors"
	"io"
	"net/http"
	"testing"
)

func TestTSWriteSendsTextPlainAndPrecision(t *testing.T) {
	var gotBody, gotCT, gotPrec, gotPath, gotSession string
	var hasPrec bool
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		gotBody, gotCT, gotPath = string(b), r.Header.Get("Content-Type"), r.URL.Path
		gotPrec = r.URL.Query().Get("precision")
		_, hasPrec = r.URL.Query()["precision"]
		gotSession = r.Header.Get("arcadedb-session-id")
		w.WriteHeader(http.StatusNoContent)
	})
	db := srv.DB("d")
	if err := db.TS().Write(context.Background(), "Temp,sensor=a value=1 1700000000", "s"); err != nil {
		t.Fatal(err)
	}
	if gotPath != "/api/v1/ts/d/write" || gotCT != "text/plain" || gotBody != "Temp,sensor=a value=1 1700000000" || gotPrec != "s" {
		t.Fatalf("path=%q ct=%q body=%q precision=%q", gotPath, gotCT, gotBody, gotPrec)
	}
	if err := db.TS().Write(context.Background(), "x", ""); err != nil {
		t.Fatal(err)
	}
	if hasPrec {
		t.Fatal("empty precision must be omitted")
	}
	if gotSession != "" {
		t.Fatal("session header sent outside a transaction")
	}
}

func TestTSWriteErrorIsArcadeDBError(t *testing.T) {
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte(`{"error":"bad line","dropped":1}`))
	})
	err := srv.DB("d").TS().Write(context.Background(), "junk", "")
	var ae *ArcadeDBError
	if !errors.As(err, &ae) || ae.Status != 400 || ae.ErrorMessage != "bad line" {
		t.Fatalf("err = %v", err)
	}
}

func TestTSQueryReturnsScalarsIntact(t *testing.T) {
	var got map[string]any
	srv := fakeServer(t, captureBody(t,
		`{"type":"Temp","columns":["ts","sensor","value"],"rows":[[1700000000000,"a",21.5]],"count":1,"limit":20000,"truncated":true}`, &got, nil))
	out, err := srv.DB("d").TS().Query(context.Background(), map[string]any{"type": "Temp"})
	if err != nil {
		t.Fatal(err)
	}
	if got["type"] != "Temp" {
		t.Fatalf("request body = %v", got)
	}
	rows := out["rows"].([]any)
	row := rows[0].([]any)
	if row[0] != float64(1700000000000) || row[1] != "a" || row[2] != 21.5 {
		t.Fatalf("row = %#v", row)
	}
	// The typed raw model has no truncated field; the map must keep it.
	if out["truncated"] != true || out["limit"] != float64(20000) {
		t.Fatalf("truncated/limit lost: %v", out)
	}
}

func TestTSQueryAggregatedKeepsShape(t *testing.T) {
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, `{"type":"Temp","aggregations":["value_avg"],"buckets":[{"timestamp":1699999980000,"values":[22.0]}],"count":1}`)
	})
	out, err := srv.DB("d").TS().Query(context.Background(), map[string]any{"type": "Temp"})
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := out["buckets"]; !ok {
		t.Fatalf("out = %v", out)
	}
	if _, ok := out["rows"]; ok {
		t.Fatalf("aggregated response misclassified as raw: %v", out)
	}
}

func TestTSLatestOmitsEmptyTag(t *testing.T) {
	var q map[string][]string
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		q = r.URL.Query()
		writeJSON(w, `{"type":"Temp","columns":["ts","value"],"latest":[1700000001000,22.5]}`)
	})
	out, err := srv.DB("d").TS().Latest(context.Background(), "Temp", "")
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := q["tag"]; ok || q["type"][0] != "Temp" {
		t.Fatalf("query = %v", q)
	}
	if l := out["latest"].([]any); l[0] != float64(1700000001000) || l[1] != 22.5 {
		t.Fatalf("latest = %#v", l)
	}
	if _, err := srv.DB("d").TS().Latest(context.Background(), "Temp", "sensor:a"); err != nil {
		t.Fatal(err)
	}
	if q["tag"][0] != "sensor:a" {
		t.Fatalf("query = %v", q)
	}
}

func TestTSLatestEmptySeriesNullLatest(t *testing.T) {
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, `{"type":"Temp","columns":["ts"],"latest":null}`)
	})
	out, err := srv.DB("d").TS().Latest(context.Background(), "Temp", "")
	if err != nil {
		t.Fatal(err)
	}
	if v, ok := out["latest"]; !ok || v != nil {
		t.Fatalf("out = %v", out)
	}
}

func TestTSEmptyBodyIsError(t *testing.T) {
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusOK) })
	if _, err := srv.DB("d").TS().Query(context.Background(), map[string]any{}); err == nil {
		t.Fatal("empty 2xx body must be an error")
	}
	if _, err := srv.DB("d").TS().Latest(context.Background(), "T", ""); err == nil {
		t.Fatal("empty 2xx body must be an error")
	}
	if _, err := srv.DB("d").Grafana().Query(context.Background(), map[string]any{}); err == nil {
		t.Fatal("empty 2xx body must be an error")
	}
}

func TestTSQuerySendsSession(t *testing.T) {
	var hdr http.Header
	var got map[string]any
	srv := fakeServer(t, captureBody(t, `{"type":"T","rows":[]}`, &got, &hdr))
	db := srv.DB("d")
	db.sessionID = "S1"
	if _, err := db.TS().Query(context.Background(), map[string]any{"type": "T"}); err != nil {
		t.Fatal(err)
	}
	if hdr.Get("arcadedb-session-id") != "S1" {
		t.Fatalf("session header = %q", hdr.Get("arcadedb-session-id"))
	}
}

func TestGrafanaQueryReturnsRawJSON(t *testing.T) {
	var got map[string]any
	srv := fakeServer(t, captureBody(t,
		`{"results":{"A":{"frames":[{"schema":{"fields":[{"name":"ts","type":"time"}]},"data":{"values":[[1700000000000,1700000001000],["a","a"],[21.5,22.5]]}}]}}}`, &got, nil))
	out, err := srv.DB("d").Grafana().Query(context.Background(), map[string]any{"targets": []any{map[string]any{"refId": "A", "type": "Temp"}}})
	if err != nil {
		t.Fatal(err)
	}
	if got["targets"] == nil {
		t.Fatalf("request body = %v", got)
	}
	frame := out["results"].(map[string]any)["A"].(map[string]any)["frames"].([]any)[0].(map[string]any)
	vals := frame["data"].(map[string]any)["values"].([]any)
	if vals[0].([]any)[0] != float64(1700000000000) || vals[2].([]any)[1] != 22.5 {
		t.Fatalf("values = %#v", vals)
	}
}
