package arcadedb

import (
	"context"
	"net/http"
	"testing"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

func TestPromQLSeriesSendsMatchArray(t *testing.T) {
	var raw string
	var q map[string][]string
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		raw, q = r.URL.RawQuery, r.URL.Query()
		writeJSON(w, `{"status":"success","data":[{"__name__":"up","job":"a"}]}`)
	})
	out, err := srv.DB("d").PromQL().Series(context.Background(),
		generated.PromQLSeriesParams{Match: []string{`up{job="a"}`, "cpu"}})
	if err != nil {
		t.Fatal(err)
	}
	if m := q["match[]"]; len(m) != 2 || m[0] != `up{job="a"}` || m[1] != "cpu" {
		t.Fatalf("match[] = %v (raw %q)", m, raw)
	}
	if len(out.Data) != 1 || out.Data[0]["job"] != "a" {
		t.Fatalf("out = %+v", out)
	}
}

func TestPromQLQueryPassesParams(t *testing.T) {
	var q map[string][]string
	var path, session string
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		q, path, session = r.URL.Query(), r.URL.Path, r.Header.Get("arcadedb-session-id")
		writeJSON(w, `{"status":"success","data":{"resultType":"vector","result":[{"metric":{"__name__":"up"},"value":[1700000000,"1"]}]}}`)
	})
	db := srv.DB("d")
	db.sessionID = "S1"
	tm := "1700000000"
	out, err := db.PromQL().Query(context.Background(), generated.PromQLQueryParams{Query: "up", Time: &tm})
	if err != nil {
		t.Fatal(err)
	}
	if path == "" {
		t.Fatal("no request seen")
	}
	if q["query"][0] != "up" || q["time"][0] != "1700000000" || session != "S1" {
		t.Fatalf("query=%v session=%q", q, session)
	}
	if out.Data.ResultType != generated.PromQLDataResponseDataResultType("vector") {
		t.Fatalf("out = %+v", out)
	}
}

func TestPromQLQueryRangeAndLabels(t *testing.T) {
	var q map[string][]string
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		q = r.URL.Query()
		if q["step"] == nil {
			writeJSON(w, `{"status":"success","data":["__name__","job"]}`)
			return
		}
		writeJSON(w, `{"status":"success","data":{"resultType":"matrix","result":[]}}`)
	})
	ctx := context.Background()
	if _, err := srv.DB("d").PromQL().QueryRange(ctx, generated.PromQLQueryRangeParams{Query: "up", Start: "1", End: "2", Step: "15"}); err != nil {
		t.Fatal(err)
	}
	if q["start"][0] != "1" || q["end"][0] != "2" || q["step"][0] != "15" {
		t.Fatalf("query = %v", q)
	}
	l, err := srv.DB("d").PromQL().Labels(ctx)
	if err != nil || len(l.Data) != 2 {
		t.Fatalf("labels = %+v err=%v", l, err)
	}
}

func TestPromQLErrorAndEmptyBody(t *testing.T) {
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte(`{"status":"error","errorType":"bad_data","error":"parse"}`))
	})
	if _, err := srv.DB("d").PromQL().Query(context.Background(), generated.PromQLQueryParams{Query: "("}); err == nil {
		t.Fatal("want error")
	} else if ae, ok := err.(*ArcadeDBError); !ok || ae.Status != 400 {
		t.Fatalf("err = %v", err)
	}
	empty := fakeServer(t, func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusOK) })
	if _, err := empty.DB("d").PromQL().Labels(context.Background()); err == nil {
		t.Fatal("empty 2xx body must be an error")
	}
}
