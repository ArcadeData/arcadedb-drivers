package arcadedbgrpc

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"io"
	"iter"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc/generated"
	"google.golang.org/grpc"
	"google.golang.org/protobuf/proto"
)

// Both client-stream wrappers iterate the caller's sequence on the caller's own goroutine:
// grpc-go's Send runs there too, so there is no io.Pipe and no background writer. A panic
// in the caller's sequence surfaces from the wrapper call itself, the RPC is cancelled on
// the way out, and nothing the wrapper started outlives it.
//
// When a Send fails with io.EOF, the wrappers return the error from CloseAndRecv instead.
// grpc-go reports a stream the server has already ended as a bare io.EOF from Send and
// puts the real status on the receive side; returning the Send error would hide every
// server-side failure (InvalidArgument, PermissionDenied, ...) behind EOF. A Send error
// other than io.EOF is grpc-go's own status for a stream it aborted, and is returned as is.

// InsertStreamRequest is a client-streaming insert.
//
// Chunks is the sequence of row batches to send; each batch becomes exactly one wire
// InsertChunk, so batching is the caller's choice. A nil Chunks is an empty input. The
// wrapper owns the envelope around those batches; see InsertStream.
//
// Options, Credentials and Transaction are never modified. Transaction is set on every
// chunk as given, because the .proto declares the field; servers from 26.9.1 on honour it
// (ArcadeData/arcadedb#6607), 26.8.1 and earlier ignored it.
type InsertStreamRequest struct {
	Database    string
	Chunks      iter.Seq[[]*generated.GrpcRecord]
	Options     *generated.InsertOptions
	Credentials *generated.DatabaseCredentials
	Transaction *generated.TransactionContext
}

// InsertStream streams rows to the server and returns its single InsertSummary unchanged.
//
// It ports the Python client's envelope:
//
//   - one session_id per call, 16 random bytes hex-encoded, stable for the whole stream;
//   - chunk_seq 1, 2, 3, ...;
//   - Database on the first chunk only, as the .proto specifies, and mirrored into a copy
//     of Options as options.database on that chunk. Servers before 26.9.1 built their
//     insert context from options.database alone and never read the chunk's database
//     (ArcadeData/arcadedb#6597), inserting nothing without the mirror; later servers prefer
//     the chunk's database and fall back to the options one, so setting both is correct on
//     either side of the fix. Later chunks carry the caller's Options unchanged;
//   - Credentials and Transaction on every chunk;
//   - last=true on the final chunk only. That chunk is found by one batch of lookahead, so
//     a nil or empty batch in the middle of the sequence is sent as a chunk with zero rows,
//     never mistaken for the end of the stream.
//
// An empty input is not an error: it sends one chunk with chunk_seq 1, last=true and no
// rows, and returns whatever summary the server answers.
//
// The caller's sequence is pulled on the caller's goroutine (iter.Pull, for the
// lookahead), and is always stopped before InsertStream returns, including when the RPC
// fails part-way: rows already sent stay sent, the remainder is never pulled.
func (c *Client) InsertStream(ctx context.Context, req InsertStreamRequest, opts ...grpc.CallOption) (*generated.InsertSummary, error) {
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	stream, err := c.raw.InsertStream(ctx, opts...)
	if err != nil {
		return nil, err
	}

	firstOptions := &generated.InsertOptions{}
	if req.Options != nil {
		firstOptions = proto.Clone(req.Options).(*generated.InsertOptions)
	}
	firstOptions.Database = req.Database
	sessionID := newSessionID()
	chunk := func(seq int64, rows []*generated.GrpcRecord, last bool) *generated.InsertChunk {
		ch := &generated.InsertChunk{
			SessionId:   sessionID,
			ChunkSeq:    seq,
			Rows:        rows,
			Last:        last,
			Credentials: req.Credentials,
			Transaction: req.Transaction,
			Options:     req.Options,
		}
		if seq == 1 {
			ch.Database = req.Database
			ch.Options = firstOptions
		}
		return ch
	}

	chunks := req.Chunks
	if chunks == nil {
		chunks = func(func([]*generated.GrpcRecord) bool) {}
	}
	next, stop := iter.Pull(chunks)
	defer stop()

	current, ok := next()
	if !ok {
		if err := stream.Send(chunk(1, nil, true)); err != nil {
			return failedSend(stream, err)
		}
		return stream.CloseAndRecv()
	}
	for seq := int64(1); ; seq++ {
		following, more := next()
		if err := stream.Send(chunk(seq, current, !more)); err != nil {
			return failedSend(stream, err)
		}
		if !more {
			return stream.CloseAndRecv()
		}
		current = following
	}
}

