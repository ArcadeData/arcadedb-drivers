package arcadedbgrpc

import (
	"context"
	"errors"
	"io"
	"iter"
	"strings"
	"sync"
	"sync/atomic"
	"testing"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc/generated"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/proto"
)

// clientStreamService is a configurable fake for the two client-stream RPCs.
type clientStreamService struct {
	generated.UnimplementedArcadeDbServiceServer
	insert func(grpc.ClientStreamingServer[generated.InsertChunk, generated.InsertSummary]) error
	ts     func(grpc.ClientStreamingServer[generated.TimeSeriesWriteChunk, generated.TimeSeriesWriteSummary]) error
}

func (s clientStreamService) InsertStream(ss grpc.ClientStreamingServer[generated.InsertChunk, generated.InsertSummary]) error {
	return s.insert(ss)
}

func (s clientStreamService) TimeSeriesWriteStream(ss grpc.ClientStreamingServer[generated.TimeSeriesWriteChunk, generated.TimeSeriesWriteSummary]) error {
	return s.ts(ss)
}

// collect is a server handler that records every chunk it receives and answers reply.
// The chunks are read through the returned func once the call has returned.
func collect[Req, Res any](reply *Res) (func(grpc.ClientStreamingServer[Req, Res]) error, func() []*Req) {
	var mu sync.Mutex
	var got []*Req
	h := func(ss grpc.ClientStreamingServer[Req, Res]) error {
		for {
			m, err := ss.Recv()
			if errors.Is(err, io.EOF) {
				return ss.SendAndClose(reply)
			}
			if err != nil {
				return err
			}
			mu.Lock()
			got = append(got, m)
			mu.Unlock()
		}
	}
	return h, func() []*Req {
		mu.Lock()
		defer mu.Unlock()
		return got
	}
}

func batches[T any](bs ...[]T) iter.Seq[[]T] {
	return func(yield func([]T) bool) {
		for _, b := range bs {
			if !yield(b) {
				return
			}
		}
	}
}

func rec(rid string) *generated.GrpcRecord { return &generated.GrpcRecord{Rid: rid} }

func TestInsertStreamEnvelope(t *testing.T) {
	summary := &generated.InsertSummary{Received: 4, Inserted: 3, Failed: 1}
	h, chunks := collect[generated.InsertChunk](summary)
	c := newFake(t, clientStreamService{insert: h}, nil)

	creds := &generated.DatabaseCredentials{Username: "u", Password: "p"}
	tx := &generated.TransactionContext{TransactionId: "tx1"}
	got, err := c.InsertStream(context.Background(), InsertStreamRequest{
		Database:    "db",
		Chunks:      batches([]*generated.GrpcRecord{rec("a"), rec("b")}, []*generated.GrpcRecord{rec("c")}, []*generated.GrpcRecord{rec("d")}),
		Options:     &generated.InsertOptions{TargetClass: "V"},
		Credentials: creds,
		Transaction: tx,
	})
	if err != nil {
		t.Fatal(err)
	}
	if !proto.Equal(got, summary) {
		t.Fatalf("summary = %v, want %v", got, summary)
	}
	cs := chunks()
	if len(cs) != 3 {
		t.Fatalf("got %d chunks, want 3", len(cs))
	}
	sid := cs[0].SessionId
	if sid == "" {
		t.Fatal("session_id is empty")
	}
	wantRows := []int{2, 1, 1}
	for i, ch := range cs {
		if ch.SessionId != sid {
			t.Errorf("chunk %d session_id %q != %q", i, ch.SessionId, sid)
		}
		if ch.ChunkSeq != int64(i+1) {
			t.Errorf("chunk %d chunk_seq = %d", i, ch.ChunkSeq)
		}
		if ch.Last != (i == 2) {
			t.Errorf("chunk %d last = %v", i, ch.Last)
		}
		if len(ch.Rows) != wantRows[i] {
			t.Errorf("chunk %d has %d rows, want %d", i, len(ch.Rows), wantRows[i])
		}
		if !proto.Equal(ch.Credentials, creds) || !proto.Equal(ch.Transaction, tx) {
			t.Errorf("chunk %d credentials/transaction = %v / %v", i, ch.Credentials, ch.Transaction)
		}
	}
	if cs[0].Database != "db" {
		t.Errorf("first chunk database = %q", cs[0].Database)
	}
	if cs[0].Options.GetDatabase() != "db" || cs[0].Options.GetTargetClass() != "V" {
		t.Errorf("first chunk options = %v", cs[0].Options)
	}
	if cs[1].Database != "" || cs[2].Database != "" {
		t.Errorf("database repeated after the first chunk: %q %q", cs[1].Database, cs[2].Database)
	}
	if cs[1].Options.GetTargetClass() != "V" {
		t.Errorf("later chunk options = %v", cs[1].Options)
	}
}

