package arcadedb

import (
	"context"
	"errors"
	"net/http"
	"reflect"
	"strings"
	"testing"
	"time"
)

const testHash = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

// authRecorder answers every request with status and body, recording each request's
// Authorization header and path.
type authRecorder struct {
	auths, paths []string
}

func (a *authRecorder) server(t *testing.T, status int, body string, opts ...Option) *Server {
	t.Helper()
	return newTestServer(t, func(w http.ResponseWriter, r *http.Request) {
		a.auths = append(a.auths, r.Header.Get("Authorization"))
		a.paths = append(a.paths, r.Method+" "+r.URL.Path)
		if body != "" {
			// The generated parser fails on an empty body typed as JSON before the facade sees it.
			w.Header().Set("Content-Type", "application/json")
		}
		w.WriteHeader(status)
		_, _ = w.Write([]byte(body))
	}, opts...)
}

func TestLoginUsesTheClientsCredentials(t *testing.T) {
	var a authRecorder
	srv := a.server(t, 200, `{"token":"AU-node-1","user":"root"}`, WithBasicAuth("root", "pw"))
	got, err := srv.Login(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if got != (LoginResult{Token: "AU-node-1", User: "root"}) {
		t.Fatalf("got %+v", got)
	}
	if a.paths[0] != "POST /api/v1/login" || a.auths[0] != basicAuthValue("root", "pw") {
		t.Fatalf("sent %s with %q", a.paths[0], a.auths[0])
	}
}

func TestLoginAsSendsTheGivenCredentialsAndLeavesTheClientAlone(t *testing.T) {
	var a authRecorder
	srv := a.server(t, 200, `{"token":"AU-node-2","user":"alice"}`, WithBasicAuth("root", "pw"))
	got, err := srv.LoginAs(context.Background(), "alice", "alice-pw")
	if err != nil {
		t.Fatal(err)
	}
	if got.Token != "AU-node-2" || got.User != "alice" {
		t.Fatalf("got %+v", got)
	}
	if a.auths[0] != basicAuthValue("alice", "alice-pw") {
		t.Fatalf("login sent %q", a.auths[0])
	}
	// The fake's body is not a database list; only the header this request carries matters.
	_, _ = srv.ListDatabases(context.Background())
	if a.auths[1] != basicAuthValue("root", "pw") {
		t.Fatalf("the client's own requests now send %q", a.auths[1])
	}
}

func TestLoginErrorsAreTyped(t *testing.T) {
	for _, c := range []struct {
		status int
		body   string
	}{
		{403, `{"error":"Security error"}`},
		{503, `{"error":"Server reached the maximum number of concurrent authentication sessions"}`},
	} {
		var a authRecorder
		srv := a.server(t, c.status, c.body, WithBasicAuth("root", "pw"))
		_, err := srv.LoginAs(context.Background(), "alice", "wrong")
		var ae *ArcadeDBError
		if !errors.As(err, &ae) || ae.Status != c.status {
			t.Fatalf("%d: got %v", c.status, err)
		}
	}
}

func TestLoginEmptyBodyIsErrEmptyBody(t *testing.T) {
	var a authRecorder
	srv := a.server(t, 200, ``, WithBasicAuth("root", "pw"))
	if _, err := srv.Login(context.Background()); !errors.Is(err, ErrEmptyBody) {
		t.Fatalf("got %v", err)
	}
}

func TestWithTokenDerivesABearerClientAndLeavesTheOriginal(t *testing.T) {
	var got []http.Header
	srv := newTestServer(t, func(w http.ResponseWriter, r *http.Request) {
		got = append(got, r.Header.Clone())
		writeJSON(w, `{"result":[]}`)
	}, WithBasicAuth("root", "pw"), WithHeader("X-Tenant", "a"))

	user := srv.WithToken("AU-node-3")
	if _, err := user.ListDatabases(context.Background()); err != nil {
		t.Fatal(err)
	}
	if _, err := srv.ListDatabases(context.Background()); err != nil {
		t.Fatal(err)
	}
	if got[0].Get("Authorization") != "Bearer AU-node-3" || got[0].Get("X-Tenant") != "a" {
		t.Fatalf("derived client sent %v", got[0])
	}
	if got[1].Get("Authorization") != basicAuthValue("root", "pw") {
		t.Fatalf("original client now sends %q", got[1].Get("Authorization"))
	}
}

func TestLogoutSendsTheSessionToken(t *testing.T) {
	var a authRecorder
	srv := a.server(t, 204, ``, WithBearerToken("AU-node-4"))
	if err := srv.Logout(context.Background()); err != nil {
		t.Fatal(err)
	}
	if a.paths[0] != "POST /api/v1/logout" || a.auths[0] != "Bearer AU-node-4" {
		t.Fatalf("sent %s with %q", a.paths[0], a.auths[0])
	}
}

func TestLogoutOfAnInvalidTokenIsTyped(t *testing.T) {
	var a authRecorder
	srv := a.server(t, 401, `{"error":"Invalid token"}`, WithBearerToken("AU-node-5"))
	var ae *ArcadeDBError
	if err := srv.Logout(context.Background()); !errors.As(err, &ae) || ae.Status != 401 {
		t.Fatalf("got %v", err)
	}
}

func TestLogoutWithoutASessionTokenSendsNothing(t *testing.T) {
	for name, opt := range map[string]Option{
		"basic":     WithBasicAuth("root", "pw"),
		"api token": WithBearerToken("at-0123"),
		"none":      WithHeader("X-Other", "1"),
	} {
		var a authRecorder
		srv := a.server(t, 204, ``, opt)
		if err := srv.Logout(context.Background()); !errors.Is(err, ErrNotSessionToken) {
			t.Fatalf("%s: got %v", name, err)
		}
		if len(a.paths) != 0 {
			t.Fatalf("%s: sent %v", name, a.paths)
		}
	}
}

func TestListSessionsMapsEveryField(t *testing.T) {
	var a authRecorder
	srv := a.server(t, 200, `{"count":2,"result":[
		{"token":"AU-n-1","user":"alice","createdAt":1000,"lastUpdate":2000,"elapsedMs":1500,
		 "sourceIp":"10.0.0.1","userAgent":"go","country":"IT","city":"Rome","issuer":"node-b"},
		{"token":"AU-n-2","user":"bob","createdAt":0,"lastUpdate":0,"elapsedMs":0,
		 "sourceIp":null,"userAgent":null,"country":null,"city":null}]}`, WithBasicAuth("root", "pw"))
	got, err := srv.ListSessions(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	want := []Session{
		{Token: "AU-n-1", User: "alice", Issuer: "node-b", CreatedAt: time.UnixMilli(1000), LastUpdate: time.UnixMilli(2000),
			Elapsed: 1500 * time.Millisecond, SourceIP: "10.0.0.1", UserAgent: "go", Country: "IT", City: "Rome"},
		{Token: "AU-n-2", User: "bob", CreatedAt: time.UnixMilli(0), LastUpdate: time.UnixMilli(0)},
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %+v", got)
	}
	if a.paths[0] != "GET /api/v1/sessions" {
		t.Fatalf("sent %s", a.paths[0])
	}
}

func TestListSessionsEmptyAndForbidden(t *testing.T) {
	var a authRecorder
	got, err := a.server(t, 200, ``, WithBasicAuth("root", "pw")).ListSessions(context.Background())
	if err != nil || got == nil || len(got) != 0 {
		t.Fatalf("got %v, %v", got, err)
	}
	_, err = a.server(t, 403, `{"error":"Security error"}`, WithBasicAuth("alice", "pw")).ListSessions(context.Background())
	wantArcadeDBError(t, err, 403, "Security error")
}

func TestCreateAPITokenSendsOnlyWhatIsSet(t *testing.T) {
	const created = `{"result":{"name":"ci","database":"*","createdAt":1000,"expiresAt":0,"permissions":{},
		"tokenHash":"` + testHash + `","tokenSuffix":"beef","token":"at-secret"}}`
	var rec recorded
	srv := recordingServer(t, 201, created, &rec)
	got, err := srv.CreateAPIToken(context.Background(), APITokenRequest{Name: "ci"})
	if err != nil {
		t.Fatal(err)
	}
	if rec.method != http.MethodPost || rec.path != "/api/v1/server/api-tokens" {
		t.Fatalf("sent %s %s", rec.method, rec.path)
	}
	if !reflect.DeepEqual(rec.body, map[string]any{"name": "ci"}) {
		t.Fatalf("body %v", rec.body)
	}
	want := CreatedAPIToken{
		APIToken: APIToken{Name: "ci", Database: "*", CreatedAt: time.UnixMilli(1000), Permissions: map[string]any{},
			TokenHash: testHash, TokenSuffix: "beef"},
		Token: "at-secret",
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %+v", got)
	}
}

func TestCreateAPITokenSendsEveryField(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 201, `{"result":{"name":"ci","database":"db","createdAt":1,"expiresAt":1700000000000,
		"permissions":{},"tokenHash":"`+testHash+`","tokenSuffix":"beef","token":"at-x"}}`, &rec)
	perms := map[string]any{"*": map[string]any{"access": []any{"readRecord"}}}
	got, err := srv.CreateAPIToken(context.Background(), APITokenRequest{
		Name: "ci", Database: "db", ExpiresAt: time.UnixMilli(1700000000000), Permissions: perms,
	})
	if err != nil {
		t.Fatal(err)
	}
	want := map[string]any{"name": "ci", "database": "db", "expiresAt": float64(1700000000000), "permissions": perms}
	if !reflect.DeepEqual(rec.body, want) {
		t.Fatalf("body %v", rec.body)
	}
	if !got.ExpiresAt.Equal(time.UnixMilli(1700000000000)) {
		t.Fatalf("expiresAt %v", got.ExpiresAt)
	}
}

func TestCreateAPITokenErrorsAreTyped(t *testing.T) {
	for _, status := range []int{400, 403, 409, 412} {
		var rec recorded
		srv := recordingServer(t, status, `{"error":"refused"}`, &rec)
		_, err := srv.CreateAPIToken(context.Background(), APITokenRequest{Name: "ci"})
		wantArcadeDBError(t, err, status, "refused")
	}
}

func TestListAPITokensMapsExpiryAndExpired(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 200, `{"count":2,"result":[
		{"name":"a","database":"*","createdAt":1,"expiresAt":0,"permissions":{},"tokenHash":"`+testHash+`","tokenSuffix":"0001"},
		{"name":"b","database":"db","createdAt":2,"expiresAt":3,"expired":true,"permissions":{"x":1},"tokenHash":"`+testHash+`","tokenSuffix":"0002"}]}`, &rec)
	got, err := srv.ListAPITokens(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if rec.method != http.MethodGet || rec.path != "/api/v1/server/api-tokens" {
		t.Fatalf("sent %s %s", rec.method, rec.path)
	}
	if len(got) != 2 || !got[0].ExpiresAt.IsZero() || got[0].Expired || !got[1].Expired ||
		!got[1].ExpiresAt.Equal(time.UnixMilli(3)) || got[1].Permissions["x"] != float64(1) {
		t.Fatalf("got %+v", got)
	}
}

func TestListAPITokensEmpty(t *testing.T) {
	var rec recorded
	got, err := recordingServer(t, 200, `{"count":0,"result":[]}`, &rec).ListAPITokens(context.Background())
	if err != nil || got == nil || len(got) != 0 {
		t.Fatalf("got %v, %v", got, err)
	}
}

func TestDeleteAPITokenSendsTheHash(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 200, `{"result":"Token deleted"}`, &rec)
	if err := srv.DeleteAPIToken(context.Background(), testHash); err != nil {
		t.Fatal(err)
	}
	if rec.method != http.MethodDelete || rec.path != "/api/v1/server/api-tokens" || rec.rawQuery != "token="+testHash {
		t.Fatalf("sent %s %s?%s", rec.method, rec.path, rec.rawQuery)
	}
}

func TestDeleteAPITokenOfAnUnknownHashIsTyped(t *testing.T) {
	var rec recorded
	err := recordingServer(t, 404, `{"error":"Token not found"}`, &rec).DeleteAPIToken(context.Background(), testHash)
	wantArcadeDBError(t, err, 404, "Token not found")
}

func TestDeleteAPITokenRefusesAnythingButAHashUnsent(t *testing.T) {
	for _, arg := range []string{
		"at-" + testHash[:61], // the plaintext token: the mistake this guards against
		strings.ToUpper(testHash),
		testHash[:63],
		testHash + "0",
		"",
	} {
		sent := false
		srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) { sent = true })
		err := srv.DeleteAPIToken(context.Background(), arg)
		if !errors.Is(err, ErrInvalidTokenHash) {
			t.Fatalf("%q: got %v", arg, err)
		}
		if sent {
			t.Fatalf("%q was sent", arg)
		}
		if arg != "" && strings.Contains(err.Error(), arg) {
			t.Fatalf("the error repeats the argument: %v", err)
		}
	}
}
