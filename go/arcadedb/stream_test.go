package arcadedb

import (
	"context"
	"errors"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"
)

func ndjsonBody(body string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/x-ndjson")
		_, _ = io.WriteString(w, body)
	}
}

func drain(t *testing.T, srv *Server) ([]StreamEvent, error) {
	t.Helper()
	var evs []StreamEvent
	for ev, err := range srv.DB("d").QueryStream(context.Background(), SQL, "select", nil) {
		if err != nil {
			return evs, err
		}
		evs = append(evs, ev)
	}
	return evs, nil
}

func TestStreamYieldsRecordsThenStats(t *testing.T) {
	srv := fakeServer(t, ndjsonBody("{\"record\":{\"a\":1}}\n{\"record\":{\"a\":2}}\n{\"stats\":{\"limit\":2,\"returned\":2,\"truncated\":true}}\n"))
	evs, err := drain(t, srv)
	if err != nil {
		t.Fatal(err)
	}
	if len(evs) != 3 || evs[0].Record["a"] != float64(1) || evs[1].Record["a"] != float64(2) {
		t.Fatalf("events = %+v", evs)
	}
	s := evs[2].Stats
	if s == nil || !s.Truncated || s.Limit != 2 || s.Returned != 2 || evs[2].Record != nil {
		t.Fatalf("stats = %+v", s)
	}
}

func TestStreamStatsOmittedLimitReadsAsUncapped(t *testing.T) {
	srv := fakeServer(t, ndjsonBody("{\"stats\":{}}\n"))
	evs, err := drain(t, srv)
	if err != nil {
		t.Fatal(err)
	}
	s := evs[0].Stats
	if s == nil || s.Limit != -1 || s.Returned != 0 || s.Truncated {
		t.Fatalf("stats = %+v", s)
	}
}

func TestStreamWithoutTrailerEndsWithoutStats(t *testing.T) {
	srv := fakeServer(t, ndjsonBody("{\"record\":{\"a\":1}}\n"))
	evs, err := drain(t, srv)
	if err != nil || len(evs) != 1 || evs[0].Stats != nil {
		t.Fatalf("evs=%+v err=%v", evs, err)
	}
}

func TestStreamInBandErrorYieldedOnce(t *testing.T) {
	srv := fakeServer(t, ndjsonBody("{\"record\":{\"a\":1}}\n{\"error\":{\"message\":\"m\"}}\n{\"record\":{\"a\":2}}\n"))
	yields := 0
	var gotErr error
	for _, err := range srv.DB("d").QueryStream(context.Background(), SQL, "select", nil) {
		yields++
		if err != nil {
			gotErr = err
		}
	}
	var ae *ArcadeDBError
	if !errors.As(gotErr, &ae) || ae.Status != 200 || ae.ErrorMessage != "m" {
		t.Fatalf("err = %#v", gotErr)
	}
	if yields != 2 {
		t.Fatalf("yields = %d, want 2", yields)
	}
}

func TestStreamInBandErrorWithoutMessage(t *testing.T) {
	srv := fakeServer(t, ndjsonBody("{\"error\":{}}\n"))
	_, err := drain(t, srv)
	var ae *ArcadeDBError
	if !errors.As(err, &ae) || ae.ErrorMessage != "the stream reported an error" {
		t.Fatalf("err = %#v", err)
	}
}

func TestStreamMalformedLineIsErrorOnce(t *testing.T) {
	srv := fakeServer(t, ndjsonBody("not json\n{\"record\":{}}\n"))
	yields := 0
	for _, err := range srv.DB("d").QueryStream(context.Background(), SQL, "select", nil) {
		yields++
		if err == nil {
			t.Fatal("want error")
		}
	}
	if yields != 1 {
		t.Fatalf("yields = %d", yields)
	}
}

func TestStreamNon2xxIsArcadeDBError(t *testing.T) {
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(500)
		writeJSON(w, `{"error":"boom"}`)
	})
	_, err := drain(t, srv)
	var ae *ArcadeDBError
	if !errors.As(err, &ae) || ae.Status != 500 || ae.ErrorMessage != "boom" {
		t.Fatalf("err = %#v", err)
	}
}

func TestStreamBreakClosesBody(t *testing.T) {
	done := make(chan struct{})
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/x-ndjson")
		_, _ = io.WriteString(w, "{\"record\":{\"a\":1}}\n")
		w.(http.Flusher).Flush()
		<-r.Context().Done()
		close(done)
	})
	for ev, err := range srv.DB("d").CommandStream(context.Background(), SQL, "select", nil) {
		if err != nil || ev.Record == nil {
			t.Fatalf("ev=%+v err=%v", ev, err)
		}
		break
	}
	select {
	case <-done:
	case <-time.After(5 * time.Second):
		t.Fatal("body not closed after break")
	}
}

func TestStreamSendsAcceptAndSessionHeaders(t *testing.T) {
	var hdr http.Header
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		hdr = r.Header.Clone()
		_, _ = io.WriteString(w, "")
	})
	db := srv.DB("d")
	db.sessionID = "AS-1"
	for _, err := range db.QueryStream(context.Background(), SQL, "select", nil) {
		if err != nil {
			t.Fatal(err)
		}
	}
	if hdr.Get("Accept") != "application/x-ndjson" || hdr.Get("arcadedb-session-id") != "AS-1" {
		t.Fatalf("headers = %v", hdr)
	}
	if hdr.Get("Authorization") == "" || !strings.HasPrefix(hdr.Get("User-Agent"), "arcadedb-go/") {
		t.Fatalf("editor headers missing: %v", hdr)
	}
}

func TestStreamIsLazy(t *testing.T) {
	called := false
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) { called = true })
	_ = srv.DB("d").QueryStream(context.Background(), SQL, "select", nil)
	if called {
		t.Fatal("request issued before iteration")
	}
}

func TestStreamLineLongerThan64KiB(t *testing.T) {
	big := strings.Repeat("x", 200*1024)
	srv := fakeServer(t, ndjsonBody("{\"record\":{\"s\":\""+big+"\"}}\n"))
	evs, err := drain(t, srv)
	if err != nil || len(evs) != 1 || evs[0].Record["s"] != big {
		t.Fatalf("long line lost: err=%v n=%d", err, len(evs))
	}
}
