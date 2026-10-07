package arcadedb

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/coder/websocket"
)

// wsFake is a scripted /ws endpoint. script runs once per accepted connection and is given
// a frame-level view of it; every frame the client sent is also recorded in frames.
type wsFake struct {
	mu     sync.Mutex
	frames []map[string]any
	auth   string
}

func (f *wsFake) sent() []map[string]any {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]map[string]any(nil), f.frames...)
}

// recv reads one client frame and records it.
func (f *wsFake) recv(t *testing.T, ctx context.Context, c *websocket.Conn) map[string]any {
	t.Helper()
	_, data, err := c.Read(ctx)
	if err != nil {
		t.Errorf("fake /ws read: %v", err)
		return nil
	}
	var m map[string]any
	if err := json.Unmarshal(data, &m); err != nil {
		t.Errorf("fake /ws frame %s: %v", data, err)
	}
	f.mu.Lock()
	f.frames = append(f.frames, m)
	f.mu.Unlock()
	return m
}

func send(t *testing.T, ctx context.Context, c *websocket.Conn, body string) {
	t.Helper()
	if err := c.Write(ctx, websocket.MessageText, []byte(body)); err != nil {
		t.Errorf("fake /ws write: %v", err)
	}
}

const startedFrame = `{"result":"ok","action":"started","sessionId":"srv-1","database":"db","transactionMode":"per_stream","conflictMode":"error","validateOnly":false}`

// newWSServer serves /ws with script and every other path with the transaction fake.
func newWSServer(t *testing.T, script func(ctx context.Context, f *wsFake, c *websocket.Conn)) (*Server, *wsFake, *txFake) {
	t.Helper()
	f, tx := &wsFake{}, &txFake{}
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/ws" {
			tx.handler(w, r)
			return
		}
		f.mu.Lock()
		f.auth = r.Header.Get("Authorization")
		f.mu.Unlock()
		c, err := websocket.Accept(w, r, nil)
		if err != nil {
			return
		}
		defer c.CloseNow()
		script(r.Context(), f, c)
	})
	return srv, f, tx
}

func chunkAck(seq int, n int) string {
	b, _ := json.Marshal(map[string]any{"result": "ok", "action": "batchAck", "sessionId": "srv-1", "chunkSeq": seq,
		"received": n, "inserted": n, "updated": 0, "ignored": 0, "failed": 0})
	return string(b)
}

func recs(names ...string) []map[string]any {
	out := make([]map[string]any, len(names))
	for i, n := range names {
		out[i] = map[string]any{"name": n}
	}
	return out
}

