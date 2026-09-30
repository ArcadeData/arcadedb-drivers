package arcadedb

import (
	"context"
	"encoding/base64"
	"errors"
	"net/http"
	"testing"
)

func TestBasicAuthHeader(t *testing.T) {
	for _, c := range [][2]string{{"root", "pw"}, {"ü", "pä"}} {
		var got string
		srv := newTestServer(t, func(w http.ResponseWriter, r *http.Request) {
			got = r.Header.Get("Authorization")
			writeJSON(w, `{}`)
		}, WithBasicAuth(c[0], c[1]))
		if _, err := srv.ListDatabases(context.Background()); err != nil {
			t.Fatal(err)
		}
		want := "Basic " + base64.StdEncoding.EncodeToString([]byte(c[0]+":"+c[1]))
		if got != want {
			t.Fatalf("got %q want %q", got, want)
		}
	}
}

func TestBearerAuthHeader(t *testing.T) {
	var got string
	srv := newTestServer(t, func(w http.ResponseWriter, r *http.Request) {
		got = r.Header.Get("Authorization")
		writeJSON(w, `{}`)
	}, WithBearerToken("tok"))
	if _, err := srv.ListDatabases(context.Background()); err != nil {
		t.Fatal(err)
	}
	if got != "Bearer tok" {
		t.Fatalf("got %q", got)
	}
}

func TestUserAgentCarriesVersionAndExtraHeaders(t *testing.T) {
	var ua, x string
	srv := newTestServer(t, func(w http.ResponseWriter, r *http.Request) {
		ua, x = r.Header.Get("User-Agent"), r.Header.Get("X-Extra")
		writeJSON(w, `{}`)
	}, WithHeader("X-Extra", "1"))
	if _, err := srv.ListDatabases(context.Background()); err != nil {
		t.Fatal(err)
	}
	if ua != "arcadedb-go/"+Version || x != "1" {
		t.Fatalf("ua=%q x=%q", ua, x)
	}
}

func TestListDatabasesEmptyWhenResultMissing(t *testing.T) {
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) { writeJSON(w, `{}`) })
	got, err := srv.ListDatabases(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if got == nil || len(got) != 0 {
		t.Fatalf("got %#v", got)
	}
}

func TestExists(t *testing.T) {
	for body, want := range map[string]bool{`{"result":true}`: true, `{}`: false} {
		srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) { writeJSON(w, body) })
		got, err := srv.Exists(context.Background(), "db")
		if err != nil || got != want {
			t.Fatalf("%s: got %v %v", body, got, err)
		}
	}
}

func TestHealthRequires204(t *testing.T) {
	status := 200
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(status) })
	var ae *ArcadeDBError
	if err := srv.Health(context.Background()); !errors.As(err, &ae) || ae.Status != 200 {
		t.Fatalf("got %v", err)
	}
	status = 204
	if err := srv.Health(context.Background()); err != nil {
		t.Fatal(err)
	}
}

func TestReady(t *testing.T) {
	status := 204
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(status) })
	ctx := context.Background()
	if ok, err := srv.Ready(ctx); !ok || err != nil {
		t.Fatalf("204: %v %v", ok, err)
	}
	status = 503
	if ok, err := srv.Ready(ctx); ok || err != nil {
		t.Fatalf("503: %v %v", ok, err)
	}
	status = 500
	var ae *ArcadeDBError
	if ok, err := srv.Ready(ctx); ok || !errors.As(err, &ae) {
		t.Fatalf("500: %v %v", ok, err)
	}
}

func TestServerInfo(t *testing.T) {
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) { writeJSON(w, `{"version":"1"}`) })
	info, err := srv.ServerInfo(context.Background())
	if err != nil || info == nil {
		t.Fatal(info, err)
	}
}

func TestRawDoesNotErrorOnNon2xx(t *testing.T) {
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(500) })
	resp, err := srv.Raw().GetServerInfoWithResponse(context.Background(), nil)
	if err != nil || resp.StatusCode() != 500 {
		t.Fatalf("%v %v", resp, err)
	}
}

func TestDatabaseNameIsEscapedAsOneSegment(t *testing.T) {
	var got string
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		got = r.URL.EscapedPath()
		writeJSON(w, `{"result":true}`)
	})
	if _, err := srv.Exists(context.Background(), "my db/x"); err != nil {
		t.Fatal(err)
	}
	if got != "/api/v1/exists/my%20db%2Fx" {
		t.Fatalf("got %q", got)
	}
}

func TestDBHandle(t *testing.T) {
	srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) {})
	db := srv.DB("x")
	if db.Name() != "x" || db.sessionParam() != nil {
		t.Fatal("bad handle")
	}
}
