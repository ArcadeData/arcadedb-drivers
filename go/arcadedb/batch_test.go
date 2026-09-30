package arcadedb

import (
	"bufio"
	"context"
	"errors"
	"io"
	"iter"
	"net/http"
	"net/http/httptest"
	"reflect"
	"slices"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

// batchCapture records what the batch fake received: headers, query and the body bytes
// that arrived before the upload ended (or was aborted).
type batchCapture struct {
	mu     sync.Mutex
	header http.Header
	query  string
	body   []byte
}

func (c *batchCapture) snapshot() (http.Header, string, string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.header, c.query, string(c.body)
}

// batchServer reads the whole request body, then answers with status and body.
func batchServer(t *testing.T, status int, contentType, respBody string) (*Server, *batchCapture) {
	t.Helper()
	c := &batchCapture{}
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		c.mu.Lock()
		c.header, c.query, c.body = r.Header.Clone(), r.URL.RawQuery, b
		c.mu.Unlock()
		w.Header().Set("Content-Type", contentType)
		w.WriteHeader(status)
		_, _ = io.WriteString(w, respBody)
	})
	return srv, c
}

func ptr[T any](v T) *T { return &v }

func TestBatchLineFormat(t *testing.T) {
	srv, c := batchServer(t, 200, "application/json", `{}`)
	_, err := srv.DB("d").BatchLoad(context.Background(),
		slices.Values([]VertexRow{{Type: "Person", ID: "p1", Properties: map[string]any{"name": "Alice"}}}),
		slices.Values([]EdgeRow{{Type: "Knows", From: "p1", To: "p2", Properties: map[string]any{"since": 2020}}}),
		nil)
	if err != nil {
		t.Fatal(err)
	}
	_, _, body := c.snapshot()
	want := `{"@type":"vertex","@class":"Person","@id":"p1","name":"Alice"}` + "\n" +
		`{"@type":"edge","@class":"Knows","@from":"p1","@to":"p2","since":2020}` + "\n"
	if body != want {
		t.Fatalf("body\n%s\nwant\n%s", body, want)
	}
}

func TestBatchVerticesBeforeEdges(t *testing.T) {
	srv, c := batchServer(t, 200, "application/json", `{}`)
	_, err := srv.DB("d").BatchLoad(context.Background(),
		slices.Values([]VertexRow{{Type: "V", ID: "a"}, {Type: "V", ID: "b"}}),
		slices.Values([]EdgeRow{{Type: "E", From: "a", To: "b"}}), nil)
	if err != nil {
		t.Fatal(err)
	}
	_, _, body := c.snapshot()
	lines := strings.Split(strings.TrimSuffix(body, "\n"), "\n")
	if len(lines) != 3 || !strings.Contains(lines[0], `"vertex"`) || !strings.Contains(lines[1], `"vertex"`) || !strings.Contains(lines[2], `"edge"`) {
		t.Fatalf("lines = %q", lines)
	}
}

func TestBatchOmitsEmptyID(t *testing.T) {
	srv, c := batchServer(t, 200, "application/json", `{}`)
	if _, err := srv.DB("d").BatchLoad(context.Background(), slices.Values([]VertexRow{{Type: "V"}}), nil, nil); err != nil {
		t.Fatal(err)
	}
	if _, _, body := c.snapshot(); body != `{"@type":"vertex","@class":"V"}`+"\n" {
		t.Fatalf("body = %q", body)
	}
}

// The upload aborts at the offending row: the call returns the validation error, and the
// server never receives that line. A first-row violation may still reach the server as an
// aborted request, so no assertion is made about whether a request arrived at all.
func TestBatchRejectsPropertyShadowingControlKey(t *testing.T) {
	for _, before := range []int{0, 5000} {
		t.Run(strconv.Itoa(before)+" rows before", func(t *testing.T) {
			var mu sync.Mutex
			var received []byte
			ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				b, _ := io.ReadAll(r.Body)
				mu.Lock()
				received = append(received, b...)
				mu.Unlock()
				writeJSON(w, `{}`)
			}))
			defer ts.Close()
			srv, err := NewServer(ts.URL, WithBasicAuth("root", "pw"))
			if err != nil {
				t.Fatal(err)
			}
			defer func() { _ = srv.Close() }()
			vs := func(yield func(VertexRow) bool) {
				for i := range before {
					if !yield(VertexRow{Type: "V", ID: "ok" + strconv.Itoa(i)}) {
						return
					}
				}
				if !yield(VertexRow{Type: "V", ID: "offender", Properties: map[string]any{"@class": "X"}}) {
					return
				}
				yield(VertexRow{Type: "V", ID: "after"})
			}
			_, err = srv.DB("d").BatchLoad(context.Background(), vs, nil, nil)
			if !errors.Is(err, ErrPropertyShadowsControlKey) {
				t.Fatalf("err = %v", err)
			}
			ts.Close() // waits for the handler, so received is final
			mu.Lock()
			defer mu.Unlock()
			if strings.Contains(string(received), "offender") || strings.Contains(string(received), "after") {
				t.Fatal("the offending line reached the server")
			}
		})
	}
}