// TimeSeriesWriteStreamRequest is a client-streaming time-series write.
//
// Chunks is the sequence of point batches to send; each batch becomes exactly one wire
// TimeSeriesWriteChunk. A nil Chunks is an empty input. Database, Type, Precision and
// Credentials are repeated on every chunk: the message has no session, sequence or last
// field, and the server ignores database after the first chunk, so the repetition is
// harmless and spares a first-chunk special case. A single stream-wide Type cannot
// express the contract's per-chunk default measurement; to mix measurements in one
// stream, set Type on each TimeSeriesPoint instead.
//
// Precision is required (D-M6-1) and is a pointer for that reason. The generated
// TimeSeriesPrecision's zero value is TS_PRECISION_MILLISECONDS, a real unit, so a plain
// enum field could not tell "unset" from "milliseconds". The HTTP /ts write endpoint
// speaks InfluxDB line protocol, whose omitted precision means nanoseconds, a factor of
// 10^6 away: an ingest ported from HTTP that forgot this field would have every timestamp
// silently misread. A nil Precision is an error from TimeSeriesWriteStream before any RPC.
//
// There is no Transaction field: TimeSeriesWriteChunk has none on the wire.
type TimeSeriesWriteStreamRequest struct {
	Database    string
	Type        string
	Precision   *generated.TimeSeriesPrecision
	Credentials *generated.DatabaseCredentials
	Chunks      iter.Seq[[]*generated.TimeSeriesPoint]
}

// TimeSeriesWriteStream streams points to the server and returns its
// TimeSeriesWriteSummary whole.
//
// A write is not atomic: each measurement's batch commits its own shard transaction as it
// is appended, so a call that returns no error can still report Written < Received, with
// the reasons in UnknownTypes, NonTimeSeriesTypes and UnavailableTypes. Returning without
// an error does not mean every point landed; check the summary.
//
// An empty input sends zero chunks, unlike InsertStream: there is no last flag to carry.
// Measured against a real server, such a stream is accepted and answered with an all-zero
// summary, which is returned as is.
//
// The caller's sequence is ranged over on the caller's goroutine and stops being pulled
// as soon as a Send fails.
func (c *Client) TimeSeriesWriteStream(ctx context.Context, req TimeSeriesWriteStreamRequest, opts ...grpc.CallOption) (*generated.TimeSeriesWriteSummary, error) {
	if req.Precision == nil {
		return nil, errors.New("arcadedbgrpc: TimeSeriesWriteStream: Precision is required; the proto default " +
			"(milliseconds) differs from HTTP line protocol's (nanoseconds), so it is never assumed")
	}
	precision := *req.Precision

	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	stream, err := c.raw.TimeSeriesWriteStream(ctx, opts...)
	if err != nil {
		return nil, err
	}
	if req.Chunks != nil {
		for points := range req.Chunks {
			err := stream.Send(&generated.TimeSeriesWriteChunk{
				Database:    req.Database,
				Credentials: req.Credentials,
				Type:        req.Type,
				Precision:   precision,
				Points:      points,
			})
			if err != nil {
				return failedSend(stream, err)
			}
		}
	}
	return stream.CloseAndRecv()
}

// failedSend turns a Send error into the call's result. io.EOF means the server already
// ended the stream, and its status (or, if it answered early, its reply) is on the receive
// side; any other error is grpc-go's own status for an aborted stream.
func failedSend[Req, Res any](stream grpc.ClientStreamingClient[Req, Res], err error) (*Res, error) {
	if errors.Is(err, io.EOF) {
		return stream.CloseAndRecv()
	}
	return nil, err
}

// newSessionID returns 16 random bytes, hex-encoded. crypto/rand.Read never fails.
func newSessionID() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}
