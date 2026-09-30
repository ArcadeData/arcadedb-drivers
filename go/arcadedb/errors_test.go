package arcadedb

import (
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"testing"
)

const fullBody = `{"error":"e","exception":"x","detail":"d","help":"h","exceptionArgs":"a","requestId":"b"}`

func TestErrorFieldsFromBody(t *testing.T) {
	e := newError(500, []byte(fullBody), "r")
	want := ArcadeDBError{Status: 500, ErrorMessage: "e", Exception: "x", Detail: "d", RequestID: "r", Help: "h", ExceptionArgs: "a"}
	if *e != want {
		t.Fatalf("got %+v, want %+v", *e, want)
	}
	if e.Error() != "e" {
		t.Fatalf("Error() = %q", e.Error())
	}
}

func TestErrorRequestIDFallsBackToBody(t *testing.T) {
	if got := newError(500, []byte(fullBody), "").RequestID; got != "b" {
		t.Fatalf("RequestID = %q", got)
	}
}

func TestErrorMessageFallbacks(t *testing.T) {
	if got := newError(400, []byte(`{"detail":"d"}`), "").Error(); got != "d" {
		t.Fatalf("got %q", got)
	}
	if got := newError(503, []byte(`{}`), "").Error(); got != "ArcadeDB request failed with status 503" {
		t.Fatalf("got %q", got)
	}
}

func TestErrorNonStringFieldIgnored(t *testing.T) {
	if got := newError(400, []byte(`{"error":42}`), "").ErrorMessage; got != "" {
		t.Fatalf("ErrorMessage = %q", got)
	}
}

func TestErrorFromHTMLBody(t *testing.T) {
	e := newError(502, []byte("<html>502</html>"), "r")
	if *e != (ArcadeDBError{Status: 502, RequestID: "r"}) {
		t.Fatalf("got %+v", *e)
	}
}

func TestErrorFromNonObjectBody(t *testing.T) {
	for _, b := range []string{`[1]`, `"s"`, `null`, `42`} {
		if e := newError(500, []byte(b), ""); *e != (ArcadeDBError{Status: 500}) {
			t.Fatalf("%s: got %+v", b, *e)
		}
	}
}

func TestErrorFromEmptyBody(t *testing.T) {
	for _, b := range [][]byte{nil, {}} {
		if e := newError(500, b, ""); *e != (ArcadeDBError{Status: 500}) {
			t.Fatalf("got %+v", *e)
		}
	}
}

func TestErrorsAsFindsArcadeDBError(t *testing.T) {
	var err error = newError(404, nil, "")
	wrapped := fmt.Errorf("wrap: %w", err)
	var got *ArcadeDBError
	if !errors.As(wrapped, &got) || got.Status != 404 {
		t.Fatalf("errors.As failed: %v", got)
	}
}

func TestErrorFromResponse(t *testing.T) {
	resp := &http.Response{
		StatusCode: 409,
		Header:     http.Header{"X-Request-Id": {"r"}},
		Body:       io.NopCloser(strings.NewReader(fullBody)),
	}
	e := errorFromResponse(resp)
	if e.Status != 409 || e.RequestID != "r" || e.ErrorMessage != "e" {
		t.Fatalf("got %+v", *e)
	}
}

func TestCheckResponse(t *testing.T) {
	for _, s := range []int{200, 201, 204, 299} {
		if err := checkResponse(&http.Response{StatusCode: s}, nil); err != nil {
			t.Fatalf("%d: got %v", s, err)
		}
	}
	err := checkResponse(&http.Response{StatusCode: 404, Header: http.Header{"X-Request-Id": {"r"}}}, []byte(`{"error":"nope"}`))
	var ae *ArcadeDBError
	if !errors.As(err, &ae) || ae.Status != 404 || ae.RequestID != "r" || ae.ErrorMessage != "nope" {
		t.Fatalf("got %v", err)
	}
}
