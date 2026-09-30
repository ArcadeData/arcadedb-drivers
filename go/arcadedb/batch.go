package arcadedb

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"iter"
	"net/http"
	"sync"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/internal/batchrows"
	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/internal/ndjson"
)

// VertexRow is a vertex for BatchLoad to create.
//
// Type is the vertex type name, e.g. "Person", sent as @class. ID is an optional temporary
// id: an edge's From/To in the same call can reference it, and the summary's idMapping
// maps it to the RID it got. An empty ID is not sent, and such vertices are counted in
// the summary's verticesWithoutId. Properties are flattened beside the control keys, never
// nested; a property named @type, @class, @id, @from or @to is rejected with
// ErrPropertyShadowsControlKey.
type VertexRow struct {
	Type       string
	ID         string
	Properties map[string]any
}

// EdgeRow is an edge for BatchLoad to create. Type is the edge type name, sent as @class.
// From and To each take either a temporary id declared by a vertex in this same call, or a
// literal "#bucket:position" RID. Properties follow VertexRow's rules.
type EdgeRow struct {
	Type       string
	From       string
	To         string
	Properties map[string]any
}

// ErrPropertyShadowsControlKey is wrapped by the error BatchLoad and BatchLoadStream return
// when a row's Properties contain one of the control keys @type, @class, @id, @from or
// @to. Match it with errors.Is; the message names the row and the key. The Python driver
// lets such a property silently override the control key; this one refuses the row.
var ErrPropertyShadowsControlKey = batchrows.ErrPropertyShadowsControlKey

const (
	ndjsonMediaType   = "application/x-ndjson"
	defaultBatchError = "the batch load reported an error"
	uploadBufferSize  = 64 << 10
)

// BatchLoad bulk-loads vertices and edges in one call to POST /api/v1/batch/{database} and
// returns the server's summary as parsed JSON, unaltered: the contract's BatchResponse
// shape (verticesCreated, edgesCreated, idMapping, idMappingOmitted, idMappingSize,
// partialCommit, ...). params carries the endpoint's tuning options and may be nil; its
// Accept field is ignored here, because this call decodes one JSON object (use
// BatchLoadStream for ndjson). A nil vertices or edges sequence means none.
//
// Every vertex is sent before any edge, whatever order the caller built them in: the
// server resolves an edge's From/To only against ids declared earlier in the same payload.
//
// The body is streamed: rows are encoded as the sequences yield them and written through an
// io.Pipe, so a load larger than memory is never buffered. The sequences are consumed on a
// separate goroutine, which the call always stops and waits for before returning, so no
// sequence is iterated after the call returns; a sequence that blocks forever therefore
// blocks the call. Each sequence is iterated at most once.
//
// A load is NOT atomic: the server commits every commitEvery records, so a failure partway
// through leaves earlier chunks durably committed, and an error from a failed load can
// still correspond to real data. Because temporary ids are not keys, retrying the whole
// payload duplicates whatever already committed rather than resuming. The same holds for a
// row that fails validation (ErrPropertyShadowsControlKey, or a property that does not
// encode as JSON): the upload is aborted at that row, which is never sent, but rows before
// it may already have been sent and committed. Use BatchLoadStream to see how far a load
// got before it failed.
//
// A non-2xx status is an *ArcadeDBError. A row validation error is returned in preference
// to the transport or status error the aborted upload causes.
func (d *Database) BatchLoad(ctx context.Context, vertices iter.Seq[VertexRow], edges iter.Seq[EdgeRow], params *generated.ExecuteBatchParams) (map[string]any, error) {
	p := copyBatchParams(params)
	p.Accept = nil
	up := startUpload(vertices, edges)
	resp, err := d.srv.raw.ExecuteBatchWithBody(ctx, d.name, &p, ndjsonMediaType, up.body)
	if err != nil {
		return nil, up.fail(err)
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, up.fail(errorFromResponse(resp))
	}
	body, err := io.ReadAll(resp.Body)
	_ = resp.Body.Close()
	if err != nil {
		return nil, up.fail(err)
	}
	if err := up.stop(); err != nil {
		return nil, err
	}
	var summary map[string]any
	if err := json.Unmarshal(body, &summary); err != nil {
		return nil, fmt.Errorf("arcadedb: decode batch response: %w", err)
	}
	return summary, nil
}

