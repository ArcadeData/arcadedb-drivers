package arcadedbgrpc

import (
	"context"
	"errors"
	"io"
	"iter"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc/generated"
	"google.golang.org/grpc"
)

// recvAll turns a server-stream RPC into an iterator of its messages.
//
// The RPC is opened lazily, on the first iteration, so each range over the returned
// sequence issues a new RPC: the sequence is a recipe, not a cursor. A context derived
// from ctx is handed to open and cancelled on every exit (exhaustion, error, or the
// caller breaking out), which tells the server to stop producing. io.EOF ends iteration
// normally. Any other error, whether from opening the stream or from a receive, is
// yielded once as (nil, err), unwrapped so status.Code(err) still works, and iteration
// then ends. yield is never called again after it returned false.
func recvAll[T any](ctx context.Context, open func(context.Context) (grpc.ServerStreamingClient[T], error)) iter.Seq2[*T, error] {
	return func(yield func(*T, error) bool) {
		ctx, cancel := context.WithCancel(ctx)
		defer cancel()
		stream, err := open(ctx)
		if err != nil {
			yield(nil, err)
			return
		}
		for {
			msg, err := stream.Recv()
			if err != nil {
				if !errors.Is(err, io.EOF) {
					yield(nil, err)
				}
				return
			}
			if !yield(msg, nil) {
				return
			}
		}
	}
}

// StreamQuery runs a streaming query and yields its records one at a time, flattening the
// server's QueryResult batches; batch boundaries, TotalRecordsInBatch and IsLastBatch are
// not surfaced. req is sent as given, so RetrievalMode and BatchSize take effect on the
// server.
//
// The returned iterator is lazy and re-rangeable: nothing is sent until the first
// iteration, and each range issues a new RPC (re-running the query). Breaking out of the
// loop cancels the server stream. A failure, including one in the middle of the stream,
// arrives as a final (nil, err) pair carrying the grpc-go status error unchanged; records
// already yielded stay yielded.
func (c *Client) StreamQuery(ctx context.Context, req *generated.StreamQueryRequest, opts ...grpc.CallOption) iter.Seq2[*generated.GrpcRecord, error] {
	batches := recvAll(ctx, func(ctx context.Context) (grpc.ServerStreamingClient[generated.QueryResult], error) {
		return c.raw.StreamQuery(ctx, req, opts...)
	})
	return func(yield func(*generated.GrpcRecord, error) bool) {
		for batch, err := range batches {
			if err != nil {
				yield(nil, err)
				return
			}
			for _, r := range batch.GetRecords() {
				if !yield(r, nil) {
					return
				}
			}
		}
	}
}

// TimeSeriesQuery runs a time-series query and yields each server message whole, with its
// rows, buckets and running total intact. Only the final message has Last set, and
// Truncated is meaningful only there: it reports that the result was cut short and the
// stream does not hold every matching row.
//
// The returned iterator has the same lazy, re-rangeable, cancel-on-break and error
// behaviour as StreamQuery.
func (c *Client) TimeSeriesQuery(ctx context.Context, req *generated.TimeSeriesQueryRequest, opts ...grpc.CallOption) iter.Seq2[*generated.TimeSeriesQueryResult, error] {
	return recvAll(ctx, func(ctx context.Context) (grpc.ServerStreamingClient[generated.TimeSeriesQueryResult], error) {
		return c.raw.TimeSeriesQuery(ctx, req, opts...)
	})
}
