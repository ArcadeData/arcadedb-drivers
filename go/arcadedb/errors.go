package arcadedb

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
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

// ArcadeDBError is returned by every facade method when the server answers with a
// non-2xx status. Callers match it with errors.As.
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
type ArcadeDBError struct {
	Status        int
	ErrorMessage  string
	Exception     string
	Detail        string
	RequestID     string
	Help          string
	ExceptionArgs string
}

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
	return newError(resp.StatusCode, body, resp.Header.Get(requestIDHeader))
}

// checkResponse returns nil for any 2xx status, otherwise an *ArcadeDBError built from
// body. It returns a plain nil error on success, never a typed-nil *ArcadeDBError.
func checkResponse(resp *http.Response, body []byte) error {
	if isSuccess(resp.StatusCode) {
		return nil
	}
	return newError(resp.StatusCode, body, resp.Header.Get(requestIDHeader))
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