func TestInsertStreamSessionIDIsFreshPerCall(t *testing.T) {
	h, chunks := collect[generated.InsertChunk](&generated.InsertSummary{})
	c := newFake(t, clientStreamService{insert: h}, nil)
	for range 2 {
		if _, err := c.InsertStream(context.Background(), InsertStreamRequest{Database: "db"}); err != nil {
			t.Fatal(err)
		}
	}
	cs := chunks()
	if len(cs) != 2 || cs[0].SessionId == cs[1].SessionId {
		t.Fatalf("session ids not distinct: %v", cs)
	}
	if len(cs[0].SessionId) != 32 {
		t.Fatalf("session id %q is not 16 hex-encoded bytes", cs[0].SessionId)
	}
}

func TestInsertStreamCallerOptionsNotMutated(t *testing.T) {
	h, _ := collect[generated.InsertChunk](&generated.InsertSummary{})
	c := newFake(t, clientStreamService{insert: h}, nil)
	opts := &generated.InsertOptions{TargetClass: "V", Database: "callers"}
	if _, err := c.InsertStream(context.Background(), InsertStreamRequest{
		Database: "db", Options: opts, Chunks: batches([]*generated.GrpcRecord{rec("a")}),
	}); err != nil {
		t.Fatal(err)
	}
	if opts.Database != "callers" {
		t.Fatalf("caller's Options.Database changed to %q", opts.Database)
	}
}

func TestInsertStreamEmptyInputSendsOneLastChunk(t *testing.T) {
	for name, seq := range map[string]iter.Seq[[]*generated.GrpcRecord]{
		"nil":   nil,
		"empty": batches[*generated.GrpcRecord](),
	} {
		t.Run(name, func(t *testing.T) {
			h, chunks := collect[generated.InsertChunk](&generated.InsertSummary{})
			c := newFake(t, clientStreamService{insert: h}, nil)
			if _, err := c.InsertStream(context.Background(), InsertStreamRequest{Database: "db", Chunks: seq}); err != nil {
				t.Fatal(err)
			}
			cs := chunks()
			if len(cs) != 1 {
				t.Fatalf("got %d chunks, want 1", len(cs))
			}
			if cs[0].ChunkSeq != 1 || !cs[0].Last || len(cs[0].Rows) != 0 || cs[0].Database != "db" || cs[0].Options.GetDatabase() != "db" {
				t.Fatalf("chunk = %v", cs[0])
			}
		})
	}
}

func TestInsertStreamEmptyMiddleBatchIsAChunk(t *testing.T) {
	h, chunks := collect[generated.InsertChunk](&generated.InsertSummary{})
	c := newFake(t, clientStreamService{insert: h}, nil)
	if _, err := c.InsertStream(context.Background(), InsertStreamRequest{
		Database: "db",
		Chunks:   batches([]*generated.GrpcRecord{rec("a")}, []*generated.GrpcRecord{}, []*generated.GrpcRecord{rec("b")}),
	}); err != nil {
		t.Fatal(err)
	}
	cs := chunks()
	if len(cs) != 3 || len(cs[1].Rows) != 0 || cs[0].Last || cs[1].Last || !cs[2].Last {
		t.Fatalf("chunks = %v", cs)
	}
}

func TestInsertStreamNilBatchIsNotTheEnd(t *testing.T) {
	h, chunks := collect[generated.InsertChunk](&generated.InsertSummary{})
	c := newFake(t, clientStreamService{insert: h}, nil)
	if _, err := c.InsertStream(context.Background(), InsertStreamRequest{
		Database: "db",
		Chunks:   batches([]*generated.GrpcRecord{rec("a")}, nil, []*generated.GrpcRecord{rec("b")}),
	}); err != nil {
		t.Fatal(err)
	}
	cs := chunks()
	if len(cs) != 3 || cs[2].ChunkSeq != 3 || !cs[2].Last || cs[2].Rows[0].Rid != "b" {
		t.Fatalf("chunks = %v", cs)
	}
}

