package arcadedb

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

// fakeServer starts an httptest server running h and returns a Server pointed at it,
// authenticated as root/pw. The server is closed when the test ends.
func fakeServer(t *testing.T, h http.HandlerFunc) *Server {
	t.Helper()
	ts := httptest.NewServer(h)
	t.Cleanup(ts.Close)
	srv, err := NewServer(ts.URL, WithBasicAuth("root", "pw"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = srv.Close() })
	return srv
}

// newTestServer is fakeServer with caller-chosen options instead of the default auth.
func newTestServer(t *testing.T, h http.HandlerFunc, opts ...Option) *Server {
	t.Helper()
	ts := httptest.NewServer(h)
	t.Cleanup(ts.Close)
	srv, err := NewServer(ts.URL, opts...)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = srv.Close() })
	return srv
}

func writeJSON(w http.ResponseWriter, body string) {
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(body))
}
