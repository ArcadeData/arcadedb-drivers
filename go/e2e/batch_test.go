package e2e

import (
	"context"
	"slices"
	"testing"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb"
	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

func batchSchema(t *testing.T) *arcadedb.Database {
	t.Helper()
	db := newDatabase(t)
	mustCommand(t, db, "CREATE VERTEX TYPE Person IF NOT EXISTS")
	mustCommand(t, db, "CREATE PROPERTY Person.name IF NOT EXISTS STRING")
	mustCommand(t, db, "CREATE EDGE TYPE Knows IF NOT EXISTS")
	return db
}

func TestBatchLoadAndStream(t *testing.T) {
	ctx := context.Background()
	db := batchSchema(t)

	summary, err := db.BatchLoad(ctx,
		slices.Values([]arcadedb.VertexRow{
			{Type: "Person", ID: "a", Properties: map[string]any{"name": "Ann"}},
			{Type: "Person", ID: "b", Properties: map[string]any{"name": "Ben"}},
		}),
		slices.Values([]arcadedb.EdgeRow{{Type: "Knows", From: "a", To: "b", Properties: map[string]any{"since": 2020}}}),
		nil)
	if err != nil {
		t.Fatal(err)
	}
	if summary["verticesCreated"] != float64(2) || summary["edgesCreated"] != float64(1) {
		t.Fatalf("summary = %v", summary)
	}
	mapping, _ := summary["idMapping"].(map[string]any)
	if _, ok := mapping["a"]; !ok {
		t.Fatalf("idMapping = %v", summary["idMapping"])
	}
	if _, ok := mapping["b"]; !ok {
		t.Fatalf("idMapping = %v", summary["idMapping"])
	}

	// The regression guard for nested properties: the load answers 200 with correct counters
	// either way, so only a query for the property by name notices.
	env, err := db.Query(ctx, arcadedb.SQL, "SELECT FROM Person WHERE name = 'Ann'", nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(env.Result) != 1 || env.Result[0]["name"] != "Ann" {
		t.Fatalf("property not stored as a real field: %v", env.Result)
	}

	var events []map[string]any
	for ev, err := range db.BatchLoadStream(ctx,
		slices.Values([]arcadedb.VertexRow{
			{Type: "Person", ID: "d", Properties: map[string]any{"name": "Dan"}},
			{Type: "Person", ID: "e", Properties: map[string]any{"name": "Eve"}},
		}),
		slices.Values([]arcadedb.EdgeRow{{Type: "Knows", From: "d", To: "e"}}),
		&generated.ExecuteBatchParams{CommitEvery: ptr(1)}) {
		if err != nil {
			t.Fatal(err)
		}
		events = append(events, ev)
	}
	progress, summaries := 0, 0
	for _, ev := range events {
		if _, ok := ev["progress"]; ok {
			progress++
		}
		if _, ok := ev["summary"]; ok {
			summaries++
		}
	}
	if progress == 0 || summaries != 1 {
		t.Fatalf("progress %d, summaries %d: %v", progress, summaries, events)
	}
	last, ok := events[len(events)-1]["summary"].(map[string]any)
	if !ok {
		t.Fatalf("summary is not the last event: %v", events)
	}
	if last["idMappingStreamed"] != true {
		t.Fatalf("summary = %v", last)
	}
	if _, ok := last["idMappingSize"].(float64); !ok {
		t.Fatalf("idMappingSize missing: %v", last)
	}
	if _, ok := last["idMapping"]; ok {
		t.Fatalf("streamed summary carries the buffered idMapping: %v", last)
	}
}