// endless yields ever-growing batches until yield returns false, counting pulls and
// recording that it returned.
func endless(pulls *atomic.Int64, done *atomic.Bool) iter.Seq[[]*generated.GrpcRecord] {
	big := strings.Repeat("x", 4096)
	return func(yield func([]*generated.GrpcRecord) bool) {
		defer done.Store(true)
		for {
			pulls.Add(1)
			if !yield([]*generated.GrpcRecord{{Rid: big}}) {
				return
			}
		}
	}
}

func failAfterFirst(ss grpc.ClientStreamingServer[generated.InsertChunk, generated.InsertSummary]) error {
	if _, err := ss.Recv(); err != nil {
		return err
	}
	return status.Error(codes.InvalidArgument, "bad")
}

func TestInsertStreamSendErrorSurfacesServerStatus(t *testing.T) {
	c := newFake(t, clientStreamService{insert: failAfterFirst}, nil)
	var pulls atomic.Int64
	var done atomic.Bool
	_, err := c.InsertStream(context.Background(), InsertStreamRequest{Database: "db", Chunks: endless(&pulls, &done)})
	if status.Code(err) != codes.InvalidArgument {
		t.Fatalf("err = %v (code %v), want InvalidArgument", err, status.Code(err))
	}
}

func TestInsertStreamStopsIteratingOnError(t *testing.T) {
	c := newFake(t, clientStreamService{insert: failAfterFirst}, nil)
	var pulls atomic.Int64
	var done atomic.Bool
	if _, err := c.InsertStream(context.Background(), InsertStreamRequest{Database: "db", Chunks: endless(&pulls, &done)}); err == nil {
		t.Fatal("want an error")
	}
	// done means the seq function itself returned: it saw yield report false, so nothing
	// can pull it again. A seq abandoned without its stop func would still be parked.
	if !done.Load() {
		t.Fatalf("the caller's seq was not stopped (%d pulls)", pulls.Load())
	}
}

func TestInsertStreamSeqPanicStaysOnCaller(t *testing.T) {
	h, _ := collect[generated.InsertChunk](&generated.InsertSummary{})
	c := newFake(t, clientStreamService{insert: h}, nil)
	defer func() {
		if r := recover(); r != "boom" {
			t.Fatalf("recovered %v, want boom", r)
		}
	}()
	_, _ = c.InsertStream(context.Background(), InsertStreamRequest{
		Database: "db",
		Chunks: func(yield func([]*generated.GrpcRecord) bool) {
			if !yield([]*generated.GrpcRecord{rec("a")}) {
				return
			}
			panic("boom")
		},
	})
	t.Fatal("InsertStream returned instead of panicking")
}

func point(ts int64) *generated.TimeSeriesPoint { return &generated.TimeSeriesPoint{Timestamp: ts} }

func precision(p generated.TimeSeriesPrecision) *generated.TimeSeriesPrecision { return &p }

func TestTimeSeriesWriteStreamRepeatsHeaderFields(t *testing.T) {
	summary := &generated.TimeSeriesWriteSummary{Received: 3, Written: 2, Dropped: 1, UnknownTypes: []string{"x"}}
	h, chunks := collect[generated.TimeSeriesWriteChunk](summary)
	c := newFake(t, clientStreamService{ts: h}, nil)
	creds := &generated.DatabaseCredentials{Username: "u"}
	got, err := c.TimeSeriesWriteStream(context.Background(), TimeSeriesWriteStreamRequest{
		Database:    "db",
		Type:        "Weather",
		Precision:   precision(generated.TimeSeriesPrecision_TS_PRECISION_MILLISECONDS),
		Credentials: creds,
		Chunks:      batches([]*generated.TimeSeriesPoint{point(1), point(2)}, []*generated.TimeSeriesPoint{point(3)}),
	})
	if err != nil {
		t.Fatal(err)
	}
	if !proto.Equal(got, summary) {
		t.Fatalf("summary = %v, want %v", got, summary)
	}
	cs := chunks()
	if len(cs) != 2 {
		t.Fatalf("got %d chunks, want 2", len(cs))
	}
	for i, ch := range cs {
		if ch.Database != "db" || ch.Type != "Weather" || ch.Precision != generated.TimeSeriesPrecision_TS_PRECISION_MILLISECONDS || !proto.Equal(ch.Credentials, creds) {
			t.Errorf("chunk %d header = %v", i, ch)
		}
	}
	if len(cs[0].Points) != 2 || len(cs[1].Points) != 1 {
		t.Errorf("points per chunk: %d, %d", len(cs[0].Points), len(cs[1].Points))
	}

	// A non-zero precision travels too.
	h2, chunks2 := collect[generated.TimeSeriesWriteChunk](summary)
	c2 := newFake(t, clientStreamService{ts: h2}, nil)
	if _, err := c2.TimeSeriesWriteStream(context.Background(), TimeSeriesWriteStreamRequest{
		Database: "db", Type: "Weather",
		Precision: precision(generated.TimeSeriesPrecision_TS_PRECISION_NANOSECONDS),
		Chunks:    batches([]*generated.TimeSeriesPoint{point(1)}),
	}); err != nil {
		t.Fatal(err)
	}
	if cs := chunks2(); len(cs) != 1 || cs[0].Precision != generated.TimeSeriesPrecision_TS_PRECISION_NANOSECONDS {
		t.Fatalf("chunks = %v", cs)
	}
}

