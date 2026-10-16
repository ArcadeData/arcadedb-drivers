package arcadedb

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"testing"
	"time"
)

// Bodies below are copied from a live 26.11.1-SNAPSHOT server.

func TestListQueriesSendsFiltersAndDecodes(t *testing.T) {
	ctx := context.Background()
	for _, c := range []struct {
		opts ListQueriesOptions
		want string
	}{
		{ListQueriesOptions{}, "list queries"},
		{ListQueriesOptions{Database: "p"}, "list queries database p"},
		{ListQueriesOptions{Tag: "a b"}, "list queries tag a b"},
		{ListQueriesOptions{Database: "p", Tag: "nightly"}, "list queries database p tag nightly"},
	} {
		var rec recorded
		srv := recordingServer(t, 200, `{"result":[{"id":"q5-1f6d4564","database":"p","user":"root","protocol":"http",
			"language":"sql","text":"SLEEP 20000","startedAt":1792137065792,"elapsedMs":1507,"terminating":false,
			"sessionId":"AS-1","tag":"tagA","clientAddress":"/192.168.65.1:18259","server":"ArcadeDB_0"}]}`, &rec)
		got, err := srv.ListQueries(ctx, c.opts)
		if err != nil {
			t.Fatal(err)
		}
		if rec.method != http.MethodPost || rec.path != "/api/v1/server" || rec.body["command"] != c.want {
			t.Fatalf("%+v: sent %s %s %v", c.opts, rec.method, rec.path, rec.body)
		}
		if _, ok := rec.body["wait"]; ok {
			t.Fatalf("list sent a wait: %v", rec.body)
		}
		want := RunningQuery{ID: "q5-1f6d4564", Database: "p", User: "root", Protocol: "http", Language: "sql",
			Text: "SLEEP 20000", StartedAt: 1792137065792, ElapsedMs: 1507, SessionID: "AS-1", Tag: "tagA",
			ClientAddress: "/192.168.65.1:18259", Server: "ArcadeDB_0"}
		if len(got) != 1 || got[0] != want {
			t.Fatalf("got %+v", got)
		}
	}
}

func TestListsAreNeverNil(t *testing.T) {
	ctx := context.Background()
	var rec recorded
	srv := recordingServer(t, 200, `{"result":[]}`, &rec)
	q, err := srv.ListQueries(ctx, ListQueriesOptions{})
	if err != nil || q == nil {
		t.Fatalf("ListQueries = %v, %v", q, err)
	}
	tx, err := srv.ListTransactions(ctx)
	if err != nil || tx == nil {
		t.Fatalf("ListTransactions = %v, %v", tx, err)
	}
	r, err := srv.TerminateQueriesByTag(ctx, "none", TerminateOptions{})
	if err != nil || r == nil {
		t.Fatalf("TerminateQueriesByTag = %v, %v", r, err)
	}
}

func TestTerminateQueryEveryStatus(t *testing.T) {
	ctx := context.Background()
	for _, status := range []QueryStatus{QueryTerminated, QueryCompleted, QueryTerminating, QueryNotFound} {
		var rec recorded
		srv := recordingServer(t, 200, fmt.Sprintf(`{"result":{"id":"q6","status":%q}}`, status), &rec)
		got, err := srv.TerminateQuery(ctx, "q6", TerminateOptions{})
		if err != nil {
			t.Fatal(err)
		}
		if rec.body["command"] != "terminate query q6" || got.ID != "q6" || got.Status != status {
			t.Fatalf("%s: sent %v, got %+v", status, rec.body, got)
		}
		if got.SessionID != "" || got.SessionOpen != nil {
			t.Fatalf("%s: session fields set outside a session: %+v", status, got)
		}
	}
}

func TestTerminateQueryInsideASession(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 200,
		`{"result":{"id":"q6","status":"terminating","sessionId":"AS-262f","sessionOpen":true}}`, &rec)
	got, err := srv.TerminateQuery(context.Background(), "q6", TerminateOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if got.SessionID != "AS-262f" || got.SessionOpen == nil || !*got.SessionOpen {
		t.Fatalf("got %+v", got)
	}
}

