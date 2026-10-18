package e2e

import (
	"context"
	"testing"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb"
	"github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc"
	"github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc/generated"
)

// The isolation tests (issue #152) read one record twice inside a transaction while another
// session changes it in between. REPEATABLE_READ keeps the first value; READ_COMMITTED, and
// the default with no level, shows the committed change.

func TestTransactionIsolationLevel(t *testing.T) {
	ctx := context.Background()
	db := newDatabase(t)
	mustCommand(t, db, "CREATE DOCUMENT TYPE IsoDoc IF NOT EXISTS")
	env, err := db.Command(ctx, arcadedb.SQL, "INSERT INTO IsoDoc SET v = 'one'", nil)
	if err != nil {
		t.Fatal(err)
	}
	rid, _ := env.Result[0]["@rid"].(string)

	read := func(tx *arcadedb.Database) string {
		t.Helper()
		env, err := tx.Query(ctx, arcadedb.SQL, "SELECT v FROM "+rid, nil)
		if err != nil {
			t.Fatal(err)
		}
		v, _ := env.Result[0]["v"].(string)
		return v
	}
	for _, tc := range []struct {
		name   string
		opts   []arcadedb.TransactionOption
		second string
	}{
		{"repeatable read", []arcadedb.TransactionOption{arcadedb.WithIsolationLevel(arcadedb.RepeatableRead)}, "one"},
		{"read committed", []arcadedb.TransactionOption{arcadedb.WithIsolationLevel(arcadedb.ReadCommitted)}, "two"},
		{"default", nil, "two"},
	} {
		mustCommand(t, db, "UPDATE "+rid+" SET v = 'one'")
		var first, second string
		err := db.Transaction(ctx, func(tx *arcadedb.Database) error {
			first = read(tx)
			mustCommand(t, db, "UPDATE "+rid+" SET v = 'two'") // outside the transaction
			second = read(tx)
			return nil
		}, tc.opts...)
		if err != nil {
			t.Fatalf("%s: %v", tc.name, err)
		}
		if first != "one" || second != tc.second {
			t.Fatalf("%s: reads = %q, %q, want \"one\", %q", tc.name, first, second, tc.second)
		}
	}
}

func TestGrpcTransactionIsolationLevel(t *testing.T) {
	ctx := context.Background()
	db := newGrpcDatabase(t)
	c := newGrpcClient(t, db)
	marker := uniqueMarker("iso")
	if _, err := c.Raw().ExecuteCommand(ctx, &generated.ExecuteCommandRequest{
		Database: db, Language: "sql", Command: "INSERT INTO Person SET name = '" + marker + "', v = 'one'",
	}); err != nil {
		t.Fatal(err)
	}
	set := func(v string) {
		t.Helper()
		if _, err := c.Raw().ExecuteCommand(ctx, &generated.ExecuteCommandRequest{
			Database: db, Language: "sql", Command: "UPDATE Person SET v = '" + v + "' WHERE name = '" + marker + "'",
		}); err != nil {
			t.Fatal(err)
		}
	}
	read := func(tx *arcadedbgrpc.TxHandle) string {
		t.Helper()
		resp, err := tx.ExecuteQuery(ctx, &generated.ExecuteQueryRequest{
			Language: "sql", Query: "SELECT v FROM Person WHERE name = '" + marker + "'",
		})
		if err != nil {
			t.Fatal(err)
		}
		return resp.GetResults()[0].GetRecords()[0].GetProperties()["v"].GetStringValue()
	}
	for _, tc := range []struct {
		name   string
		opts   []arcadedbgrpc.TransactionOption
		second string
	}{
		{"repeatable read", []arcadedbgrpc.TransactionOption{arcadedbgrpc.WithIsolationLevel(arcadedbgrpc.RepeatableRead)}, "one"},
		{"read committed", []arcadedbgrpc.TransactionOption{arcadedbgrpc.WithIsolationLevel(arcadedbgrpc.ReadCommitted)}, "two"},
		{"unset", nil, "two"},
	} {
		set("one")
		var first, second string
		err := c.Transaction(ctx, db, func(tx *arcadedbgrpc.TxHandle) error {
			first = read(tx)
			set("two") // outside the transaction
			second = read(tx)
			return nil
		}, tc.opts...)
		if err != nil {
			t.Fatalf("%s: %v", tc.name, err)
		}
		if first != "one" || second != tc.second {
			t.Fatalf("%s: reads = %q, %q, want \"one\", %q", tc.name, first, second, tc.second)
		}
	}
}