func TestBatchStreamRejectsPropertyShadowingControlKey(t *testing.T) {
	srv, _ := batchServer(t, 200, "application/x-ndjson", "")
	var gotErr error
	for _, err := range srv.DB("d").BatchLoadStream(context.Background(), nil,
		slices.Values([]EdgeRow{{Type: "E", From: "a", To: "b", Properties: map[string]any{"@to": "c"}}}), nil) {
		if err != nil {
			gotErr = err
		}
	}
	if !errors.Is(gotErr, ErrPropertyShadowsControlKey) {
		t.Fatalf("err = %v", gotErr)
	}
}

func TestBatchLoadSendsNdjsonAndParams(t *testing.T) {
	srv, c := batchServer(t, 200, "application/json", `{}`)
	accept := generated.ExecuteBatchParamsAcceptApplicationxNdjson
	params := &generated.ExecuteBatchParams{CommitEvery: ptr(7), Accept: &accept}
	if _, err := srv.DB("d").BatchLoad(context.Background(), slices.Values([]VertexRow{{Type: "V"}}), nil, params); err != nil {
		t.Fatal(err)
	}
	h, q, _ := c.snapshot()
	if h.Get("Content-Type") != "application/x-ndjson" {
		t.Fatalf("Content-Type = %q", h.Get("Content-Type"))
	}
	if q != "commitEvery=7" {
		t.Fatalf("query = %q", q)
	}
	if strings.Contains(h.Get("Accept"), "ndjson") {
		t.Fatalf("buffered load asked for ndjson: Accept = %q", h.Get("Accept"))
	}
	if params.Accept != &accept || *params.CommitEvery != 7 {
		t.Fatal("caller's params were mutated")
	}
}

func TestBatchLoadReturnsRawSummary(t *testing.T) {
	srv, _ := batchServer(t, 200, "application/json",
		`{"verticesCreated":2,"edgesCreated":1,"idMapping":{"p1":"#1:0"},"idMappingOmitted":false}`)
	got, err := srv.DB("d").BatchLoad(context.Background(), nil, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	want := map[string]any{"verticesCreated": float64(2), "edgesCreated": float64(1),
		"idMapping": map[string]any{"p1": "#1:0"}, "idMappingOmitted": false}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v", got)
	}
}

// endless yields vertices until told to stop, and records that it was.
func endless(stopped *bool) iter.Seq[VertexRow] {
	return func(yield func(VertexRow) bool) {
		for i := 0; ; i++ {
			if !yield(VertexRow{Type: "V", ID: strconv.Itoa(i)}) {
				*stopped = true
				return
			}
		}
	}
}

// A server that rejects the load without reading the body must not leave the writer
// goroutine consuming the caller's sequence after the call returns.
func TestBatchLoadNon2xxStopsTheUpload(t *testing.T) {
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(403)
		_, _ = io.WriteString(w, `{"error":"no"}`)
	})
	stopped := false
	_, err := srv.DB("d").BatchLoad(context.Background(), endless(&stopped), nil, nil)
	var ae *ArcadeDBError
	if !errors.As(err, &ae) || ae.Status != 403 || ae.ErrorMessage != "no" {
		t.Fatalf("err = %#v", err)
	}
	if !stopped {
		t.Fatal("the sequence was still being consumed after BatchLoad returned")
	}
}

