package arcadedb

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"net/http"
	"strconv"
	"strings"
	"time"
)

// ErrEmptyBody is returned when the server answered 2xx with an empty or null body where
// the method needs a JSON document to return: ServerInfo, the Vector, PromQL, TS and
// Grafana methods. Returning (nil, nil) instead would read as a successful empty answer.
// Match it with errors.Is. Methods for which an empty body has a meaning (ListDatabases,
// Exists) never return it.
var ErrEmptyBody = errors.New("arcadedb: response had an empty body")

// requestIDHeader is set by the server on every response, generating a value when the
// client sent none, so it is a usable correlation id unconditionally.
const requestIDHeader = "X-Request-Id"

// retryAfterHeader and commitIndexHeader are read off every non-2xx response into
// ArcadeDBError.RetryAfter and ArcadeDBError.CommitIndex.
const (
	retryAfterHeader  = "Retry-After"
	commitIndexHeader = "X-ArcadeDB-Commit-Index"
)

// ArcadeDBError is returned by every facade method when the server answers with a
// non-2xx status, except Server.Ready, which reads a 503 as (false, nil). Callers match it
// with errors.As.
//
// It carries the HTTP status plus whatever the server's JSON error body contributed.
// Every field beyond Status may be empty, because the body may be absent, unparsable,
// or missing individual fields; parsing an error never itself fails.
//
// This asymmetry is deliberate: Raw() never returns an error for a non-2xx status,
// while every facade method does, as *ArcadeDBError.
//
// Two names differ from the wire. ErrorMessage holds the body's "error" string: Go
// forbids a field and a method with the same name, and Error() is what makes this
// type an error. Help is spelled without the underscore Python uses (help_): that
// avoids shadowing a builtin, which Go has no equivalent of, so do not port it.
//
// ExceptionArgs is a plain string despite its plural name; the contract types it
// that way and it is passed through as-is, not parsed or coerced.
//
// RetryAfter is how long the server asked the caller to wait before retrying: the
// Retry-After response header of a non-2xx response, or the retryAfter field of an in-band
// stream or batch error, where a header can no longer be added. Only a non-negative whole
// number of seconds is read; an HTTP-date, a negative or malformed value, and an absent one
// all leave it 0, so 0 means "absent or no wait", never "retry now is safe". The server sends
// it on a 503 when the node cannot execute the request yet (a snapshot install, for one) and
// on a 409 when an identical request is still in flight.
//
// CommitIndex is the last applied Raft index the server reported: the
// X-ArcadeDB-Commit-Index response header of a non-2xx response, or the commitIndex field of
// an in-band batch error (the in-band query and command stream error carries none). It is 0
// when absent, which is always the case on a standalone (non-replicated) database; the
// server never sends 0, it omits the header instead. It stays a valid read-after barrier
// on an error: a failed batch load's index bookmarks the chunks committed before the
// failure, and sending it back as the X-ArcadeDB-Read-After request header makes a later
// read see them.
//
// 409 has two meanings, and neither this client nor any of its siblings retries on it. An
// identical request still in flight is retryable after RetryAfter, and carries
// Exception "...RequestStillInFlightException" with a Retry-After. A query terminated by
// `terminate query`, `terminate queries` or `terminate transaction` had its writes rolled
// back and must not be retried. Retry logic must tell them apart by Exception or
// RetryAfter, never by Status alone.
type ArcadeDBError struct {
	Status        int
	ErrorMessage  string
	Exception     string
	Detail        string
	RequestID     string
	Help          string
	ExceptionArgs string
	RetryAfter    time.Duration
	CommitIndex   int64
}

// TimeSeriesWriteError is the error TimeSeries.Write returns when the server answers 400
// with a JSON object body, the contract's TimeSeriesWriteError: some or all samples were
// dropped. It embeds the *ArcadeDBError built from the same response the usual way (Status,
// ErrorMessage, RequestID, RetryAfter, CommitIndex, ...), so errors.As matches both
// *TimeSeriesWriteError and *ArcadeDBError, and Error() is ArcadeDBError's.
//
// A write is NOT atomic: Written samples landed even though the call failed, and retrying
// the whole payload writes them twice. Written and Dropped are 0 when the body omits them.
//
// The four lists say why samples were dropped, each nil when absent (elements that are not
// strings are dropped): UnknownTypes names measurements whose type does not exist,
// NonTimeSeriesTypes ones whose type exists but is not a time-series type,
// UnavailableTypes time-series types whose storage engine failed to load (the server log
// says why), and UndeclaredKeys tag or field keys the measurement's type does not declare
// in that role. UndeclaredKeys is capped at 100 entries by the server; setting
// arcadedb.timeSeriesUndeclaredKeys=ignore on the server stores such samples with the
// undeclared keys discarded instead of dropping them.
//
// Any other failure of Write, a 400 whose body is not a JSON object included, is a plain
// *ArcadeDBError.
type TimeSeriesWriteError struct {
	*ArcadeDBError
	Written            int64
	Dropped            int64
	UnknownTypes       []string
	NonTimeSeriesTypes []string
	UnavailableTypes   []string
	UndeclaredKeys     []string
}

// Unwrap returns the embedded *ArcadeDBError, which is what lets errors.As find it.
func (e *TimeSeriesWriteError) Unwrap() error { return e.ArcadeDBError }

// Error returns ErrorMessage, else Detail, else a generic message naming the status.
func (e *ArcadeDBError) Error() string {
	switch {
	case e.ErrorMessage != "":
		return e.ErrorMessage
	case e.Detail != "":
		return e.Detail
	}
	return fmt.Sprintf("ArcadeDB request failed with status %d", e.Status)
}

