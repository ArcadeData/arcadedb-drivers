package e2e

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"slices"
	"strings"
	"testing"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc"
	"github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc/generated"
	"google.golang.org/grpc/status"
)

func person(name string) *generated.GrpcRecord {
	return &generated.GrpcRecord{
		Type:       "Person",
		Properties: map[string]*generated.GrpcValue{"name": {Kind: &generated.GrpcValue_StringValue{StringValue: name}}},
	}
}

// uniqueMarker makes a name prefix no other test's rows share, since one database hosts a
// whole test.
func uniqueMarker(prefix string) string { return fmt.Sprintf("%s%d", prefix, dbCounter.Add(1)) }

func insertPersonSQL(name string) *generated.ExecuteCommandRequest {
	return &generated.ExecuteCommandRequest{Language: "sql", Command: "INSERT INTO Person SET name = '" + name + "'"}
}

// personNames returns the sorted names of Person rows whose name starts with marker, read
// through StreamQuery.
func personNames(t *testing.T, c *arcadedbgrpc.Client, db, marker string) []string {
	t.Helper()
	var names []string
	for rec, err := range c.StreamQuery(context.Background(), &generated.StreamQueryRequest{
		Database: db, Language: "sql", Query: "SELECT FROM Person WHERE name LIKE '" + marker + "%'",
	}) {
		if err != nil {
			t.Fatal(err)
		}
		names = append(names, rec.GetProperties()["name"].GetStringValue())
	}
	slices.Sort(names)
	return names
}

func TestGrpcPasswordAuth(t *testing.T) {
	db := newGrpcDatabase(t)
	c := newGrpcClient(t, db)
	resp, err := c.Raw().ExecuteQuery(context.Background(), &generated.ExecuteQueryRequest{
		Database: db, Language: "sql", Query: "SELECT FROM Person",
	})
	if err != nil || resp == nil {
		t.Fatalf("ExecuteQuery = %v, %v", resp, err)
	}
}

func TestGrpcBearerAuth(t *testing.T) {
	db := newGrpcDatabase(t)
	// The token is minted over HTTP (no data-plane RPC mints one) and presented as a gRPC
	// bearer credential: the session token both drivers share, against the real service.
	req, err := http.NewRequest(http.MethodPost, grpcBaseURL+"/api/v1/login", nil)
	if err != nil {
		t.Fatal(err)
	}
	req.SetBasicAuth("root", rootPassword)
	hresp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = hresp.Body.Close() }()
	var login struct {
		Token string `json:"token"`
	}
	if err := json.NewDecoder(hresp.Body).Decode(&login); err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(login.Token, "AU-") {
		t.Fatalf("token = %q, want AU- prefix", login.Token)
	}
	c, err := arcadedbgrpc.NewClient(grpcTarget, arcadedbgrpc.WithBearerToken(login.Token), arcadedbgrpc.WithInsecure())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = c.Close() })
	resp, err := c.Raw().ExecuteQuery(context.Background(), &generated.ExecuteQueryRequest{
		Database: db, Language: "sql", Query: "SELECT FROM Person",
	})
	if err != nil || resp == nil {
		t.Fatalf("ExecuteQuery = %v, %v", resp, err)
	}
}

func TestGrpcStreamQuery(t *testing.T) {
	db := newGrpcDatabase(t)
	c := newGrpcClient(t, db)
	marker := uniqueMarker("sq")
	if _, err := c.Raw().ExecuteCommand(context.Background(), &generated.ExecuteCommandRequest{
		Database: db, Language: "sql", Command: "INSERT INTO Person SET name = '" + marker + "-a'",
	}); err != nil {
		t.Fatal(err)
	}
	if got := personNames(t, c, db, marker); !slices.Equal(got, []string{marker + "-a"}) {
		t.Fatalf("names = %v", got)
	}
}

func TestGrpcInsertStream(t *testing.T) {
	db := newGrpcDatabase(t)
	c := newGrpcClient(t, db)
	marker := uniqueMarker("is")
	summary, err := c.InsertStream(context.Background(), arcadedbgrpc.InsertStreamRequest{
		Database: db,
		Options:  &generated.InsertOptions{TargetClass: "Person"},
		Chunks: slices.Values([][]*generated.GrpcRecord{
			{person(marker + "-a"), person(marker + "-b")},
			{person(marker + "-c")},
		}),
	})
	if err != nil {
		t.Fatal(err)
	}
	if summary.GetInserted() != 3 {
		t.Fatalf("summary = %v", summary)
	}
	want := []string{marker + "-a", marker + "-b", marker + "-c"}
	if got := personNames(t, c, db, marker); !slices.Equal(got, want) {
		t.Fatalf("names = %v, want %v", got, want)
	}
}

