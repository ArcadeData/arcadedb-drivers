package arcadedb

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"reflect"
	"testing"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

// recorded is what the fake server saw of the one request a test sends.
type recorded struct {
	method, path, rawQuery string
	body                   map[string]any
}

// recordingServer answers every request with status and body, recording the request into rec.
func recordingServer(t *testing.T, status int, body string, rec *recorded) *Server {
	t.Helper()
	return fakeServer(t, func(w http.ResponseWriter, r *http.Request) {
		rec.method, rec.path, rec.rawQuery = r.Method, r.URL.Path, r.URL.RawQuery
		raw, _ := io.ReadAll(r.Body)
		rec.body = nil
		if len(raw) > 0 {
			if err := json.Unmarshal(raw, &rec.body); err != nil {
				t.Errorf("request body is not a JSON object: %s", raw)
			}
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_, _ = w.Write([]byte(body))
	})
}

func wantArcadeDBError(t *testing.T, err error, status int, msg string) {
	t.Helper()
	var ae *ArcadeDBError
	if !errors.As(err, &ae) {
		t.Fatalf("got %v (%T), want *ArcadeDBError", err, err)
	}
	if ae.Status != status || ae.ErrorMessage != msg {
		t.Fatalf("got status %d message %q, want %d %q", ae.Status, ae.ErrorMessage, status, msg)
	}
}

func TestSQLScriptLanguageReachesTheWire(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 200, `{"result":[]}`, &rec)
	if _, err := srv.DB("db").Command(context.Background(), SQLScript, "LET a = 1; RETURN $a", nil); err != nil {
		t.Fatal(err)
	}
	if rec.body["language"] != "sqlscript" {
		t.Fatalf("language %v", rec.body["language"])
	}
}

func TestCreateAndDropDatabaseSendServerCommands(t *testing.T) {
	for _, c := range []struct {
		call func(*Server) error
		want string
	}{
		{func(s *Server) error { return s.CreateDatabase(context.Background(), "tenant_a") }, "create database tenant_a"},
		{func(s *Server) error { return s.DropDatabase(context.Background(), "tenant_a") }, "drop database tenant_a"},
	} {
		var rec recorded
		// The server's real answer: a string result where the contract declares an array.
		srv := recordingServer(t, 200, `{"result":"ok"}`, &rec)
		if err := c.call(srv); err != nil {
			t.Fatalf("%s: %v", c.want, err)
		}
		if rec.method != http.MethodPost || rec.path != "/api/v1/server" {
			t.Fatalf("%s: sent %s %s", c.want, rec.method, rec.path)
		}
		if rec.body["command"] != c.want || rec.body["language"] != "sql" {
			t.Fatalf("%s: body %v", c.want, rec.body)
		}
	}
}

func TestCreateAndDropDatabaseFailAsArcadeDBError(t *testing.T) {
	for _, call := range []func(*Server) error{
		func(s *Server) error { return s.CreateDatabase(context.Background(), "db") },
		func(s *Server) error { return s.DropDatabase(context.Background(), "db") },
	} {
		var rec recorded
		srv := recordingServer(t, 400, `{"error":"Database 'db' already exists"}`, &rec)
		wantArcadeDBError(t, call(srv), 400, "Database 'db' already exists")
	}
}

func TestDatabaseNameRefusedBeforeAnyRequest(t *testing.T) {
	for _, name := range []string{"", " ", " db", "db ", "\tdb", "db\n"} {
		sent := false
		srv := fakeServer(t, func(w http.ResponseWriter, r *http.Request) { sent = true; writeJSON(w, `{"result":"ok"}`) })
		for _, err := range []error{
			srv.CreateDatabase(context.Background(), name),
			srv.DropDatabase(context.Background(), name),
		} {
			if !errors.Is(err, ErrInvalidName) {
				t.Fatalf("%q: got %v, want ErrInvalidName", name, err)
			}
		}
		if sent {
			t.Fatalf("%q: a request was sent", name)
		}
	}
}