func TestInsertSessionHappyPath(t *testing.T) {
	srv, f, _ := newWSServer(t, func(ctx context.Context, f *wsFake, c *websocket.Conn) {
		f.recv(t, ctx, c)
		send(t, ctx, c, startedFrame)
		f.recv(t, ctx, c)
		send(t, ctx, c, chunkAck(1, 2))
		f.recv(t, ctx, c)
		send(t, ctx, c, chunkAck(2, 1))
		f.recv(t, ctx, c)
		send(t, ctx, c, `{"result":"ok","action":"committed","sessionId":"srv-1","outcome":"commit","summary":{"received":3,"inserted":3,"partialCommit":false}}`)
		_, _, _ = c.Read(ctx) // wait for the client to close
	})
	ctx := context.Background()
	var seen []int64
	s, err := srv.DB("db").InsertSession(ctx, WithInsertTargetType("Person"), WithInsertKeyColumns("name"),
		WithInsertConflictMode(InsertConflictUpdate), WithInsertUpdateColumnsOnConflict("age"), WithInsertValidateOnly(),
		WithOnInsertAck(func(a InsertAck) { seen = append(seen, a.ChunkSeq) }))
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	if s.SessionID() != "srv-1" || s.TransactionMode() != "per_stream" || s.DatabaseName() != "db" || !s.IsOpen() {
		t.Fatalf("session = %+v", s)
	}
	ack, err := s.SendChunk(ctx, recs("a", "b"))
	if err != nil || ack.Inserted != 2 || ack.ChunkSeq != 1 {
		t.Fatalf("ack = %+v, %v", ack, err)
	}
	if _, err := s.SendChunk(ctx, recs("c")); err != nil {
		t.Fatal(err)
	}
	if len(seen) != 2 || seen[0] != 1 || seen[1] != 2 || s.LastChunkSeq() != 2 {
		t.Fatalf("callback saw %v, last seq %d", seen, s.LastChunkSeq())
	}
	res, err := s.Commit(ctx)
	if err != nil || res.Outcome != "commit" || res.Summary.Inserted != 3 {
		t.Fatalf("result = %+v, %v", res, err)
	}
	if s.IsOpen() {
		t.Fatal("session still open after Commit")
	}
	if _, err := s.SendChunk(ctx, recs("x")); !errors.Is(err, ErrInsertSessionClosed) {
		t.Fatalf("SendChunk after Commit = %v", err)
	}
	if _, err := s.Commit(ctx); !errors.Is(err, ErrInsertSessionClosed) {
		t.Fatalf("second Commit = %v", err)
	}
	_ = s.Close()
	_ = s.Close() // idempotent

	frames := f.sent()
	start := frames[0]
	opts, _ := start["options"].(map[string]any)
	if start["action"] != "start" || start["database"] != "db" || start["sessionId"] != nil || start["transactionId"] != nil ||
		opts["targetType"] != "Person" || opts["conflictMode"] != "update" || opts["validateOnly"] != true {
		t.Fatalf("start frame = %v", start)
	}
	if frames[1]["chunkSeq"] != float64(1) || frames[2]["chunkSeq"] != float64(2) || frames[1]["sessionId"] != "srv-1" {
		t.Fatalf("chunk frames = %v %v", frames[1], frames[2])
	}
	if len(frames) != 4 { // Close after Commit must not send a rollback
		t.Fatalf("frames = %v", frames)
	}
	if !strings.HasPrefix(f.auth, "Basic ") {
		t.Fatalf("Authorization = %q", f.auth)
	}
}

func TestInsertSessionClientChosenID(t *testing.T) {
	srv, f, _ := newWSServer(t, func(ctx context.Context, f *wsFake, c *websocket.Conn) {
		f.recv(t, ctx, c)
		send(t, ctx, c, startedFrame)
		_, _, _ = c.Read(ctx)
	})
	s, err := srv.DB("db").InsertSession(context.Background(), WithInsertSessionID("mine"))
	if err != nil {
		t.Fatal(err)
	}
	s.abort()
	if f.sent()[0]["sessionId"] != "mine" {
		t.Fatalf("start = %v", f.sent()[0])
	}
}

// A chunk refused as a whole leaves the session open and its sequence number unspent.
func TestInsertSessionRefusedChunkReusesItsSequence(t *testing.T) {
	srv, f, _ := newWSServer(t, func(ctx context.Context, f *wsFake, c *websocket.Conn) {
		f.recv(t, ctx, c)
		send(t, ctx, c, startedFrame)
		f.recv(t, ctx, c)
		send(t, ctx, c, `{"result":"error","action":"error","error":"Insert session error","detail":"Chunk 1 carries 5 records, more than the 4 allowed by 'x'","sessionId":"srv-1"}`)
		f.recv(t, ctx, c)
		send(t, ctx, c, chunkAck(1, 2))
		_, _, _ = c.Read(ctx)
	})
	ctx := context.Background()
	s, err := srv.DB("db").InsertSession(ctx)
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	_, err = s.SendChunk(ctx, recs("a", "b", "c", "d", "e"))
	var serr *InsertSessionError
	if !errors.As(err, &serr) || !strings.Contains(serr.Detail, "more than the 4") || serr.SessionEnded {
		t.Fatalf("err = %v (%+v)", err, serr)
	}
	if !s.IsOpen() || s.LastChunkSeq() != 0 {
		t.Fatalf("open=%v lastSeq=%d", s.IsOpen(), s.LastChunkSeq())
	}
	if _, err := s.SendChunk(ctx, recs("a", "b")); err != nil {
		t.Fatal(err)
	}
	frames := f.sent()
	if frames[1]["chunkSeq"] != float64(1) || frames[2]["chunkSeq"] != float64(1) {
		t.Fatalf("sequences = %v, %v", frames[1]["chunkSeq"], frames[2]["chunkSeq"])
	}
}