func TestGrpcEmptyInsertStream(t *testing.T) {
	db := newGrpcDatabase(t)
	c := newGrpcClient(t, db)
	summary, err := c.InsertStream(context.Background(), arcadedbgrpc.InsertStreamRequest{
		Database: db,
		Options:  &generated.InsertOptions{TargetClass: "Person"},
		Chunks:   slices.Values([][]*generated.GrpcRecord(nil)),
	})
	if err != nil {
		t.Fatal(err)
	}
	if summary.GetInserted() != 0 || summary.GetFailed() != 0 {
		t.Fatalf("summary = %v", summary)
	}
}

func TestGrpcTransactionCommitAndRollback(t *testing.T) {
	ctx := context.Background()
	db := newGrpcDatabase(t)
	c := newGrpcClient(t, db)

	committed := uniqueMarker("tc")
	err := c.Transaction(ctx, db, func(tx *arcadedbgrpc.TxHandle) error {
		_, err := tx.ExecuteCommand(ctx, insertPersonSQL(committed+"-a"))
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	if got := personNames(t, c, db, committed); !slices.Equal(got, []string{committed + "-a"}) {
		t.Fatalf("committed names = %v", got)
	}

	rolledBack := uniqueMarker("tr")
	sentinel := errors.New("boom")
	err = c.Transaction(ctx, db, func(tx *arcadedbgrpc.TxHandle) error {
		if _, err := tx.ExecuteCommand(ctx, insertPersonSQL(rolledBack+"-a")); err != nil {
			return err
		}
		return sentinel
	})
	if !errors.Is(err, sentinel) {
		t.Fatalf("err = %v, want the callback's sentinel", err)
	}
	if got := personNames(t, c, db, rolledBack); len(got) != 0 {
		t.Fatalf("rows survived the rollback: %v", got)
	}
}

// The handle outlives its callback in Go, unlike Python's context manager. What the server
// does with a call bound to an already-committed transaction id is observed here, not
// assumed; the doc comment on TxHandle depends on the answer.
func TestGrpcHandleAfterCommitIsRefused(t *testing.T) {
	ctx := context.Background()
	db := newGrpcDatabase(t)
	c := newGrpcClient(t, db)
	marker := uniqueMarker("hc")

	var captured *arcadedbgrpc.TxHandle
	if err := c.Transaction(ctx, db, func(tx *arcadedbgrpc.TxHandle) error {
		captured = tx
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	_, err := captured.ExecuteCommand(ctx, insertPersonSQL(marker+"-late"))
	t.Logf("ExecuteCommand on a committed handle: err=%v code=%v", err, status.Code(err))
	if err == nil {
		t.Errorf("the server accepted a command on a committed transaction id")
	}
	if got := personNames(t, c, db, marker); len(got) != 0 {
		t.Errorf("row inserted through a committed handle: %v", got)
	}
}

func TestGrpcVectorHybridFulltextRaw(t *testing.T) {
	ctx := context.Background()
	db := newGrpcDatabase(t)
	c := newGrpcClient(t, db)
	query := []float32{1, 0, 0, 0}

	vec, err := c.Raw().VectorSearch(ctx, &generated.VectorSearchRequest{
		Database: db, IndexName: vectorIndexName, QueryVector: query, K: 10,
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(vec.GetResults()) == 0 || vec.GetCount() != 3 {
		t.Fatalf("vector = %v", vec)
	}
	// k (10) exceeds the row count (3), so the window was never filled: a complete answer.
	if vec.GetTruncated() {
		t.Error("vector search truncated")
	}
	// The query vector is red-apple's embedding, so its distance is exactly 0.
	if vec.GetResults()[0].GetDistance() != 0 {
		t.Errorf("first distance = %v, want 0", vec.GetResults()[0].GetDistance())
	}
	var distances []float64
	for _, hit := range vec.GetResults() {
		distances = append(distances, hit.GetDistance())
	}
	if !slices.IsSorted(distances) {
		t.Errorf("distances not nearest-first: %v", distances)
	}

	hyb, err := c.Raw().HybridSearch(ctx, &generated.HybridSearchRequest{
		Database: db, VectorIndexName: vectorIndexName, QueryVector: query, K: 10,
		FulltextIndexName: fulltextIndexName, FulltextQuery: "apple",
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(hyb.GetResults()) == 0 || hyb.GetCount() != 3 || !hyb.GetFused() {
		t.Fatalf("hybrid = %v", hyb)
	}

	ft, err := c.Raw().FullTextSearch(ctx, &generated.FullTextSearchRequest{
		Database: db, IndexName: fulltextIndexName, QueryText: "apple",
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(ft.GetResults()) == 0 || ft.GetCount() != 2 {
		t.Fatalf("fulltext = %v", ft)
	}
}

func TestGrpcSearchThroughTxHandle(t *testing.T) {
	ctx := context.Background()
	db := newGrpcDatabase(t)
	c := newGrpcClient(t, db)
	var (
		vec *generated.VectorSearchResponse
		hyb *generated.HybridSearchResponse
		ft  *generated.FullTextSearchResponse
	)
	err := c.Transaction(ctx, db, func(tx *arcadedbgrpc.TxHandle) (err error) {
		if vec, err = tx.VectorSearch(ctx, &generated.VectorSearchRequest{
			IndexName: vectorIndexName, QueryVector: []float32{1, 0, 0, 0}, K: 10,
		}); err != nil {
			return err
		}
		if hyb, err = tx.HybridSearch(ctx, &generated.HybridSearchRequest{
			VectorIndexName: vectorIndexName, QueryVector: []float32{1, 0, 0, 0}, K: 10,
			FulltextIndexName: fulltextIndexName, FulltextQuery: "apple",
		}); err != nil {
			return err
		}
		ft, err = tx.FullTextSearch(ctx, &generated.FullTextSearchRequest{IndexName: fulltextIndexName, QueryText: "apple"})
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(vec.GetResults()) == 0 || vec.GetTruncated() {
		t.Errorf("vector = %v", vec)
	}
	if len(hyb.GetResults()) == 0 || !hyb.GetFused() {
		t.Errorf("hybrid = %v", hyb)
	}
	if len(ft.GetResults()) == 0 {
		t.Errorf("fulltext = %v", ft)
	}
}

func tsPoint(ts int64, sensor string, value float64) *generated.TimeSeriesPoint {
	return &generated.TimeSeriesPoint{
		Timestamp: ts,
		Tags:      map[string]*generated.GrpcValue{"sensor": {Kind: &generated.GrpcValue_StringValue{StringValue: sensor}}},
		Fields:    map[string]*generated.GrpcValue{"value": {Kind: &generated.GrpcValue_DoubleValue{DoubleValue: value}}},
	}
}

// A multi-chunk write is the only thing that proves the per-chunk envelope (database, type
// and precision repeated on every wire chunk) works against a real server.
func TestGrpcTimeSeriesWriteQueryLatest(t *testing.T) {
	ctx := context.Background()
	db := newGrpcDatabase(t)
	c := newGrpcClient(t, db)
	ms := generated.TimeSeriesPrecision_TS_PRECISION_MILLISECONDS

	summary, err := c.TimeSeriesWriteStream(ctx, arcadedbgrpc.TimeSeriesWriteStreamRequest{
		Database:  db,
		Type:      grpcTsType,
		Precision: &ms,
		Chunks: slices.Values([][]*generated.TimeSeriesPoint{
			{tsPoint(1000, "A", 1.1), tsPoint(2000, "A", 1.2)},
			{tsPoint(3000, "B", 2.1)},
		}),
	})
	if err != nil {
		t.Fatal(err)
	}
	if summary.GetReceived() != 3 || summary.GetWritten() != 3 || summary.GetDropped() != 0 {
		t.Fatalf("summary = %v", summary)
	}

	rows := 0
	for res, err := range c.TimeSeriesQuery(ctx, &generated.TimeSeriesQueryRequest{Database: db, Type: grpcTsType}) {
		if err != nil {
			t.Fatal(err)
		}
		rows += len(res.GetRows())
	}
	if rows == 0 {
		t.Fatal("time-series query returned no rows")
	}

	var latest *generated.TimeSeriesLatestResponse
	if err := c.Transaction(ctx, db, func(tx *arcadedbgrpc.TxHandle) (err error) {
		latest, err = tx.TimeSeriesLatest(ctx, &generated.TimeSeriesLatestRequest{Type: grpcTsType})
		return err
	}); err != nil {
		t.Fatal(err)
	}
	if !latest.GetFound() {
		t.Fatalf("latest = %v", latest)
	}
	i := slices.Index(latest.GetColumns(), "ts")
	if i < 0 || latest.GetLatest().GetValues()[i].GetInt64Value() != 3000 {
		t.Fatalf("latest = %v", latest)
	}
}

func TestGrpcEmptyTimeSeriesWriteStream(t *testing.T) {
	db := newGrpcDatabase(t)
	c := newGrpcClient(t, db)
	ms := generated.TimeSeriesPrecision_TS_PRECISION_MILLISECONDS
	summary, err := c.TimeSeriesWriteStream(context.Background(), arcadedbgrpc.TimeSeriesWriteStreamRequest{
		Database:  db,
		Type:      grpcTsType,
		Precision: &ms,
		Chunks:    slices.Values([][]*generated.TimeSeriesPoint(nil)),
	})
	if err != nil {
		t.Fatal(err)
	}
	if summary.GetReceived() != 0 || summary.GetWritten() != 0 || summary.GetDropped() != 0 ||
		len(summary.GetUnknownTypes()) != 0 || len(summary.GetNonTimeSeriesTypes()) != 0 ||
		len(summary.GetUnavailableTypes()) != 0 {
		t.Fatalf("summary = %v", summary)
	}
}

func TestGrpcRawAdminHealth(t *testing.T) {
	c := newGrpcClient(t, "")
	admin, err := c.RawAdmin()
	if err != nil {
		t.Fatal(err)
	}
	resp, err := admin.Health(context.Background(), &generated.HealthRequest{})
	if err != nil {
		t.Fatal(err)
	}
	if !resp.GetOk() {
		t.Fatalf("health = %v", resp)
	}
}
