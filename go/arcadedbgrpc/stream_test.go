package arcadedbgrpc

import (
	"context"
	"sync/atomic"
	"testing"
	"time"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc/generated"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// streamService is a configurable fake for the two server-stream RPCs.
type streamService struct {
	generated.UnimplementedArcadeDbServiceServer
	query func(*generated.StreamQueryRequest, grpc.ServerStreamingServer[generated.QueryResult]) error
	ts    func(*generated.TimeSeriesQueryRequest, grpc.ServerStreamingServer[generated.TimeSeriesQueryResult]) error
}

func (s streamService) StreamQuery(r *generated.StreamQueryRequest, ss grpc.ServerStreamingServer[generated.QueryResult]) error {
	return s.query(r, ss)
}

func (s streamService) TimeSeriesQuery(r *generated.TimeSeriesQueryRequest, ss grpc.ServerStreamingServer[generated.TimeSeriesQueryResult]) error {
	return s.ts(r, ss)
}

func recs(rids ...string) *generated.QueryResult {
	q := &generated.QueryResult{}
	for _, r := range rids {
		q.Records = append(q.Records, &generated.GrpcRecord{Rid: r})
	}
	return q
}

func TestStreamQueryFlattensBatches(t *testing.T) {
	c := newFake(t, streamService{query: func(_ *generated.StreamQueryRequest, s grpc.ServerStreamingServer[generated.QueryResult]) error {
		if err := s.Send(recs("#1:0", "#1:1")); err != nil {
			return err
		}
		return s.Send(recs("#1:2"))
	}}, nil)
	var got []string
	for r, err := range c.StreamQuery(context.Background(), &generated.StreamQueryRequest{}) {
		if err != nil {
			t.Fatal(err)
		}
		got = append(got, r.Rid)
	}
	if len(got) != 3 || got[0] != "#1:0" || got[1] != "#1:1" || got[2] != "#1:2" {
		t.Fatalf("got %v", got)
	}
}

func TestStreamQueryPassesRequestUntouched(t *testing.T) {
	var seen *generated.StreamQueryRequest
	c := newFake(t, streamService{query: func(r *generated.StreamQueryRequest, _ grpc.ServerStreamingServer[generated.QueryResult]) error {
		seen = r
		return nil
	}}, nil)
	req := &generated.StreamQueryRequest{Query: "select", BatchSize: 7, RetrievalMode: generated.StreamQueryRequest_PAGED}
	for range c.StreamQuery(context.Background(), req) {
	}
	if seen == nil || seen.Query != "select" || seen.BatchSize != 7 || seen.RetrievalMode != generated.StreamQueryRequest_PAGED {
		t.Fatalf("server saw %v", seen)
	}
}

func TestStreamQueryMidStreamErrorKeepsStatus(t *testing.T) {
	c := newFake(t, streamService{query: func(_ *generated.StreamQueryRequest, s grpc.ServerStreamingServer[generated.QueryResult]) error {
		if err := s.Send(recs("#1:0")); err != nil {
			return err
		}
		return status.Error(codes.Aborted, "x")
	}}, nil)
	records, errs := 0, 0
	for r, err := range c.StreamQuery(context.Background(), &generated.StreamQueryRequest{}) {
		if err != nil {
			errs++
			if status.Code(err) != codes.Aborted {
				t.Fatalf("code = %v", status.Code(err))
			}
			if r != nil {
				t.Fatal("record yielded alongside error")
			}
			continue
		}
		records++
	}
	if records != 1 || errs != 1 {
		t.Fatalf("records=%d errs=%d", records, errs)
	}
}

func TestStreamQueryBreakCancelsServerStream(t *testing.T) {
	done := make(chan struct{})
	c := newFake(t, streamService{query: func(_ *generated.StreamQueryRequest, s grpc.ServerStreamingServer[generated.QueryResult]) error {
		if err := s.Send(recs("#1:0", "#1:1")); err != nil {
			return err
		}
		<-s.Context().Done()
		close(done)
		return s.Context().Err()
	}}, nil)
	for range c.StreamQuery(context.Background(), &generated.StreamQueryRequest{}) {
		break
	}
	select {
	case <-done:
	case <-time.After(5 * time.Second):
		t.Fatal("server stream was not cancelled after break")
	}
}

func TestStreamQueryEmptyStream(t *testing.T) {
	c := newFake(t, streamService{query: func(*generated.StreamQueryRequest, grpc.ServerStreamingServer[generated.QueryResult]) error {
		return nil
	}}, nil)
	for r, err := range c.StreamQuery(context.Background(), &generated.StreamQueryRequest{}) {
		t.Fatalf("unexpected event %v %v", r, err)
	}
}

func TestTimeSeriesQueryYieldsWholeMessages(t *testing.T) {
	c := newFake(t, streamService{ts: func(_ *generated.TimeSeriesQueryRequest, s grpc.ServerStreamingServer[generated.TimeSeriesQueryResult]) error {
		if err := s.Send(&generated.TimeSeriesQueryResult{Type: "m", RunningTotalEmitted: 1}); err != nil {
			return err
		}
		return s.Send(&generated.TimeSeriesQueryResult{Type: "m", RunningTotalEmitted: 2, Last: true, Truncated: true})
	}}, nil)
	var got []*generated.TimeSeriesQueryResult
	for m, err := range c.TimeSeriesQuery(context.Background(), &generated.TimeSeriesQueryRequest{}) {
		if err != nil {
			t.Fatal(err)
		}
		got = append(got, m)
	}
	if len(got) != 2 || got[0].Last || !got[1].Last || !got[1].Truncated || got[1].RunningTotalEmitted != 2 {
		t.Fatalf("got %v", got)
	}
}

func TestEachRangeIssuesANewRPC(t *testing.T) {
	var calls atomic.Int32
	c := newFake(t, streamService{query: func(*generated.StreamQueryRequest, grpc.ServerStreamingServer[generated.QueryResult]) error {
		calls.Add(1)
		return nil
	}}, nil)
	seq := c.StreamQuery(context.Background(), &generated.StreamQueryRequest{})
	if calls.Load() != 0 {
		t.Fatal("RPC issued before iteration")
	}
	for range seq {
	}
	for range seq {
	}
	if n := calls.Load(); n != 2 {
		t.Fatalf("calls = %d, want 2", n)
	}
}