func TestBatchLoadReportsTransportErrorNotClosedPipe(t *testing.T) {
	ts := httptest.NewServer(http.NotFoundHandler())
	url := ts.URL
	ts.Close()
	srv, err := NewServer(url)
	if err != nil {
		t.Fatal(err)
	}
	stopped := false
	_, err = srv.DB("d").BatchLoad(context.Background(), endless(&stopped), nil, nil)
	if err == nil || errors.Is(err, io.ErrClosedPipe) {
		t.Fatalf("err = %v", err)
	}
	if !stopped {
		t.Fatal("the sequence was still being consumed after BatchLoad returned")
	}
}

func TestBatchStreamProgressThenSummary(t *testing.T) {
	srv, c := batchServer(t, 200, "application/x-ndjson",
		"{\"progress\":{\"verticesCreated\":1,\"idMapping\":{\"a\":\"#1:0\"}}}\n\n"+
			"{\"progress\":{\"verticesCreated\":2,\"idMapping\":{\"b\":\"#1:1\"}}}\n"+
			"{\"summary\":{\"verticesCreated\":2,\"idMappingStreamed\":true}}\n")
	params := &generated.ExecuteBatchParams{CommitEvery: ptr(1)}
	var evs []map[string]any
	for ev, err := range srv.DB("d").BatchLoadStream(context.Background(),
		slices.Values([]VertexRow{{Type: "V", ID: "a"}, {Type: "V", ID: "b"}}), nil, params) {
		if err != nil {
			t.Fatal(err)
		}
		evs = append(evs, ev)
	}
	if len(evs) != 3 || evs[0]["progress"] == nil || evs[2]["summary"] == nil {
		t.Fatalf("events = %v", evs)
	}
	// Fragments are yielded as received, never merged.
	if m := evs[1]["progress"].(map[string]any)["idMapping"].(map[string]any); len(m) != 1 || m["b"] != "#1:1" {
		t.Fatalf("second fragment = %v", m)
	}
	h, q, _ := c.snapshot()
	if h.Get("Accept") != "application/x-ndjson" || h.Get("Content-Type") != "application/x-ndjson" || q != "commitEvery=1" {
		t.Fatalf("Accept=%q Content-Type=%q query=%q", h.Get("Accept"), h.Get("Content-Type"), q)
	}
	if params.Accept != nil {
		t.Fatal("caller's params were mutated")
	}
}

func TestBatchStreamInBandError(t *testing.T) {
	cases := []struct {
		name, event string
		want        ArcadeDBError
	}{
		{"status given", `{"error":{"status":409}}`,
			ArcadeDBError{Status: 409, ErrorMessage: "the batch load reported an error"}},
		{"status absent", `{"error":{}}`,
			ArcadeDBError{Status: 500, ErrorMessage: "the batch load reported an error"}},
		{"all fields", `{"error":{"status":503,"error":"conflict","exception":"com.X","exceptionArgs":"a,b","commitIndex":3}}`,
			ArcadeDBError{Status: 503, ErrorMessage: "conflict", Exception: "com.X", ExceptionArgs: "a,b"}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			srv, _ := batchServer(t, 200, "application/x-ndjson",
				"{\"progress\":{\"verticesCreated\":1}}\n"+tc.event+"\n{\"summary\":{}}\n")
			var evs []map[string]any
			var errs []error
			for ev, err := range srv.DB("d").BatchLoadStream(context.Background(), nil, nil, nil) {
				if err != nil {
					errs = append(errs, err)
					continue
				}
				evs = append(evs, ev)
			}
			if len(evs) != 1 || len(errs) != 1 {
				t.Fatalf("events=%v errors=%v", evs, errs)
			}
			var ae *ArcadeDBError
			if !errors.As(errs[0], &ae) {
				t.Fatalf("err = %#v", errs[0])
			}
			ae.RequestID = ""
			if *ae != tc.want {
				t.Fatalf("got %+v want %+v", *ae, tc.want)
			}
		})
	}
}

func TestBatchStreamNon2xxIsArcadeDBError(t *testing.T) {
	srv, _ := batchServer(t, 400, "application/json", `{"error":"bad payload"}`)
	var gotErr error
	n := 0
	for _, err := range srv.DB("d").BatchLoadStream(context.Background(), nil, nil, nil) {
		n++
		gotErr = err
	}
	var ae *ArcadeDBError
	if n != 1 || !errors.As(gotErr, &ae) || ae.Status != 400 || ae.ErrorMessage != "bad payload" {
		t.Fatalf("n=%d err=%#v", n, gotErr)
	}
}