func TestServerCommandReturnsTheWholeBody(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 200, `{"result":["a","b"]}`, &rec)
	got, err := srv.ServerCommand(context.Background(), "list databases")
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(got, map[string]any{"result": []any{"a", "b"}}) {
		t.Fatalf("got %#v", got)
	}
	if rec.body["command"] != "list databases" || rec.body["language"] != "sql" {
		t.Fatalf("body %v", rec.body)
	}
}

func TestServerCommandFailsAsArcadeDBError(t *testing.T) {
	for _, c := range []struct {
		status int
		msg    string
	}{{400, "Server command not valid"}, {403, "Security error"}, {503, "Cluster unavailable"}} {
		var rec recorded
		srv := recordingServer(t, c.status, `{"error":"`+c.msg+`"}`, &rec)
		_, err := srv.ServerCommand(context.Background(), "whatever")
		wantArcadeDBError(t, err, c.status, c.msg)
	}
}

func TestServerCommandEmptyBodyIsErrEmptyBody(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 200, ``, &rec)
	if _, err := srv.ServerCommand(context.Background(), "shutdown"); !errors.Is(err, ErrEmptyBody) {
		t.Fatalf("got %v", err)
	}
}

func TestCreateUser(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 201, `{"result":"User 'alice' created"}`, &rec)
	err := srv.CreateUser(context.Background(), "alice", "secret-pw", map[string][]string{"tenant_a": {"admin"}})
	if err != nil {
		t.Fatal(err)
	}
	if rec.method != http.MethodPost || rec.path != "/api/v1/server/users" {
		t.Fatalf("sent %s %s", rec.method, rec.path)
	}
	want := map[string]any{"name": "alice", "password": "secret-pw", "databases": map[string]any{"tenant_a": []any{"admin"}}}
	if !reflect.DeepEqual(rec.body, want) {
		t.Fatalf("body %#v", rec.body)
	}
}

func TestCreateUserNilDatabasesOmitted(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 201, `{"result":"User 'bob' created"}`, &rec)
	if err := srv.CreateUser(context.Background(), "bob", "secret-pw", nil); err != nil {
		t.Fatal(err)
	}
	if _, ok := rec.body["databases"]; ok {
		t.Fatalf("body %v", rec.body)
	}
}

func TestCreateUserFailsAsArcadeDBError(t *testing.T) {
	for _, c := range []struct {
		status int
		msg    string
	}{{400, "User password must be at least 8 characters"}, {403, "Security error"}, {409, "User 'alice' already exists"}} {
		var rec recorded
		srv := recordingServer(t, c.status, `{"error":"`+c.msg+`"}`, &rec)
		wantArcadeDBError(t, srv.CreateUser(context.Background(), "alice", "pw", nil), c.status, c.msg)
	}
}

func TestUpdateUser(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 200, `{"result":"User 'alice' updated"}`, &rec)
	if err := srv.UpdateUser(context.Background(), "alice", UserUpdate{Password: "new-secret"}); err != nil {
		t.Fatal(err)
	}
	if rec.method != http.MethodPut || rec.path != "/api/v1/server/users" || rec.rawQuery != "name=alice" {
		t.Fatalf("sent %s %s?%s", rec.method, rec.path, rec.rawQuery)
	}
	if !reflect.DeepEqual(rec.body, map[string]any{"password": "new-secret"}) {
		t.Fatalf("body %#v", rec.body)
	}
}

func TestUpdateUserEmptyDatabasesIsSentToClearThem(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 200, `{"result":"ok"}`, &rec)
	if err := srv.UpdateUser(context.Background(), "alice", UserUpdate{Databases: map[string][]string{}}); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(rec.body, map[string]any{"databases": map[string]any{}}) {
		t.Fatalf("body %#v", rec.body)
	}
}

func TestUpdateUserNotFound(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 404, `{"error":"User 'ghost' not found"}`, &rec)
	wantArcadeDBError(t, srv.UpdateUser(context.Background(), "ghost", UserUpdate{}), 404, "User 'ghost' not found")
}

func TestDropUser(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 200, `{"result":"User 'a b' deleted"}`, &rec)
	if err := srv.DropUser(context.Background(), "a b"); err != nil {
		t.Fatal(err)
	}
	if rec.method != http.MethodDelete || rec.path != "/api/v1/server/users" || rec.rawQuery != "name=a+b" {
		t.Fatalf("sent %s %s?%s", rec.method, rec.path, rec.rawQuery)
	}
}