// A per_batch chunk whose own transaction failed is acknowledged but not applied: the
// server keeps its watermark, so the next chunk must take the same sequence.
func TestInsertSessionWholeChunkFailureDoesNotAdvanceSequence(t *testing.T) {
	srv, f, _ := newWSServer(t, func(ctx context.Context, f *wsFake, c *websocket.Conn) {
		f.recv(t, ctx, c)
		send(t, ctx, c, startedFrame)
		f.recv(t, ctx, c)
		send(t, ctx, c, `{"result":"ok","action":"batchAck","sessionId":"srv-1","chunkSeq":1,"received":2,"inserted":0,"updated":0,"ignored":0,"failed":2,"errors":[{"rowIndex":-1,"code":"DB_ERROR","message":"boom"}]}`)
		f.recv(t, ctx, c)
		send(t, ctx, c, chunkAck(1, 2))
		_, _, _ = c.Read(ctx)
	})
	ctx := context.Background()
	s, _ := srv.DB("db").InsertSession(ctx)
	defer s.Close()
	ack, err := s.SendChunk(ctx, recs("a", "b"))
	if err != nil || !ack.WholeChunkFailed || ack.Failed != 2 || s.LastChunkSeq() != 0 {
		t.Fatalf("ack = %+v, %v, seq %d", ack, err, s.LastChunkSeq())
	}
	if _, err := s.SendChunk(ctx, recs("a", "b")); err != nil || s.LastChunkSeq() != 1 {
		t.Fatalf("resend: %v, seq %d", err, s.LastChunkSeq())
	}
	if f.sent()[2]["chunkSeq"] != float64(1) {
		t.Fatalf("resend used seq %v", f.sent()[2]["chunkSeq"])
	}
}

func TestInsertSessionRowFailuresAreInTheAckNotAnError(t *testing.T) {
	srv, _, _ := newWSServer(t, func(ctx context.Context, f *wsFake, c *websocket.Conn) {
		f.recv(t, ctx, c)
		send(t, ctx, c, startedFrame)
		f.recv(t, ctx, c)
		send(t, ctx, c, `{"result":"ok","action":"batchAck","sessionId":"srv-1","chunkSeq":1,"received":2,"inserted":1,"updated":0,"ignored":0,"failed":1,"errors":[{"rowIndex":1,"code":"DB_ERROR","message":"no type"}]}`)
		_, _, _ = c.Read(ctx)
	})
	ctx := context.Background()
	s, _ := srv.DB("db").InsertSession(ctx)
	defer s.Close()
	ack, err := s.SendChunk(ctx, []map[string]any{{"name": "a"}, {"@class": "NoSuchType"}})
	if err != nil || ack.Failed != 1 || ack.WholeChunkFailed || len(ack.Errors) != 1 || ack.Errors[0].RowIndex != 1 || s.LastChunkSeq() != 1 {
		t.Fatalf("ack = %+v, %v", ack, err)
	}
}

func TestInsertSessionJoinNeedsATransaction(t *testing.T) {
	srv, _, _ := newWSServer(t, func(ctx context.Context, f *wsFake, c *websocket.Conn) { t.Error("must not connect") })
	_, err := srv.DB("db").InsertSession(context.Background(), WithJoinCurrentTransaction())
	if !errors.Is(err, ErrNoTransactionToJoin) {
		t.Fatalf("err = %v", err)
	}
}

func TestInsertSessionJoinRefusesAnotherMode(t *testing.T) {
	srv, _, _ := newWSServer(t, func(ctx context.Context, f *wsFake, c *websocket.Conn) { t.Error("must not connect") })
	db := &Database{srv: srv, name: "db", sessionID: "s1"}
	_, err := db.InsertSession(context.Background(), WithJoinCurrentTransaction(), WithInsertTransactionMode(InsertPerRow))
	if err == nil || !strings.Contains(err.Error(), "implies transaction mode") {
		t.Fatalf("err = %v", err)
	}
}