func TestBatchStreamsBodyWithoutBuffering(t *testing.T) {
	const n = 100_000
	firstLine := make(chan struct{})
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		br := bufio.NewReader(r.Body)
		if _, err := br.ReadString('\n'); err == nil {
			close(firstLine)
		}
		_, _ = io.Copy(io.Discard, br)
		writeJSON(w, `{"verticesCreated":100000}`)
	})
	vs := func(yield func(VertexRow) bool) {
		for i := range n {
			if i == n-1 {
				select {
				case <-firstLine:
				case <-time.After(10 * time.Second):
					t.Error("the server saw no line before the sequence finished")
					return
				}
			}
			if !yield(VertexRow{Type: "V", ID: strconv.Itoa(i)}) {
				return
			}
		}
	}
	if _, err := srv.DB("d").BatchLoad(context.Background(), vs, nil, nil); err != nil {
		t.Fatal(err)
	}
}

// Breaking out of the stream while the upload is still running must stop the writer
// goroutine: the sequence is told to stop before iteration returns.
func TestBatchStreamBreakStopsTheUpload(t *testing.T) {
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		_ = http.NewResponseController(w).EnableFullDuplex()
		br := bufio.NewReader(r.Body)
		_, _ = br.ReadString('\n')
		w.Header().Set("Content-Type", "application/x-ndjson")
		_, _ = io.WriteString(w, "{\"progress\":{\"verticesCreated\":1}}\n")
		w.(http.Flusher).Flush()
		_, _ = io.Copy(io.Discard, br)
	})
	stopped := false
	done := make(chan struct{})
	go func() {
		defer close(done)
		for _, err := range srv.DB("d").BatchLoadStream(context.Background(), endless(&stopped), nil, nil) {
			if err != nil {
				t.Error(err)
			}
			break
		}
	}()
	select {
	case <-done:
	case <-time.After(10 * time.Second):
		t.Fatal("iteration did not return after break")
	}
	if !stopped {
		t.Fatal("the sequence was still being consumed after iteration returned")
	}
}

// panickingVertices yields one row, then panics with v. unwound is closed as the panic
// leaves the sequence's frame, so a test can tell the writer goroutine got that far.
func panickingVertices(v any, unwound chan struct{}) iter.Seq[VertexRow] {
	return func(yield func(VertexRow) bool) {
		defer close(unwound)
		if !yield(VertexRow{Type: "V", ID: "a"}) {
			return
		}
		panic(v)
	}
}

// The caller's sequence runs on the library's writer goroutine, where an unrecovered panic
// would kill the process. It is recovered there and re-raised, with its original value, on
// the caller's goroutine, after the upload is aborted and the writer has finished.
func TestBatchLoadSequencePanicReRaisedOnCallerGoroutine(t *testing.T) {
	srv, _ := batchServer(t, 200, "application/json", `{}`)
	unwound := make(chan struct{})
	func() {
		defer func() {
			if r := recover(); r != "row boom" {
				t.Fatalf("recover() = %v, want row boom", r)
			}
		}()
		_, _ = srv.DB("d").BatchLoad(context.Background(), panickingVertices("row boom", unwound), nil, nil)
		t.Fatal("BatchLoad returned instead of re-panicking")
	}()
	select {
	case <-unwound:
	default:
		t.Fatal("the writer goroutine had not finished when the panic was re-raised")
	}
}

func TestBatchLoadStreamSequencePanicReRaisedOnCallerGoroutine(t *testing.T) {
	srv, _ := batchServer(t, 200, "application/x-ndjson", "{\"summary\":{}}\n")
	unwound := make(chan struct{})
	func() {
		defer func() {
			if r := recover(); r != "row boom" {
				t.Fatalf("recover() = %v, want row boom", r)
			}
		}()
		for range srv.DB("d").BatchLoadStream(context.Background(), panickingVertices("row boom", unwound), nil, nil) {
		}
		t.Fatal("iteration ended instead of re-panicking")
	}()
	select {
	case <-unwound:
	default:
		t.Fatal("the writer goroutine had not finished when the panic was re-raised")
	}
}