func TestDropUserNotFound(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 404, `{"error":"User 'ghost' not found"}`, &rec)
	wantArcadeDBError(t, srv.DropUser(context.Background(), "ghost"), 404, "User 'ghost' not found")
}

func TestListUsers(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 200, `{"result":[{"name":"root","databases":{"*":["admin"]}},{"name":"alice","databases":{}}]}`, &rec)
	got, err := srv.ListUsers(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	want := []User{{Name: "root", Databases: map[string][]string{"*": {"admin"}}}, {Name: "alice", Databases: map[string][]string{}}}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %#v", got)
	}
	if rec.method != http.MethodGet || rec.path != "/api/v1/server/users" {
		t.Fatalf("sent %s %s", rec.method, rec.path)
	}
}

func TestListUsersEmptyWhenResultMissing(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 200, `{}`, &rec)
	got, err := srv.ListUsers(context.Background())
	if err != nil || got == nil || len(got) != 0 {
		t.Fatalf("got %#v %v", got, err)
	}
}

func TestListUsersFailsAsArcadeDBError(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 403, `{"error":"Security error"}`, &rec)
	_, err := srv.ListUsers(context.Background())
	wantArcadeDBError(t, err, 403, "Security error")
}

func TestListGroups(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 200, `{"result":{"version":1,"databases":{"*":{"groups":{"admin":{"access":["updateSecurity"],"readTimeout":-1,"resultSetLimit":-1,"types":{}}}}}}}`, &rec)
	got, err := srv.ListGroups(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	g, ok := got["*"]["admin"]
	if !ok || !reflect.DeepEqual(g.Access, []string{"updateSecurity"}) || g.ReadTimeout != -1 {
		t.Fatalf("got %#v", got)
	}
	if rec.method != http.MethodGet || rec.path != "/api/v1/server/groups" {
		t.Fatalf("sent %s %s", rec.method, rec.path)
	}
}

func TestListGroupsEmptyWhenResultMissing(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 200, `{}`, &rec)
	got, err := srv.ListGroups(context.Background())
	if err != nil || got == nil || len(got) != 0 {
		t.Fatalf("got %#v %v", got, err)
	}
}

func TestSaveGroup(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 200, `{"result":"Group 'reader' saved"}`, &rec)
	limit := 100
	err := srv.SaveGroup(context.Background(), generated.SaveGroupRequest{Database: "tenant_a", Name: "reader", ResultSetLimit: &limit})
	if err != nil {
		t.Fatal(err)
	}
	if rec.method != http.MethodPost || rec.path != "/api/v1/server/groups" {
		t.Fatalf("sent %s %s", rec.method, rec.path)
	}
	if !reflect.DeepEqual(rec.body, map[string]any{"database": "tenant_a", "name": "reader", "resultSetLimit": float64(100)}) {
		t.Fatalf("body %#v", rec.body)
	}
}

func TestDeleteGroup(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 200, `{"result":"Group 'reader' deleted"}`, &rec)
	if err := srv.DeleteGroup(context.Background(), "tenant_a", "reader"); err != nil {
		t.Fatal(err)
	}
	if rec.method != http.MethodDelete || rec.path != "/api/v1/server/groups" || rec.rawQuery != "database=tenant_a&name=reader" {
		t.Fatalf("sent %s %s?%s", rec.method, rec.path, rec.rawQuery)
	}
}

func TestGroupCallsFailAsArcadeDBError(t *testing.T) {
	var rec recorded
	srv := recordingServer(t, 404, `{"error":"Group 'x' not found"}`, &rec)
	wantArcadeDBError(t, srv.DeleteGroup(context.Background(), "db", "x"), 404, "Group 'x' not found")
	wantArcadeDBError(t, srv.SaveGroup(context.Background(), generated.SaveGroupRequest{Database: "db", Name: "x"}), 404, "Group 'x' not found")
	_, err := srv.ListGroups(context.Background())
	wantArcadeDBError(t, err, 404, "Group 'x' not found")
}
