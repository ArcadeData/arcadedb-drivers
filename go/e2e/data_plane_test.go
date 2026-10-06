package e2e

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"testing"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb"
	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

func count(t *testing.T, db *arcadedb.Database, typ string) float64 {
	t.Helper()
	env, err := db.Query(context.Background(), arcadedb.SQL, "SELECT count(*) AS c FROM "+typ, nil)
	if err != nil {
		t.Fatal(err)
	}
	c, _ := env.Result[0]["c"].(float64)
	return c
}

func TestRoundTrip(t *testing.T) {
	ctx := context.Background()
	db := newDatabase(t)
	srv := newServer(t)

	ready, err := srv.Ready(ctx)
	if err != nil || !ready {
		t.Fatalf("Ready = %v, %v", ready, err)
	}
	dbs, err := srv.ListDatabases(ctx)
	if err != nil {
		t.Fatal(err)
	}
	found := false
	for _, n := range dbs {
		found = found || n == db.Name()
	}
	if !found {
		t.Fatalf("%s not in %v", db.Name(), dbs)
	}
	if ok, err := srv.Exists(ctx, db.Name()); err != nil || !ok {
		t.Fatalf("Exists = %v, %v", ok, err)
	}
	if ok, err := srv.Exists(ctx, "no_such_db"); err != nil || ok {
		t.Fatalf("Exists(no_such_db) = %v, %v", ok, err)
	}

	mustCommand(t, db, "CREATE VERTEX TYPE Person IF NOT EXISTS")
	mustCommand(t, db, "INSERT INTO Person SET name = 'Ada', age = 36")
	env, err := db.Query(ctx, arcadedb.SQL, "SELECT FROM Person WHERE age > :min", map[string]any{"min": 18})
	if err != nil {
		t.Fatal(err)
	}
	if len(env.Result) != 1 || env.Result[0]["name"] != "Ada" {
		t.Fatalf("result = %v", env.Result)
	}
	if env.Truncated {
		t.Fatal("Truncated = true")
	}
}

func TestExplainCarriesPlan(t *testing.T) {
	ctx := context.Background()
	db := newDatabase(t)
	mustCommand(t, db, "CREATE VERTEX TYPE Explained IF NOT EXISTS")
	mustCommand(t, db, "INSERT INTO Explained SET n = 1")
	env, err := db.Query(ctx, arcadedb.SQL, "EXPLAIN SELECT FROM Explained", nil)
	if err != nil {
		t.Fatal(err)
	}
	if strings.TrimSpace(env.Explain) == "" {
		t.Fatalf("Explain is empty; env = %+v", env)
	}
	if len(env.ExplainPlan) == 0 {
		t.Fatalf("ExplainPlan is empty; env = %+v", env)
	}
	if len(env.Result) != 0 || env.Returned != 0 {
		t.Fatalf("Result = %v, Returned = %d, want empty and 0", env.Result, env.Returned)
	}
}