// newError never fails. A body that is not a JSON object yields an error carrying only
// Status and RequestID; a field that is not a string is left empty. RequestID falls back
// to the body's requestId when the header is empty.
func newError(status int, body []byte, requestID string) *ArcadeDBError {
	var parsed map[string]any
	if json.Unmarshal(body, &parsed) != nil {
		parsed = nil
	}
	str := func(key string) string {
		s, _ := parsed[key].(string)
		return s
	}
	if requestID == "" {
		requestID = str("requestId")
	}
	return &ArcadeDBError{
		Status:        status,
		ErrorMessage:  str("error"),
		Exception:     str("exception"),
		Detail:        str("detail"),
		RequestID:     requestID,
		Help:          str("help"),
		ExceptionArgs: str("exceptionArgs"),
	}
}

// errorFromHeaders is newError plus what the response headers contribute: RequestID from
// X-Request-Id, RetryAfter and CommitIndex. Every non-2xx response goes through it.
func errorFromHeaders(status int, body []byte, h http.Header) *ArcadeDBError {
	e := newError(status, body, h.Get(requestIDHeader))
	if n, ok := parseNonNegative(h.Get(retryAfterHeader)); ok {
		e.RetryAfter = secondsDuration(n)
	}
	if n, ok := parseNonNegative(h.Get(commitIndexHeader)); ok {
		e.CommitIndex = n
	}
	return e
}

// parseNonNegative reads s, trimmed, as a non-negative base-10 integer of digits only (no
// sign). Anything else, an HTTP-date Retry-After included, reports false; it never fails.
func parseNonNegative(s string) (int64, bool) {
	s = strings.TrimSpace(s)
	if s == "" || strings.TrimLeft(s, "0123456789") != "" {
		return 0, false
	}
	n, err := strconv.ParseInt(s, 10, 64)
	if err != nil {
		return 0, false
	}
	return n, true
}

// jsonNonNegative reads an in-band JSON number as a non-negative whole number.
func jsonNonNegative(v any) (int64, bool) {
	f, ok := v.(float64)
	if !ok || f < 0 || f != math.Trunc(f) || f > math.MaxInt64 {
		return 0, false
	}
	return int64(f), true
}

// secondsDuration converts seconds to a Duration, saturating rather than overflowing.
func secondsDuration(n int64) time.Duration {
	if n > int64(math.MaxInt64/time.Second) {
		return time.Duration(math.MaxInt64)
	}
	return time.Duration(n) * time.Second
}

// isSuccess reports whether status is 2xx: the one definition of success every facade
// method shares, buffered (checkResponse) and streamed (streams, BatchLoad) alike.
func isSuccess(status int) bool { return status >= 200 && status < 300 }

// errorFromResponse reads and closes resp.Body. A read failure is treated as an empty
// body: the status is still worth reporting.
func errorFromResponse(resp *http.Response) *ArcadeDBError {
	var body []byte
	if resp.Body != nil {
		body, _ = io.ReadAll(resp.Body)
		_ = resp.Body.Close()
	}
	return errorFromHeaders(resp.StatusCode, body, resp.Header)
}

// checkResponse returns nil for any 2xx status, otherwise an *ArcadeDBError built from
// body. It returns a plain nil error on success, never a typed-nil *ArcadeDBError.
func checkResponse(resp *http.Response, body []byte) error {
	if isSuccess(resp.StatusCode) {
		return nil
	}
	return errorFromHeaders(resp.StatusCode, body, resp.Header)
}

// decodeBody returns typed when the generated parser filled it. The parser only does so
// for an exact 200 whose Content-Type contains "json", so a JSON body behind a proxy that
// rewrites the type, or a 203, would otherwise be lost. It then decodes body itself. An
// empty body yields (nil, nil); callers decide what "unset" means.
func decodeBody[T any](typed *T, body []byte) (*T, error) {
	if typed != nil {
		return typed, nil
	}
	if trimmed := bytes.TrimSpace(body); len(trimmed) == 0 || string(trimmed) == "null" {
		return nil, nil
	}
	out := new(T)
	if err := json.Unmarshal(body, out); err != nil {
		return nil, fmt.Errorf("arcadedb: decode response: %w", err)
	}
	return out, nil
}

// nonEmpty turns a nil decoded body into ErrEmptyBody: a call that succeeded with no body
// has no answer to give, and (nil, nil) would read as an empty one.
func nonEmpty[T any](r *T, err error) (*T, error) {
	if err != nil {
		return nil, err
	}
	if r == nil {
		return nil, ErrEmptyBody
	}
	return r, nil
}

// readChecked reads and closes resp.Body and returns it, or the *ArcadeDBError for a
// non-2xx status. It is for the plain (non-WithResponse) client methods, whose body the
// caller still has to read.
func readChecked(resp *http.Response) ([]byte, error) {
	var body []byte
	if resp.Body != nil {
		body, _ = io.ReadAll(resp.Body)
		_ = resp.Body.Close()
	}
	if err := checkResponse(resp, body); err != nil {
		return nil, err
	}
	return body, nil
}

// decodeMap turns a plain-client response into the JSON object it carries. An empty or
// null 2xx body is ErrEmptyBody, never (nil, nil): the caller expected an object.
func decodeMap(resp *http.Response, err error) (map[string]any, error) {
	if err != nil {
		return nil, err
	}
	body, err := readChecked(resp)
	if err != nil {
		return nil, err
	}
	m, err := nonEmpty(decodeBody[map[string]any](nil, body))
	if err != nil {
		return nil, err
	}
	return *m, nil
}
