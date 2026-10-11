package arcadedb

import (
	"context"
	"errors"
	"net/http"
	"slices"
	"testing"
	"time"
)

// refusal answers every request with 503, a Retry-After and a commit index header.
func refusal(retryAfter, commitIndex string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if retryAfter != "" {
			w.Header().Set("Retry-After", retryAfter)
		}
		if commitIndex != "" {
			w.Header().Set("X-ArcadeDB-Commit-Index", commitIndex)
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = w.Write([]byte(`{"error":"not yet"}`))
	}
}

func asArcade(t *testing.T, err error) *ArcadeDBError {
	t.Helper()
	var ae *ArcadeDBError
	if !errors.As(err, &ae) {
		t.Fatalf("err = %#v, want *ArcadeDBError", err)
	}
	return ae
}

func TestErrorHeadersReachEveryBufferedEntryPoint(t *testing.T) {
	ctx := context.Background()
	calls := map[string]func(db *Database) error{
		"Query": func(db *Database) error {
			_, err := db.Query(ctx, SQL, "select", nil)
			return err
		},
		"Command": func(db *Database) error {
			_, err := db.Command(ctx, SQL, "select", nil)
			return err
		},
		"Transaction begin": func(db *Database) error {
			return db.Transaction(ctx, func(*Database) error {
				t.Fatal("fn must not run when begin fails")
				return nil
			})
		},
		"BatchLoad": func(db *Database) error {
			_, err := db.BatchLoad(ctx, nil, nil, nil)
			return err
		},
		"TS().Write": func(db *Database) error {
			return db.TS().Write(ctx, "x", "")
		},
		"QueryStream non-2xx": func(db *Database) error {
			for _, err := range db.QueryStream(ctx, SQL, "select", nil) {
				return err
			}
			return nil
		},
		"BatchLoadStream non-2xx": func(db *Database) error {
			for _, err := range db.BatchLoadStream(ctx, nil, nil, nil) {
				return err
			}
			return nil
		},
	}
	for name, call := range calls {
		t.Run(name, func(t *testing.T) {
			srv := fakeServer(t, refusal(" 7 ", "42"))
			ae := asArcade(t, call(srv.DB("d")))
			if ae.Status != 503 || ae.RetryAfter != 7*time.Second || ae.CommitIndex != 42 {
				t.Fatalf("got %+v", *ae)
			}
		})
	}
}

func TestErrorHeadersUnparsableReadAsAbsent(t *testing.T) {
	for _, v := range []string{"", "Wed, 21 Oct 2026 07:28:00 GMT", "-1", "+3", "1.5", "abc", "99999999999999999999"} {
		t.Run(v, func(t *testing.T) {
			srv := fakeServer(t, refusal(v, v))
			_, err := srv.DB("d").Query(context.Background(), SQL, "select", nil)
			ae := asArcade(t, err)
			if ae.RetryAfter != 0 || ae.CommitIndex != 0 {
				t.Fatalf("header %q: got RetryAfter=%v CommitIndex=%d", v, ae.RetryAfter, ae.CommitIndex)
			}
		})
	}
}

func TestErrorHeaderRetryAfterZeroMeansNoWait(t *testing.T) {
	srv := fakeServer(t, refusal("0", ""))
	_, err := srv.DB("d").Query(context.Background(), SQL, "select", nil)
	if ae := asArcade(t, err); ae.RetryAfter != 0 || ae.Status != 503 {
		t.Fatalf("got %+v", *ae)
	}
}

func TestStreamInBandErrorMapsEveryField(t *testing.T) {
	event := `{"error":{"status":503,"error":"RetryableException","message":"raw text","exception":"com.arcadedb.X",` +
		`"detail":"cause","exceptionArgs":"a|b","requestId":"body-id","retryAfter":4}}`
	streams := map[string]func(db *Database) error{
		"QueryStream": func(db *Database) error {
			for _, err := range db.QueryStream(context.Background(), SQL, "select", nil) {
				if err != nil {
					return err
				}
			}
			return nil
		},
		"CommandStream": func(db *Database) error {
			for _, err := range db.CommandStream(context.Background(), SQL, "select", nil) {
				if err != nil {
					return err
				}
			}
			return nil
		},
	}
	for name, run := range streams {
		t.Run(name, func(t *testing.T) {
			srv := fakeServer(t, ndjsonBody(event+"\n"))
			ae := asArcade(t, run(srv.DB("d")))
			want := ArcadeDBError{
				Status: 503, ErrorMessage: "RetryableException", Exception: "com.arcadedb.X",
				Detail: "cause", ExceptionArgs: "a|b", RequestID: "body-id", RetryAfter: 4 * time.Second,
			}
			if *ae != want {
				t.Fatalf("got %+v\nwant %+v", *ae, want)
			}
		})
	}
}

func TestStreamInBandErrorFallsBackToMessageAnd200(t *testing.T) {
	srv := fakeServer(t, ndjsonBody(`{"error":{"message":"m","status":0}}`+"\n"))
	_, err := drain(t, srv)
	if ae := asArcade(t, err); ae.Status != 200 || ae.ErrorMessage != "m" || ae.RetryAfter != 0 {
		t.Fatalf("got %+v", *ae)
	}
}

func TestStreamInBandErrorHeaderRequestIDWins(t *testing.T) {
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Request-Id", "hdr-id")
		ndjsonBody(`{"error":{"message":"m","requestId":"body-id"}}`+"\n")(w, r)
	})
	_, err := drain(t, srv)
	if ae := asArcade(t, err); ae.RequestID != "hdr-id" {
		t.Fatalf("RequestID = %q, want hdr-id", ae.RequestID)
	}
}

func TestStreamInBandErrorNegativeRetryAfterIsAbsent(t *testing.T) {
	srv := fakeServer(t, ndjsonBody(`{"error":{"message":"m","retryAfter":-3}}`+"\n"))
	_, err := drain(t, srv)
	if ae := asArcade(t, err); ae.RetryAfter != 0 {
		t.Fatalf("RetryAfter = %v", ae.RetryAfter)
	}
}

func TestBatchStreamInBandErrorCarriesRetryAfterAndCommitIndex(t *testing.T) {
	srv, _ := batchServer(t, 200, "application/x-ndjson",
		`{"error":{"status":409,"error":"in flight","exception":"RequestStillInFlightException","retryAfter":2,"commitIndex":17}}`+"\n")
	var gotErr error
	for _, err := range srv.DB("d").BatchLoadStream(context.Background(), nil, slices.Values([]EdgeRow(nil)), nil) {
		if err != nil {
			gotErr = err
		}
	}
	ae := asArcade(t, gotErr)
	if ae.Status != 409 || ae.RetryAfter != 2*time.Second || ae.CommitIndex != 17 || ae.Exception != "RequestStillInFlightException" {
		t.Fatalf("got %+v", *ae)
	}
}
