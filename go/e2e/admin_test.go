package e2e

import (
	"context"
	"errors"
	"fmt"
	"slices"
	"strings"
	"testing"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb"
	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

func asArcadeDBError(t *testing.T, err error) *arcadedb.ArcadeDBError {
	t.Helper()
	var ae *arcadedb.ArcadeDBError
	if !errors.As(err, &ae) {
		t.Fatalf("got %v (%T), want *ArcadeDBError", err, err)
	}
	return ae
}

func TestCreateAndDropDatabase(t *testing.T) {
	ctx := context.Background()
	srv := newServer(t)
	name := fmt.Sprintf("e2eadmin%d", dbCounter.Add(1))

	if err := srv.CreateDatabase(ctx, name); err != nil {
		t.Fatal(err)
	}
	if ok, err := srv.Exists(ctx, name); err != nil || !ok {
		t.Fatalf("exists after create: %v %v", ok, err)
	}

	// An existing name is a 400, not a 409: CreateDatabase's doc comment and the README
	// rely on this.
	ae := asArcadeDBError(t, srv.CreateDatabase(ctx, name))
	if ae.Status != 400 || !strings.Contains(ae.Detail, "already exists") {
		t.Fatalf("create twice: %#v", ae)
	}

	if err := srv.DropDatabase(ctx, name); err != nil {
		t.Fatal(err)
	}
	if ok, err := srv.Exists(ctx, name); err != nil || ok {
		t.Fatalf("exists after drop: %v %v", ok, err)
	}
	if ae := asArcadeDBError(t, srv.DropDatabase(ctx, name)); ae.Status != 400 {
		t.Fatalf("drop missing: status %d %q", ae.Status, ae.Error())
	}
}

func TestServerCommandListDatabases(t *testing.T) {
	db := newDatabase(t)
	got, err := newServer(t).ServerCommand(context.Background(), "list databases")
	if err != nil {
		t.Fatal(err)
	}
	names, _ := got["result"].([]any)
	if !slices.Contains(names, any(db.Name())) {
		t.Fatalf("got %v, want it to contain %s", got, db.Name())
	}
}

// TestPerUserIsolation is the use case behind issue #122: a database per tenant, and a user
// who can see only theirs.
func TestPerUserIsolation(t *testing.T) {
	ctx := context.Background()
	srv := newServer(t)
	tenant := fmt.Sprintf("e2etenant%d", dbCounter.Add(1))
	user := fmt.Sprintf("e2euser%d", dbCounter.Add(1))
	if err := srv.CreateDatabase(ctx, tenant); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = srv.DropDatabase(context.Background(), tenant) })
	other := newDatabase(t)

	if err := srv.CreateUser(ctx, user, "first-password", map[string][]string{tenant: {"admin"}}); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = srv.DropUser(context.Background(), user) })

	users, err := srv.ListUsers(ctx)
	if err != nil {
		t.Fatal(err)
	}
	i := slices.IndexFunc(users, func(u arcadedb.User) bool { return u.Name == user })
	if i < 0 || !slices.Equal(users[i].Databases[tenant], []string{"admin"}) {
		t.Fatalf("user %s not listed with its assignment: %#v", user, users)
	}

	// 409 since ArcadeData/arcadedb#10076; earlier servers answered 403 "Security error", the
	// status a non-root caller also gets. CreateUser's doc comment and the README rely on it.
	if ae := asArcadeDBError(t, srv.CreateUser(ctx, user, "first-password", nil)); ae.Status != 409 || !strings.Contains(ae.Error(), "already exists") {
		t.Fatalf("create user twice: %#v", ae)
	}

	asUser := func(password string) *arcadedb.Server {
		s, err := arcadedb.NewServer(baseURL, arcadedb.WithBasicAuth(user, password))
		if err != nil {
			t.Fatal(err)
		}
		t.Cleanup(func() { _ = s.Close() })
		return s
	}
	visible, err := asUser("first-password").ListDatabases(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if !slices.Contains(visible, tenant) || slices.Contains(visible, other.Name()) {
		t.Fatalf("user sees %v; want %s and not %s", visible, tenant, other.Name())
	}

	if err := srv.UpdateUser(ctx, user, arcadedb.UserUpdate{Password: "second-password"}); err != nil {
		t.Fatal(err)
	}
	if _, err := asUser("second-password").ListDatabases(ctx); err != nil {
		t.Fatalf("new password refused: %v", err)
	}

	if err := srv.DropUser(ctx, user); err != nil {
		t.Fatal(err)
	}
	if ae := asArcadeDBError(t, srv.DropUser(ctx, user)); ae.Status != 404 {
		t.Fatalf("drop missing user: status %d %q", ae.Status, ae.Error())
	}
	if ae := asArcadeDBError(t, srv.UpdateUser(ctx, user, arcadedb.UserUpdate{Password: "third-password"})); ae.Status != 404 {
		t.Fatalf("update missing user: status %d %q", ae.Status, ae.Error())
	}
}

func TestGroupLifecycle(t *testing.T) {
	ctx := context.Background()
	srv := newServer(t)
	db := newDatabase(t)
	limit := 10
	if err := srv.SaveGroup(ctx, generated.SaveGroupRequest{Database: db.Name(), Name: "reader", ResultSetLimit: &limit}); err != nil {
		t.Fatal(err)
	}
	groups, err := srv.ListGroups(ctx)
	if err != nil {
		t.Fatal(err)
	}
	g, ok := groups[db.Name()]["reader"]
	if !ok || g.ResultSetLimit != 10 {
		t.Fatalf("group not listed as saved: %#v", groups[db.Name()])
	}
	if err := srv.DeleteGroup(ctx, db.Name(), "reader"); err != nil {
		t.Fatal(err)
	}
	groups, err = srv.ListGroups(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := groups[db.Name()]["reader"]; ok {
		t.Fatalf("group still listed after delete")
	}
}

func TestSQLScript(t *testing.T) {
	ctx := context.Background()
	db := newDatabase(t)
	if _, err := db.Command(ctx, arcadedb.SQLScript,
		"CREATE DOCUMENT TYPE Script; INSERT INTO Script SET x = 1; INSERT INTO Script SET x = 2;", nil); err != nil {
		t.Fatal(err)
	}
	env, err := db.Query(ctx, arcadedb.SQL, "SELECT count(*) AS n FROM Script", nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(env.Result) != 1 || env.Result[0]["n"] != float64(2) {
		t.Fatalf("got %#v", env.Result)
	}
}
