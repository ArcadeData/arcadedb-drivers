package e2e

import (
	"context"
	"errors"
	"fmt"
	"slices"
	"strings"
	"testing"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb"
)

// TestLoginQueryLogout is issue #123's acceptance path: log in as a user, act as that user
// with the token alone, log out, and see the token refused.
func TestLoginQueryLogout(t *testing.T) {
	ctx := context.Background()
	root := newServer(t)
	tenant := newDatabase(t)
	other := newDatabase(t)
	user := fmt.Sprintf("e2esession%d", dbCounter.Add(1))
	if err := root.CreateUser(ctx, user, "session-password", map[string][]string{tenant.Name(): {"admin"}}); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = root.DropUser(context.Background(), user) })

	// 401 since ArcadeData/arcadedb#10109; earlier servers answered 403. Login's doc comment relies on it.
	if ae := asArcadeDBError(t, func() error { _, err := root.LoginAs(ctx, user, "wrong-password"); return err }()); ae.Status != 401 {
		t.Fatalf("wrong password: status %d %q", ae.Status, ae.Error())
	}

	login, err := root.LoginAs(ctx, user, "session-password")
	if err != nil {
		t.Fatal(err)
	}
	if login.User != user || !strings.HasPrefix(login.Token, "AU-") {
		t.Fatalf("got %+v", login)
	}
	asUser := root.WithToken(login.Token)

	visible, err := asUser.ListDatabases(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if !slices.Contains(visible, tenant.Name()) || slices.Contains(visible, other.Name()) {
		t.Fatalf("user sees %v; want %s and not %s", visible, tenant.Name(), other.Name())
	}
	if _, err := asUser.DB(tenant.Name()).Query(ctx, arcadedb.SQL, "SELECT 1 AS one", nil); err != nil {
		t.Fatalf("query as the user: %v", err)
	}

	sessions, err := root.ListSessions(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if !slices.ContainsFunc(sessions, func(s arcadedb.Session) bool { return s.Token == login.Token && s.User == user }) {
		t.Fatalf("session not listed: %+v", sessions)
	}
	if ae := asArcadeDBError(t, func() error { _, err := asUser.ListSessions(ctx); return err }()); ae.Status != 403 {
		t.Fatalf("list sessions as a non-root user: status %d %q", ae.Status, ae.Error())
	}

	if err := root.Logout(ctx); !errors.Is(err, arcadedb.ErrNotSessionToken) {
		t.Fatalf("logout on a Basic client: %v", err)
	}
	if err := asUser.Logout(ctx); err != nil {
		t.Fatal(err)
	}
	if ae := asArcadeDBError(t, func() error { _, err := asUser.ListDatabases(ctx); return err }()); ae.Status != 401 {
		t.Fatalf("token after logout: status %d %q", ae.Status, ae.Error())
	}
	if ae := asArcadeDBError(t, asUser.Logout(ctx)); ae.Status != 401 {
		t.Fatalf("logout twice: status %d %q", ae.Status, ae.Error())
	}
}

func TestAPITokenLifecycle(t *testing.T) {
	ctx := context.Background()
	root := newServer(t)
	db := newDatabase(t)
	name := fmt.Sprintf("e2etoken%d", dbCounter.Add(1))

	created, err := root.CreateAPIToken(ctx, arcadedb.APITokenRequest{Name: name, Database: db.Name()})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = root.DeleteAPIToken(context.Background(), created.TokenHash) })
	if !strings.HasPrefix(created.Token, "at-") || created.Name != name || created.Database != db.Name() ||
		!created.ExpiresAt.IsZero() || created.Expired || !strings.HasSuffix(created.Token, created.TokenSuffix) {
		t.Fatalf("got %+v", created.APIToken)
	}

	tokens, err := root.ListAPITokens(ctx)
	if err != nil {
		t.Fatal(err)
	}
	i := slices.IndexFunc(tokens, func(a arcadedb.APIToken) bool { return a.Name == name })
	if i < 0 || tokens[i].TokenHash != created.TokenHash || tokens[i].TokenSuffix != created.TokenSuffix {
		t.Fatalf("token not listed as created: %+v", tokens)
	}

	// A taken name is a 409; CreateAPIToken's doc comment and the README rely on it.
	if ae := asArcadeDBError(t, func() error {
		_, err := root.CreateAPIToken(ctx, arcadedb.APITokenRequest{Name: name})
		return err
	}()); ae.Status != 409 {
		t.Fatalf("create twice: status %d %q", ae.Status, ae.Error())
	}

	withToken := root.WithToken(created.Token)
	if _, err := withToken.ListDatabases(ctx); err != nil {
		t.Fatalf("the API token does not authenticate: %v", err)
	}
	if err := withToken.Logout(ctx); !errors.Is(err, arcadedb.ErrNotSessionToken) {
		t.Fatalf("logout with an API token: %v", err)
	}

	if err := root.DeleteAPIToken(ctx, created.Token); !errors.Is(err, arcadedb.ErrInvalidTokenHash) {
		t.Fatalf("delete by plaintext: %v", err)
	}
	if err := root.DeleteAPIToken(ctx, created.TokenHash); err != nil {
		t.Fatal(err)
	}
	// 404 is not in the contract's list for deleteApiToken; measured here.
	if ae := asArcadeDBError(t, root.DeleteAPIToken(ctx, created.TokenHash)); ae.Status != 404 {
		t.Fatalf("delete twice: status %d %q", ae.Status, ae.Error())
	}
	if ae := asArcadeDBError(t, func() error { _, err := withToken.ListDatabases(ctx); return err }()); ae.Status != 401 {
		t.Fatalf("token after delete: status %d %q", ae.Status, ae.Error())
	}
}