func TestTerminateSendsWaitInMilliseconds(t *testing.T) {
	ctx := context.Background()
	for _, c := range []struct {
		wait time.Duration
		want any // nil: not sent
	}{
		{0, nil},
		{-time.Second, nil},
		{3 * time.Second, float64(3000)},
		{time.Microsecond, float64(1)},
		{1500 * time.Microsecond, float64(2)},
		{time.Millisecond, float64(1)},
	} {
		var rec recorded
		srv := recordingServer(t, 200, `{"result":[]}`, &rec)
		if _, err := srv.TerminateQueriesByTag(ctx, "t", TerminateOptions{Wait: c.wait}); err != nil {
			t.Fatal(err)
		}
		if got, ok := rec.body["wait"]; got != c.want || (c.want == nil && ok) {
			t.Fatalf("wait %v: sent %v", c.wait, rec.body)
		}
		if rec.body["command"] != "terminate queries tag t" || rec.body["language"] != "sql" {
			t.Fatalf("sent %v", rec.body)
		}
	}
}

func TestTerminateQueriesByTagDecodesEach(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 200, `{"result":[{"id":"q1","status":"terminated"},{"id":"q2","status":"completed"}]}`, &rec)
	got, err := srv.TerminateQueriesByTag(context.Background(), "it's \"q\"", TerminateOptions{Wait: time.Second})
	if err != nil {
		t.Fatal(err)
	}
	if rec.body["command"] != `terminate queries tag it's "q"` {
		t.Fatalf("sent %v", rec.body)
	}
	if len(got) != 2 || got[0].Status != QueryTerminated || got[1].Status != QueryCompleted {
		t.Fatalf("got %+v", got)
	}
}

func TestListAndTerminateTransactions(t *testing.T) {
	ctx := context.Background()
	var rec recorded
	srv := recordingServer(t, 200, `{"result":[{"id":"AS-4c9d","user":"root","database":"p","idleMs":1522,
		"busy":true,"runningQueries":["q16"],"server":"ArcadeDB_0"}]}`, &rec)
	txs, err := srv.ListTransactions(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if rec.body["command"] != "list transactions" || len(txs) != 1 || !txs[0].Busy ||
		txs[0].IdleMs != 1522 || len(txs[0].RunningQueries) != 1 || txs[0].RunningQueries[0] != "q16" {
		t.Fatalf("sent %v, got %+v", rec.body, txs)
	}

	srv = recordingServer(t, 200, `{"result":{"id":"AS-4c9d","status":"terminated"}}`, &rec)
	r, err := srv.TerminateTransaction(ctx, "AS-4c9d")
	if err != nil {
		t.Fatal(err)
	}
	if rec.body["command"] != "terminate transaction AS-4c9d" || r.Status != QueryTerminated {
		t.Fatalf("sent %v, got %+v", rec.body, r)
	}
}

// Every value the server would split or trim is refused before a request is sent.
func TestRunningCommandsRefuseBadArguments(t *testing.T) {
	ctx := context.Background()
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		t.Errorf("a request was sent: %s", r.URL.Path)
	})
	for name, call := range map[string]func() error{
		"empty id":           func() error { _, err := srv.TerminateQuery(ctx, "", TerminateOptions{}); return err },
		"id with space":      func() error { _, err := srv.TerminateQuery(ctx, "q1 q2", TerminateOptions{}); return err },
		"empty tag":          func() error { _, err := srv.TerminateQueriesByTag(ctx, "", TerminateOptions{}); return err },
		"padded tag":         func() error { _, err := srv.TerminateQueriesByTag(ctx, " t", TerminateOptions{}); return err },
		"padded list tag":    func() error { _, err := srv.ListQueries(ctx, ListQueriesOptions{Tag: "t\n"}); return err },
		"database with tab":  func() error { _, err := srv.ListQueries(ctx, ListQueriesOptions{Database: "a\tb"}); return err },
		"empty session":      func() error { _, err := srv.TerminateTransaction(ctx, ""); return err },
		"session with space": func() error { _, err := srv.TerminateTransaction(ctx, "AS-1 x"); return err },
		"id with a control":  func() error { _, err := srv.TerminateQuery(ctx, "q1\x01", TerminateOptions{}); return err },
		"tag ending in NUL":  func() error { _, err := srv.TerminateQueriesByTag(ctx, "t\x00", TerminateOptions{}); return err },
	} {
		if err := call(); !errors.Is(err, ErrInvalidName) {
			t.Errorf("%s: err = %v, want ErrInvalidName", name, err)
		}
	}
}

