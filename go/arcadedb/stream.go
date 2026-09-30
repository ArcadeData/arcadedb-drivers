package arcadedb

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"iter"
	"net/http"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/internal/ndjson"
)

// StreamStats is the trailer of a complete stream: the same limit, returned and truncated
// the buffered QueryEnvelope reports. As there, an omitted limit reads as -1 (uncapped).
type StreamStats struct {
	Limit     int
	Returned  int
	Truncated bool
}

// StreamEvent is one event of a stream: exactly one of Record and Stats is set. An in-band
// error event is never yielded as an event; it arrives as the error of the iteration.
type StreamEvent struct {
	Record map[string]any
	Stats  *StreamStats
}

const defaultStreamError = "the stream reported an error"

// QueryStream runs a read statement and yields its rows as they arrive. The request is
// issued on first iteration, and the response body is closed when iteration ends by any
// route, including the consumer breaking out.
//
// The stats trailer is last in a complete stream, so a stream that ends without a Stats
// event was cut short (a server write timeout, a dropped connection) and the rows seen
// may be a partial answer. An in-band error, sent after the 200 status line, is yielded
// once as an *ArcadeDBError with status 200, and iteration then stops; so does a
// transport or decode error. Events of an unknown kind are ignored, so a newer server can
// add kinds without breaking this client. A non-2xx status is an *ArcadeDBError.
func (d *Database) QueryStream(ctx context.Context, lang QueryLanguage, command string, params map[string]any, opts ...QueryOption) iter.Seq2[StreamEvent, error] {
	return d.stream(func() (io.ReadCloser, error) {
		accept := generated.ExecuteQueryPostParamsAcceptApplicationxNdjson
		resp, err := d.srv.raw.ExecuteQueryPost(ctx, d.name,
			&generated.ExecuteQueryPostParams{ArcadedbSessionId: d.sessionParam(), Accept: &accept},
			buildQueryRequest(lang, command, params, opts...))
		return unpackStream(resp, err)
	})
}

// CommandStream is QueryStream for /command. It accepts read-only statements only: the
// server streams rows for a statement that produces them, and a statement that changes
// data does not fit the row-per-line shape. Use Command for those. The trailer and error
// rules are QueryStream's.
func (d *Database) CommandStream(ctx context.Context, lang QueryLanguage, command string, params map[string]any) iter.Seq2[StreamEvent, error] {
	return d.stream(func() (io.ReadCloser, error) {
		accept := generated.ExecuteCommandParamsAcceptApplicationxNdjson
		resp, err := d.srv.raw.ExecuteCommand(ctx, d.name,
			&generated.ExecuteCommandParams{ArcadedbSessionId: d.sessionParam(), Accept: &accept},
			buildCommandRequest(lang, command, params))
		return unpackStream(resp, err)
	})
}

// unpackStream returns the body of a 2xx response, or the *ArcadeDBError for any other.
func unpackStream(resp *http.Response, err error) (io.ReadCloser, error) {
	if err != nil {
		return nil, err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, errorFromResponse(resp)
	}
	return resp.Body, nil
}

func (d *Database) stream(open func() (io.ReadCloser, error)) iter.Seq2[StreamEvent, error] {
	return func(yield func(StreamEvent, error) bool) {
		body, err := open()
		if err != nil {
			yield(StreamEvent{}, err)
			return
		}
		defer body.Close()
		for line, err := range ndjson.Lines(body) {
			if err != nil {
				yield(StreamEvent{}, err)
				return
			}
			ev, ok, err := decodeStreamLine(line)
			if !ok && err == nil {
				continue
			}
			if !yield(ev, err) || err != nil {
				return
			}
		}
	}
}

type statsWire struct {
	Limit     *int `json:"limit"`
	Returned  int  `json:"returned"`
	Truncated bool `json:"truncated"`
}

type eventWire struct {
	Record map[string]any `json:"record"`
	Stats  *statsWire     `json:"stats"`
	Error  *struct {
		Message string `json:"message"`
	} `json:"error"`
}

// decodeStreamLine reports ok=false with a nil error for an event of an unknown kind.
func decodeStreamLine(line []byte) (StreamEvent, bool, error) {
	var w eventWire
	if err := json.Unmarshal(line, &w); err != nil {
		return StreamEvent{}, false, fmt.Errorf("arcadedb: decode stream event: %w", err)
	}
	switch {
	case w.Error != nil:
		msg := w.Error.Message
		if msg == "" {
			msg = defaultStreamError
		}
		return StreamEvent{}, true, &ArcadeDBError{Status: 200, ErrorMessage: msg}
	case w.Stats != nil:
		s := &StreamStats{Limit: -1, Returned: w.Stats.Returned, Truncated: w.Stats.Truncated}
		if w.Stats.Limit != nil {
			s.Limit = *w.Stats.Limit
		}
		return StreamEvent{Stats: s}, true, nil
	case w.Record != nil:
		return StreamEvent{Record: w.Record}, true, nil
	}
	return StreamEvent{}, false, nil
}
