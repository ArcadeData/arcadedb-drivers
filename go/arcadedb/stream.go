package arcadedb

import (
	"context"
	"encoding/json"
	"fmt"
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
// route, including the consumer breaking out. Every range over the returned iterator
// issues the request again, so treat it as single-use: ranging twice runs the statement
// twice and may see different rows.
//
// The stats trailer is last in a complete stream, so a stream that ends without a Stats
// event was cut short (a server write timeout, a dropped connection) and the rows seen
// may be a partial answer. An in-band error, sent after the 200 status line, is yielded
// once as an *ArcadeDBError, and iteration then stops; so does a transport or decode
// error. That error's Status is the status the event itself reports, the one the
// buffered call would have answered with (503 for a retryable conflict, 409 for a
// duplicated key, 413 for a result cut short, ...), and is 200 only when the event carries
// none; ErrorMessage, Exception, Detail, ExceptionArgs and RetryAfter come from the event,
// and RequestID from the response's X-Request-Id, else the event's requestId (see
// streamError). Before contract 26.11.1 the status was always 200, so code that keyed on
// 200 to recognise an in-band failure must key on the iteration's error instead. Events of an unknown kind are ignored, so a newer server can
// add kinds without breaking this client. A non-2xx status is an *ArcadeDBError.
func (d *Database) QueryStream(ctx context.Context, lang QueryLanguage, command string, params map[string]any, opts ...QueryOption) iter.Seq2[StreamEvent, error] {
	o := queryCallOptions(opts)
	return d.stream(func() (*http.Response, error) {
		accept := generated.ExecuteQueryPostParamsAcceptApplicationxNdjson
		return d.srv.raw.ExecuteQueryPost(ctx, d.name,
			&generated.ExecuteQueryPostParams{ArcadedbSessionId: d.sessionParam(), Accept: &accept, XArcadeDBQueryTag: queryTagParam(o.queryTag)},
			buildQueryRequest(lang, command, params, o))
	})
}

// CommandStream is QueryStream for /command. It accepts read-only statements only: the
// server streams rows for a statement that produces them, and a statement that changes
// data does not fit the row-per-line shape. Use Command for those. The trailer and error
// rules are QueryStream's. opts takes WithLimit and WithQueryTag.
func (d *Database) CommandStream(ctx context.Context, lang QueryLanguage, command string, params map[string]any, opts ...CommandOption) iter.Seq2[StreamEvent, error] {
	o := commandCallOptions(opts)
	return d.stream(func() (*http.Response, error) {
		accept := generated.ExecuteCommandParamsAcceptApplicationxNdjson
		return d.srv.raw.ExecuteCommand(ctx, d.name,
			&generated.ExecuteCommandParams{ArcadedbSessionId: d.sessionParam(), Accept: &accept, XArcadeDBQueryTag: queryTagParam(o.queryTag)},
			buildCommandRequest(lang, command, params, o))
	})
}

// unpackStream returns a 2xx response, or the *ArcadeDBError for any other.
func unpackStream(resp *http.Response, err error) (*http.Response, error) {
	if err != nil {
		return nil, err
	}
	if !isSuccess(resp.StatusCode) {
		return nil, errorFromResponse(resp)
	}
	return resp, nil
}

func (d *Database) stream(open func() (*http.Response, error)) iter.Seq2[StreamEvent, error] {
	return func(yield func(StreamEvent, error) bool) {
		resp, err := unpackStream(open())
		if err != nil {
			yield(StreamEvent{}, err)
			return
		}
		defer resp.Body.Close()
		requestID := resp.Header.Get(requestIDHeader)
		for line, err := range ndjson.Lines(resp.Body) {
			if err != nil {
				yield(StreamEvent{}, err)
				return
			}
			ev, ok, err := decodeStreamLine(line, requestID)
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
	Error  map[string]any `json:"error"`
}

// decodeStreamLine reports ok=false with a nil error for an event of an unknown kind.
func decodeStreamLine(line []byte, requestID string) (StreamEvent, bool, error) {
	var w eventWire
	if err := json.Unmarshal(line, &w); err != nil {
		return StreamEvent{}, false, fmt.Errorf("arcadedb: decode stream event: %w", err)
	}
	switch {
	case w.Error != nil:
		return StreamEvent{}, true, streamError(w.Error, requestID)
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

// streamError maps an in-band {"error":{...}} event onto an *ArcadeDBError, field by field.
//
// Status is the event's own status, the one the buffered encoding would have answered the
// same failure with; only an event that carries none (or 0) reads as 200, the status line
// actually on the wire. ErrorMessage is the classified label in "error", the value the
// buffered body carries there, falling back to the raw "message" and then to a fixed
// text. RequestID prefers requestID, the response's X-Request-Id, over the event's own
// requestId. RetryAfter comes from the event's retryAfter, in seconds: the header the
// buffered encoding would send cannot be added once the stream has started. The event
// carries no commit index. A field of the wrong JSON type is left empty.
func streamError(fields map[string]any, requestID string) *ArcadeDBError {
	str := func(key string) string {
		s, _ := fields[key].(string)
		return s
	}
	e := &ArcadeDBError{
		Status:        inBandStatus(fields["status"], http.StatusOK),
		ErrorMessage:  str("error"),
		Exception:     str("exception"),
		Detail:        str("detail"),
		ExceptionArgs: str("exceptionArgs"),
		RequestID:     requestID,
	}
	if e.ErrorMessage == "" {
		e.ErrorMessage = str("message")
	}
	if e.ErrorMessage == "" {
		e.ErrorMessage = defaultStreamError
	}
	if e.RequestID == "" {
		e.RequestID = str("requestId")
	}
	if n, ok := jsonNonNegative(fields["retryAfter"]); ok {
		e.RetryAfter = secondsDuration(n)
	}
	return e
}