func TestTransactionCommitAndRollback(t *testing.T) {
	ctx := context.Background()
	db := newDatabase(t)
	mustCommand(t, db, "CREATE VERTEX TYPE TxCommit IF NOT EXISTS")
	mustCommand(t, db, "CREATE VERTEX TYPE TxRollback IF NOT EXISTS")

	err := db.Transaction(ctx, func(tx *arcadedb.Database) error {
		_, err := tx.Command(ctx, arcadedb.SQL, "INSERT INTO TxCommit SET n = 1", nil)
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	if c := count(t, db, "TxCommit"); c != 1 {
		t.Fatalf("committed count = %v", c)
	}

	abort := errors.New("abort")
	err = db.Transaction(ctx, func(tx *arcadedb.Database) error {
		if _, err := tx.Command(ctx, arcadedb.SQL, "INSERT INTO TxRollback SET n = 1", nil); err != nil {
			return err
		}
		return abort
	})
	if !errors.Is(err, abort) {
		t.Fatalf("err = %v, want abort", err)
	}
	if c := count(t, db, "TxRollback"); c != 0 {
		t.Fatalf("rolled-back count = %v", c)
	}
}

func TestBadQueryCarriesRequestID(t *testing.T) {
	db := newDatabase(t)
	_, err := db.Query(context.Background(), arcadedb.SQL, "SELCT nonsense", nil)
	var ae *arcadedb.ArcadeDBError
	if !errors.As(err, &ae) {
		t.Fatalf("err = %v (%T), want *ArcadeDBError", err, err)
	}
	if ae.Status < 400 || ae.RequestID == "" {
		t.Fatalf("Status = %d, RequestID = %q", ae.Status, ae.RequestID)
	}
}

// createVectorFixture creates a type with a real LSM_VECTOR index, a real FULL_TEXT index and
// three rows of small embeddings. red-apple's embedding is the exact query vector every
// search below uses, so it is always the nearest neighbour (distance 0).
func createVectorFixture(t *testing.T, db *arcadedb.Database) (vectorIndex, fulltextIndex string) {
	t.Helper()
	for _, sql := range []string{
		"CREATE DOCUMENT TYPE VectorItem IF NOT EXISTS",
		"CREATE PROPERTY VectorItem.name STRING",
		"CREATE PROPERTY VectorItem.embedding ARRAY_OF_FLOATS",
		"CREATE PROPERTY VectorItem.description STRING",
		`CREATE INDEX ON VectorItem (embedding) LSM_VECTOR METADATA {"dimensions": 4}`,
		"INSERT INTO VectorItem SET name = 'red-apple', embedding = [1,0,0,0], description = 'a bright red apple'",
		"INSERT INTO VectorItem SET name = 'green-apple', embedding = [0.9,0.1,0,0], description = 'a crisp green apple'",
		"INSERT INTO VectorItem SET name = 'blue-car', embedding = [0,0,1,0], description = 'a fast blue car engine'",
		"CREATE INDEX ON VectorItem (description) FULL_TEXT",
	} {
		mustCommand(t, db, sql)
	}
	return "VectorItem[embedding]", "VectorItem[description]"
}

func ptr[T any](v T) *T { return &v }

func TestVectorSearchHybridFulltext(t *testing.T) {
	ctx := context.Background()
	db := newDatabase(t)
	vecIdx, ftIdx := createVectorFixture(t, db)
	q := []float32{1, 0, 0, 0}

	res, err := db.Vector().Search(ctx, generated.VectorSearchRequest{IndexName: vecIdx, QueryVector: q, K: ptr(10)})
	if err != nil {
		t.Fatal(err)
	}
	if len(res.Results) == 0 || res.Count != 3 {
		t.Fatalf("search: count = %d, results = %d", res.Count, len(res.Results))
	}
	if res.Truncated {
		t.Fatal("k=10 over 3 rows: Truncated = true")
	}
	if d := res.Results[0].Distance; d == nil || *d != 0 {
		t.Fatalf("nearest distance = %v", d)
	}
	for i := 1; i < len(res.Results); i++ {
		if *res.Results[i].Distance < *res.Results[i-1].Distance {
			t.Fatalf("results not nearest-first: %v", res.Results)
		}
	}

	small, err := db.Vector().Search(ctx, generated.VectorSearchRequest{IndexName: vecIdx, QueryVector: q, K: ptr(2)})
	if err != nil {
		t.Fatal(err)
	}
	if small.Count != 2 || !small.Truncated {
		t.Fatalf("k=2: count = %d, truncated = %v", small.Count, small.Truncated)
	}

	hyb, err := db.Vector().Hybrid(ctx, generated.HybridSearchRequest{
		VectorIndexName: vecIdx, QueryVector: q, FulltextIndexName: &ftIdx, FulltextQuery: ptr("apple"), K: ptr(10),
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(hyb.Results) == 0 || hyb.Count != 3 || hyb.Truncated || !hyb.Fused {
		t.Fatalf("hybrid = count %d, results %d, truncated %v, fused %v", hyb.Count, len(hyb.Results), hyb.Truncated, hyb.Fused)
	}

	ft, err := db.Vector().Fulltext(ctx, generated.FullTextSearchRequest{IndexName: &ftIdx, QueryText: "apple"})
	if err != nil {
		t.Fatal(err)
	}
	if len(ft.Results) == 0 || ft.Count != 2 {
		t.Fatalf("fulltext = count %d, results %d", ft.Count, len(ft.Results))
	}
}

const (
	streamType     = "StreamRow"
	streamRowCount = 2000
)

// createStreamRows inserts enough ~150-byte rows that the response is split across many
// real reads, so a decoder with no cross-chunk buffering cannot pass by accident.
func createStreamRows(t *testing.T, db *arcadedb.Database) {
	t.Helper()
	mustCommand(t, db, "CREATE DOCUMENT TYPE "+streamType+" IF NOT EXISTS")
	mustCommand(t, db, "CREATE PROPERTY "+streamType+".n INTEGER")
	mustCommand(t, db, "CREATE PROPERTY "+streamType+".payload STRING")
	payload := strings.Repeat("x", 100)
	var sb strings.Builder
	for i := 0; i < streamRowCount; i++ {
		if i > 0 {
			sb.WriteByte(',')
		}
		fmt.Fprintf(&sb, "(%d,'%s')", i, payload)
	}
	mustCommand(t, db, "INSERT INTO "+streamType+" (n, payload) VALUES "+sb.String())
}

func collect(t *testing.T, seq func(func(arcadedb.StreamEvent, error) bool)) (records []map[string]any, stats *arcadedb.StreamStats) {
	t.Helper()
	for ev, err := range seq {
		if err != nil {
			t.Fatal(err)
		}
		if ev.Record != nil {
			records = append(records, ev.Record)
		}
		if ev.Stats != nil {
			stats = ev.Stats
		}
	}
	return records, stats
}

func TestQueryStreamRecordsAndTrailer(t *testing.T) {
	ctx := context.Background()
	db := newDatabase(t)
	createStreamRows(t, db)
	sql := "SELECT FROM " + streamType

	records, stats := collect(t, db.QueryStream(ctx, arcadedb.SQL, sql, nil, arcadedb.WithLimit(-1)))
	if len(records) != streamRowCount {
		t.Fatalf("records = %d", len(records))
	}
	if stats == nil || stats.Returned != len(records) || stats.Truncated {
		t.Fatalf("stats = %+v", stats)
	}

	// Streaming must return exactly the rows the buffered path does.
	env, err := db.Query(ctx, arcadedb.SQL, sql, nil, arcadedb.WithLimit(-1))
	if err != nil {
		t.Fatal(err)
	}
	if env.Truncated || len(env.Result) != len(records) {
		t.Fatalf("buffered: truncated %v, rows %d", env.Truncated, len(env.Result))
	}
	byN := func(rows []map[string]any) map[float64]string {
		m := map[float64]string{}
		for _, r := range rows {
			m[r["n"].(float64)] = r["payload"].(string)
		}
		return m
	}
	s, b := byN(records), byN(env.Result)
	if len(s) != streamRowCount || len(b) != streamRowCount {
		t.Fatalf("distinct n: streamed %d, buffered %d", len(s), len(b))
	}
	for n, p := range b {
		if s[n] != p {
			t.Fatalf("row %v differs between streamed and buffered", n)
		}
	}

	const capRows = 500
	records, stats = collect(t, db.QueryStream(ctx, arcadedb.SQL, sql, nil, arcadedb.WithLimit(capRows)))
	if len(records) != capRows || stats == nil || stats.Returned != capRows || !stats.Truncated {
		t.Fatalf("capped: records %d, stats %+v", len(records), stats)
	}
}

func TestCommandStreamReadOnly(t *testing.T) {
	// The server, not the client, must honour Accept: application/x-ndjson on /command; only a
	// read-only statement can stream (rows would reach the client before a commit that might
	// still roll back), so a SELECT is the one shape /command streams at all.
	db := newDatabase(t)
	createStreamRows(t, db)
	records, stats := collect(t, db.CommandStream(context.Background(), arcadedb.SQL, "SELECT FROM "+streamType+" WHERE n < 5", nil))
	if len(records) != 5 || stats == nil || stats.Returned != 5 {
		t.Fatalf("records %d, stats %+v", len(records), stats)
	}
}