func TestTimeSeriesWriteStreamRequiresPrecision(t *testing.T) {
	c, rec := newRecordingFake(t, clientStreamService{ts: func(grpc.ClientStreamingServer[generated.TimeSeriesWriteChunk, generated.TimeSeriesWriteSummary]) error {
		return nil
	}}, nil)
	_, err := c.TimeSeriesWriteStream(context.Background(), TimeSeriesWriteStreamRequest{
		Database: "db", Type: "Weather",
		Chunks: batches([]*generated.TimeSeriesPoint{point(1)}),
	})
	if err == nil || !strings.Contains(err.Error(), "Precision") {
		t.Fatalf("err = %v, want a Precision error", err)
	}
	rec.mu.Lock()
	defer rec.mu.Unlock()
	if len(rec.calls) != 0 {
		t.Fatalf("an RPC was made: %v", rec.calls)
	}
}

func TestTimeSeriesWriteStreamEmptyInputSendsZeroChunks(t *testing.T) {
	for name, seq := range map[string]iter.Seq[[]*generated.TimeSeriesPoint]{
		"nil":   nil,
		"empty": batches[*generated.TimeSeriesPoint](),
	} {
		t.Run(name, func(t *testing.T) {
			h, chunks := collect[generated.TimeSeriesWriteChunk](&generated.TimeSeriesWriteSummary{})
			c := newFake(t, clientStreamService{ts: h}, nil)
			if _, err := c.TimeSeriesWriteStream(context.Background(), TimeSeriesWriteStreamRequest{
				Database: "db", Type: "Weather",
				Precision: precision(generated.TimeSeriesPrecision_TS_PRECISION_SECONDS),
				Chunks:    seq,
			}); err != nil {
				t.Fatal(err)
			}
			if cs := chunks(); len(cs) != 0 {
				t.Fatalf("got %d chunks, want 0", len(cs))
			}
		})
	}
}

func TestTimeSeriesWriteStreamSendErrorSurfacesServerStatus(t *testing.T) {
	c := newFake(t, clientStreamService{ts: func(ss grpc.ClientStreamingServer[generated.TimeSeriesWriteChunk, generated.TimeSeriesWriteSummary]) error {
		if _, err := ss.Recv(); err != nil {
			return err
		}
		return status.Error(codes.FailedPrecondition, "nope")
	}}, nil)
	var done atomic.Bool
	big := strings.Repeat("x", 4096)
	_, err := c.TimeSeriesWriteStream(context.Background(), TimeSeriesWriteStreamRequest{
		Database: "db", Type: "Weather",
		Precision: precision(generated.TimeSeriesPrecision_TS_PRECISION_MILLISECONDS),
		Chunks: func(yield func([]*generated.TimeSeriesPoint) bool) {
			defer done.Store(true)
			for {
				if !yield([]*generated.TimeSeriesPoint{{Type: big}}) {
					return
				}
			}
		},
	})
	if status.Code(err) != codes.FailedPrecondition {
		t.Fatalf("err = %v (code %v), want FailedPrecondition", err, status.Code(err))
	}
	if !done.Load() {
		t.Fatal("the caller's seq was not stopped")
	}
}