func TestRunningCommandErrorsAndEmptyBodies(t *testing.T) {
	ctx := context.Background()
	var rec recorded
	srv := recordingServer(t, 400, `{"error":"Server command not valid","detail":"Syntax: terminate query <id>"}`, &rec)
	_, err := srv.TerminateQuery(ctx, "q1", TerminateOptions{})
	wantArcadeDBError(t, err, 400, "Server command not valid")

	for _, body := range []string{``, `{}`, `{"result":null}`} {
		srv = recordingServer(t, 200, body, &rec)
		if _, err := srv.ListTransactions(ctx); !errors.Is(err, ErrEmptyBody) {
			t.Fatalf("body %q: err = %v, want ErrEmptyBody", body, err)
		}
	}
}

func TestIsQueryTerminated(t *testing.T) {
	terminated := `{"error":"Query terminated","requestId":"ee5d","exception":"com.arcadedb.exception.QueryTerminatedException",
		"detail":"the commit has been terminated (query q5-1f6d4564, terminated by root)"}`
	var rec recorded
	_, err := recordingServer(t, 409, terminated, &rec).DB("p").Command(context.Background(), SQL, "SLEEP 20000", nil)
	if !IsQueryTerminated(err) {
		t.Fatalf("IsQueryTerminated(%v) = false", err)
	}
	if !IsQueryTerminated(fmt.Errorf("wrapped: %w", err)) {
		t.Fatal("a wrapped error is not matched")
	}

	inFlight := `{"error":"Request still in flight","exception":"com.arcadedb.server.http.RequestStillInFlightException"}`
	_, err = recordingServer(t, 409, inFlight, &rec).DB("p").Command(context.Background(), SQL, "SELECT 1", nil)
	if IsQueryTerminated(err) {
		t.Fatal("another 409 is matched")
	}
	if IsQueryTerminated(nil) || IsQueryTerminated(errors.New("Query terminated")) {
		t.Fatal("a non-ArcadeDBError is matched")
	}
}

func TestProgress(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 200, `{"result":[{"database":"p","done":40,"elapsedMs":1200,"id":7,"operation":"CHECK DATABASE",
		"percentage":40,"startedOn":1792137065792,"stepIndex":1,"stepName":"pages","total":100,"totalSteps":3}]}`, &rec)
	got, err := srv.DB("p").Progress(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if rec.method != http.MethodGet || rec.path != "/api/v1/progress/p" {
		t.Fatalf("sent %s %s", rec.method, rec.path)
	}
	if len(got.Result) != 1 || got.Result[0].Operation != "CHECK DATABASE" || got.Result[0].Percentage != 40 {
		t.Fatalf("got %+v", got)
	}

	srv = recordingServer(t, 403, `{"error":"Security error"}`, &rec)
	_, err = srv.DB("p").Progress(context.Background())
	wantArcadeDBError(t, err, 403, "Security error")

	// No Content-Type, as in promql_test.go: with one, the generated parser fails on the empty
	// body before the facade sees it, the same for every typed method.
	srv = fakeServer(t, func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusOK) })
	if _, err := srv.DB("p").Progress(context.Background()); !errors.Is(err, ErrEmptyBody) {
		t.Fatalf("err = %v, want ErrEmptyBody", err)
	}
}

// The rule is Java's trim: at or below U+0020. A no-break space is not white space to the server,
// so a tag that ends in one is sent, not refused.
func TestNoBreakSpaceIsNotRefused(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 200, `{"result":[]}`, &rec)
	if _, err := srv.TerminateQueriesByTag(context.Background(), "t\u00a0", TerminateOptions{}); err != nil {
		t.Fatal(err)
	}
	if rec.body["command"] != "terminate queries tag t\u00a0" {
		t.Fatalf("sent %v", rec.body)
	}
}