// BatchLoadStream runs the same load as BatchLoad but asks for application/x-ndjson, and
// yields each event as parsed JSON, as received: a progress event at every vertex commit
// and every commitEvery edges, then exactly one summary event carrying what BatchLoad
// would have returned, with idMappingStreamed in place of idMapping. The request is
// issued on first iteration; the caller's params are not modified.
//
// A progress event's idMapping is only the fragment that chunk resolved. Fragments are
// never merged across events, since accumulating them would rebuild client-side the
// memory cost streaming exists to avoid; a caller that needs the whole mapping collects it
// as the events arrive.
//
// A load can fail two ways: before the first line, with a real non-2xx status, or after
// it, in band, as an {"error":{...}} event, because the 200 status line is already on the
// wire. Both are yielded as an *ArcadeDBError, once, and iteration then stops. An in-band
// error carries its own status (500 when absent), its error message ("the batch load
// reported an error" when absent), and exception and exceptionArgs when present. Events
// yielded before the error stay delivered: a partial commit is durable, and those progress
// counts are how the caller learns what may have landed. The non-atomic rules, the
// validation rules and the sequence-goroutine rules are BatchLoad's; breaking out of the
// loop aborts the upload and waits for that goroutine.
func (d *Database) BatchLoadStream(ctx context.Context, vertices iter.Seq[VertexRow], edges iter.Seq[EdgeRow], params *generated.ExecuteBatchParams) iter.Seq2[map[string]any, error] {
	return func(yield func(map[string]any, error) bool) {
		p := copyBatchParams(params)
		accept := generated.ExecuteBatchParamsAcceptApplicationxNdjson
		p.Accept = &accept
		up := startUpload(vertices, edges)
		defer func() { _ = up.stop() }()
		resp, err := d.srv.raw.ExecuteBatchWithBody(ctx, d.name, &p, ndjsonMediaType, up.body)
		if err != nil {
			yield(nil, up.fail(err))
			return
		}
		if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			yield(nil, up.fail(errorFromResponse(resp)))
			return
		}
		defer resp.Body.Close()
		requestID := resp.Header.Get(requestIDHeader)
		for line, err := range ndjson.Lines(resp.Body) {
			if err != nil {
				yield(nil, up.fail(err))
				return
			}
			ev, err := decodeBatchEvent(line, requestID)
			if err != nil {
				yield(nil, up.fail(err))
				return
			}
			if !yield(ev, nil) {
				return
			}
		}
		// The response ended cleanly; an upload that failed validation still failed.
		if err := up.stop(); err != nil {
			yield(nil, err)
		}
	}
}

func copyBatchParams(params *generated.ExecuteBatchParams) generated.ExecuteBatchParams {
	if params == nil {
		return generated.ExecuteBatchParams{}
	}
	return *params
}

// upload feeds the encoded rows into a pipe from its own goroutine.
type upload struct {
	body *io.PipeReader
	done chan error
	once sync.Once
	err  error
}

func startUpload(vertices iter.Seq[VertexRow], edges iter.Seq[EdgeRow]) *upload {
	pr, pw := io.Pipe()
	up := &upload{body: pr, done: make(chan error, 1)}
	go func() {
		bw := bufio.NewWriterSize(pw, uploadBufferSize)
		err := batchrows.Write(bw, vertexSeq(vertices), edgeSeq(edges))
		if err == nil {
			err = bw.Flush()
		}
		// A nil err closes the body with EOF; any other aborts the request with it.
		_ = pw.CloseWithError(err)
		up.done <- err
	}()
	return up
}

// stop closes the pipe's read side, so a writer still running gets io.ErrClosedPipe on its
// next write and stops iterating, then waits for it. It returns the writer's own failure
// (a row that did not validate or encode), or nil when the writer succeeded or only lost
// its pipe. The transport also closes the read side when a request fails, which is where
// that io.ErrClosedPipe comes from: it is derived, never the cause, so it is not reported.
func (u *upload) stop() error {
	u.once.Do(func() {
		_ = u.body.Close()
		if err := <-u.done; err != nil && !errors.Is(err, io.ErrClosedPipe) {
			u.err = err
		}
	})
	return u.err
}

// fail stops the upload and returns its own failure in preference to err, which is then
// a consequence of the aborted body.
func (u *upload) fail(err error) error {
	if uerr := u.stop(); uerr != nil {
		return uerr
	}
	return err
}

func vertexSeq(s iter.Seq[VertexRow]) iter.Seq[batchrows.Vertex] {
	if s == nil {
		return nil
	}
	return func(yield func(batchrows.Vertex) bool) {
		for v := range s {
			if !yield(batchrows.Vertex(v)) {
				return
			}
		}
	}
}

func edgeSeq(s iter.Seq[EdgeRow]) iter.Seq[batchrows.Edge] {
	if s == nil {
		return nil
	}
	return func(yield func(batchrows.Edge) bool) {
		for e := range s {
			if !yield(batchrows.Edge(e)) {
				return
			}
		}
	}
}

// decodeBatchEvent returns the event as parsed, or an *ArcadeDBError for an in-band error
// event. The contract's error object declares only commitIndex, status and exceptionArgs,
// but the server also sends error and exception, so all are read off the raw map.
func decodeBatchEvent(line []byte, requestID string) (map[string]any, error) {
	var ev map[string]any
	if err := json.Unmarshal(line, &ev); err != nil {
		return nil, fmt.Errorf("arcadedb: decode batch event: %w", err)
	}
	raw, ok := ev["error"]
	if !ok || raw == nil {
		return ev, nil
	}
	fields, _ := raw.(map[string]any)
	e := &ArcadeDBError{Status: http.StatusInternalServerError, ErrorMessage: defaultBatchError, RequestID: requestID}
	if s, ok := fields["status"].(float64); ok {
		e.Status = int(s)
	}
	if s, _ := fields["error"].(string); s != "" {
		e.ErrorMessage = s
	}
	e.Exception, _ = fields["exception"].(string)
	switch args := fields["exceptionArgs"].(type) {
	case nil:
	case string:
		e.ExceptionArgs = args
	default:
		if b, err := json.Marshal(args); err == nil {
			e.ExceptionArgs = string(b)
		}
	}
	return nil, e
}