func TestInsertSessionJoinsTheTransactionOfTheHandle(t *testing.T) {
	srv, f, tx := newWSServer(t, func(ctx context.Context, f *wsFake, c *websocket.Conn) {
		f.recv(t, ctx, c)
		send(t, ctx, c, `{"result":"ok","action":"started","sessionId":"srv-1","database":"db","transactionMode":"none","conflictMode":"error","transactionId":"s1"}`)
		f.recv(t, ctx, c)
		send(t, ctx, c, chunkAck(1, 2))
		f.recv(t, ctx, c)
		send(t, ctx, c, `{"result":"ok","action":"committed","sessionId":"srv-1","outcome":"detached","summary":{"inserted":2,"externalTransaction":true,"transactionId":"s1"}}`)
		_, _, _ = c.Read(ctx)
	})
	ctx := context.Background()
	err := srv.DB("db").Transaction(ctx, func(txdb *Database) error {
		s, err := txdb.InsertSession(ctx, WithInsertTargetType("Person"), WithJoinCurrentTransaction())
		if err != nil {
			return err
		}
		defer s.Close()
		if s.ExternalTransactionID() != "s1" || s.TransactionMode() != "none" {
			t.Errorf("session = %+v", s)
		}
		if _, err := s.SendChunk(ctx, recs("a", "b")); err != nil {
			return err
		}
		res, err := s.Commit(ctx)
		if err != nil {
			return err
		}
		if res.Outcome != InsertOutcomeDetached || !res.Summary.ExternalTransaction {
			t.Errorf("result = %+v", res)
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	start := f.sent()[0]
	opts, _ := start["options"].(map[string]any)
	if start["transactionId"] != "s1" || opts["transactionMode"] != "none" {
		t.Fatalf("start = %v", start)
	}
	if calls := tx.seen(); calls[len(calls)-1].op != "commit" {
		t.Fatalf("http calls = %v", calls)
	}
}

// The idle sweep pushes an error frame nobody asked for; the next call must report it and
// not skip over it to some later frame.
func TestInsertSessionReportsAnUnsolicitedError(t *testing.T) {
	pushed := make(chan struct{})
	srv, _, _ := newWSServer(t, func(ctx context.Context, f *wsFake, c *websocket.Conn) {
		f.recv(t, ctx, c)
		send(t, ctx, c, startedFrame)
		send(t, ctx, c, `{"result":"error","action":"error","error":"Insert session expired","detail":"idle","sessionId":"srv-1"}`)
		close(pushed)
		// The chunk that follows is answered with the "unknown session" error a real server gives.
		f.recv(t, ctx, c)
		send(t, ctx, c, `{"result":"error","action":"error","error":"Insert session error","detail":"session is closed"}`)
		_, _, _ = c.Read(ctx)
	})
	ctx := context.Background()
	s, _ := srv.DB("db").InsertSession(ctx)
	defer s.Close()
	<-pushed
	time.Sleep(50 * time.Millisecond)
	_, err := s.SendChunk(ctx, recs("a"))
	var serr *InsertSessionError
	if !errors.As(err, &serr) || serr.Title != "Insert session expired" || !serr.SessionEnded {
		t.Fatalf("err = %v", err)
	}
	if s.IsOpen() {
		t.Fatal("an expired session must be closed")
	}
}

func TestInsertSessionCloseRollsBackAnOpenSession(t *testing.T) {
	done := make(chan struct{})
	srv, f, _ := newWSServer(t, func(ctx context.Context, f *wsFake, c *websocket.Conn) {
		f.recv(t, ctx, c)
		send(t, ctx, c, startedFrame)
		f.recv(t, ctx, c)
		send(t, ctx, c, chunkAck(1, 1))
		f.recv(t, ctx, c)
		send(t, ctx, c, `{"result":"ok","action":"committed","sessionId":"srv-1","outcome":"rollback","summary":{}}`)
		_, _, _ = c.Read(ctx)
		close(done)
	})
	ctx := context.Background()
	s, _ := srv.DB("db").InsertSession(ctx)
	if _, err := s.SendChunk(ctx, recs("a")); err != nil {
		t.Fatal(err)
	}
	if err := s.Close(); err != nil {
		t.Fatal(err)
	}
	if s.IsOpen() {
		t.Fatal("open after Close")
	}
	_ = s.Close()
	<-done
	frames := f.sent()
	if len(frames) != 3 || frames[2]["action"] != "rollback" {
		t.Fatalf("frames = %v", frames)
	}
}

func TestInsertSessionTimeoutClosesTheSession(t *testing.T) {
	srv, _, _ := newWSServer(t, func(ctx context.Context, f *wsFake, c *websocket.Conn) {
		f.recv(t, ctx, c)
		send(t, ctx, c, startedFrame)
		f.recv(t, ctx, c) // never answered
		_, _, _ = c.Read(ctx)
	})
	ctx := context.Background()
	s, err := srv.DB("db").InsertSession(ctx, WithInsertFrameTimeout(100*time.Millisecond))
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	_, err = s.SendChunk(ctx, recs("a"))
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("err = %v", err)
	}
	if s.IsOpen() || s.LastChunkSeq() != 0 {
		t.Fatalf("open=%v seq=%d", s.IsOpen(), s.LastChunkSeq())
	}
}

func TestInsertSessionCancelledContext(t *testing.T) {
	srv, _, _ := newWSServer(t, func(ctx context.Context, f *wsFake, c *websocket.Conn) {
		f.recv(t, ctx, c)
		send(t, ctx, c, startedFrame)
		f.recv(t, ctx, c)
		_, _, _ = c.Read(ctx)
	})
	s, err := srv.DB("db").InsertSession(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	ctx, cancel := context.WithCancel(context.Background())
	time.AfterFunc(50*time.Millisecond, cancel)
	if _, err := s.SendChunk(ctx, recs("a")); !errors.Is(err, context.Canceled) {
		t.Fatalf("err = %v", err)
	}
	if s.IsOpen() {
		t.Fatal("still open")
	}
}

// A chunk over wsMaxInsertFrameSize is not answered with an error frame: the server drops
// the connection with 1009.
func TestInsertSessionOversizeFrameKillsTheConnection(t *testing.T) {
	srv, _, _ := newWSServer(t, func(ctx context.Context, f *wsFake, c *websocket.Conn) {
		f.recv(t, ctx, c)
		send(t, ctx, c, startedFrame)
		f.recv(t, ctx, c)
		_ = c.Close(websocket.StatusMessageTooBig, "frame too big")
	})
	ctx := context.Background()
	s, _ := srv.DB("db").InsertSession(ctx)
	defer s.Close()
	_, err := s.SendChunk(ctx, recs("a"))
	if err == nil || websocket.CloseStatus(errors.Unwrap(err)) != websocket.StatusMessageTooBig && !strings.Contains(err.Error(), "StatusMessageTooBig") {
		t.Fatalf("err = %v", err)
	}
	if s.IsOpen() {
		t.Fatal("still open")
	}
}

func TestInsertSessionStartRefused(t *testing.T) {
	srv, _, _ := newWSServer(t, func(ctx context.Context, f *wsFake, c *websocket.Conn) {
		f.recv(t, ctx, c)
		send(t, ctx, c, `{"result":"error","action":"error","error":"Insert session error","detail":"Database 'nope' does not exist"}`)
		_, _, _ = c.Read(ctx)
	})
	s, err := srv.DB("nope").InsertSession(context.Background())
	var serr *InsertSessionError
	if s != nil || !errors.As(err, &serr) || !strings.Contains(serr.Detail, "does not exist") {
		t.Fatalf("s=%v err=%v", s, err)
	}
}

func TestInsertSessionUnexpectedFrame(t *testing.T) {
	srv, _, _ := newWSServer(t, func(ctx context.Context, f *wsFake, c *websocket.Conn) {
		f.recv(t, ctx, c)
		send(t, ctx, c, startedFrame)
		f.recv(t, ctx, c)
		send(t, ctx, c, `{"result":"ok","action":"committed"}`)
		_, _, _ = c.Read(ctx)
	})
	ctx := context.Background()
	s, _ := srv.DB("db").InsertSession(ctx)
	defer s.Close()
	if _, err := s.SendChunk(ctx, recs("a")); err == nil || !strings.Contains(err.Error(), "unexpected frame") {
		t.Fatalf("err = %v", err)
	}
	if s.IsOpen() {
		t.Fatal("still open")
	}
}

func TestWebSocketURLKeepsThePathPrefix(t *testing.T) {
	for in, want := range map[string]string{
		"http://h:2480":        "http://h:2480/ws",
		"https://h/arcade/":    "https://h/arcade/ws",
		"http://h:2480/?x=1#f": "http://h:2480/ws",
	} {
		got, err := (&Server{baseURL: in}).webSocketURL()
		if err != nil || got != want {
			t.Errorf("%s -> %q, %v; want %q", in, got, err, want)
		}
	}
}

// errorEndsSession runs one chunk against an error frame and reports how it was classified.
func errorEndsSession(t *testing.T, frame string) (*InsertSessionError, bool) {
	t.Helper()
	srv, _, _ := newWSServer(t, func(ctx context.Context, f *wsFake, c *websocket.Conn) {
		f.recv(t, ctx, c)
		send(t, ctx, c, startedFrame)
		f.recv(t, ctx, c)
		send(t, ctx, c, frame)
		_, _, _ = c.Read(ctx)
	})
	ctx := context.Background()
	s, err := srv.DB("db").InsertSession(ctx)
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	_, err = s.SendChunk(ctx, recs("a"))
	var serr *InsertSessionError
	if !errors.As(err, &serr) {
		t.Fatalf("err = %v", err)
	}
	if _, err := s.SendChunk(ctx, recs("b")); s.IsOpen() == errors.Is(err, ErrInsertSessionClosed) {
		t.Fatalf("IsOpen=%v but next SendChunk = %v", s.IsOpen(), err)
	}
	return serr, s.IsOpen()
}

func TestInsertSessionSecurityErrorEndsTheSession(t *testing.T) {
	serr, open := errorEndsSession(t, `{"result":"error","action":"error","error":"Security error","detail":"User does not have access to database 'db'.","sessionId":"srv-1","exception":"java.lang.SecurityException"}`)
	if !serr.SessionEnded || open {
		t.Fatalf("SessionEnded=%v open=%v", serr.SessionEnded, open)
	}
}

func TestInsertSessionNotFoundEndsTheSession(t *testing.T) {
	serr, open := errorEndsSession(t, `{"result":"error","action":"error","error":"Insert session error","detail":"Insert session 'srv-1' not found or expired","sessionId":"srv-1"}`)
	if !serr.SessionEnded || open {
		t.Fatalf("SessionEnded=%v open=%v", serr.SessionEnded, open)
	}
}

func TestInsertSessionErrorClassification(t *testing.T) {
	for _, c := range []struct {
		title, detail string
		ended         bool
	}{
		{"Insert session expired", "idle", true},
		{"Security error", "Principal is gone", true},
		{"Internal error", "NPE", true},
		{"Insert session error", "Insert session 'x' is closed", true},
		{"Insert session error", "Insert session 'x' not found or expired", true},
		{"Insert session error", "Chunk 3 carries 5 records, more than the 4 allowed by 'arcadedb.server.wsMaxInsertChunkRows'. Split it into smaller chunks", false},
		{"Insert session error", "Chunk 3 skips ahead: session 'x' has applied up to chunk 1 and expects 2 next. Chunk sequences must be contiguous from 1", false},
		{"Insert session error", "Property 'records' is required and must be an array", false},
		{"Too many frames in flight", "...", false},
	} {
		if got := endsSession(c.title, c.detail); got != c.ended {
			t.Errorf("%s / %s: ended = %v, want %v", c.title, c.detail, got, c.ended)
		}
	}
}
