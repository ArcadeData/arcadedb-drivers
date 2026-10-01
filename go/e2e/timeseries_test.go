package e2e

import (
	"context"
	"slices"
	"testing"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb"
	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

const tsType = "GoTsPoint"

// seedTimeSeries creates the TIMESERIES type and writes three points. CREATE TIMESERIES TYPE
// takes the tag and field columns inline: a later CREATE PROPERTY adds a schema column that a
// time-series write never populates, so the columns must be named in this one statement.
func seedTimeSeries(t *testing.T, db *arcadedb.Database) {
	t.Helper()
	mustCommand(t, db, "CREATE TIMESERIES TYPE "+tsType+" TIMESTAMP ts TAGS (sensor STRING) FIELDS (value DOUBLE)")
	lp := tsType + ",sensor=a value=1.5 1000\n" + tsType + ",sensor=a value=2.5 2000\n" + tsType + ",sensor=a value=3.5 3000\n"
	if err := db.TS().Write(context.Background(), lp, "ms"); err != nil {
		t.Fatal(err)
	}
}

func TestTimeSeriesWriteQueryLatest(t *testing.T) {
	ctx := context.Background()
	db := newDatabase(t)
	seedTimeSeries(t, db)

	res, err := db.TS().Query(ctx, map[string]any{"type": tsType})
	if err != nil {
		t.Fatal(err)
	}
	rows, _ := res["rows"].([]any)
	if len(rows) != 3 || res["count"] != float64(3) || res["truncated"] != false {
		t.Fatalf("query = %v", res)
	}

	latest, err := db.TS().Latest(ctx, tsType, "")
	if err != nil {
		t.Fatal(err)
	}
	point, _ := latest["latest"].([]any)
	if len(point) != 3 || point[0] != float64(3000) || point[2] != 3.5 {
		t.Fatalf("latest = %v", latest)
	}
}

func TestGrafanaAndPromQL(t *testing.T) {
	ctx := context.Background()
	db := newDatabase(t)
	seedTimeSeries(t, db)

	graf, err := db.Grafana().Query(ctx, map[string]any{
		"from": 0, "to": 10000,
		"targets": []map[string]any{{"refId": "A", "type": tsType}},
	})
	if err != nil {
		t.Fatal(err)
	}
	frames, _ := graf["results"].(map[string]any)["A"].(map[string]any)["frames"].([]any)
	if len(frames) != 1 {
		t.Fatalf("grafana = %v", graf)
	}
	values := frames[0].(map[string]any)["data"].(map[string]any)["values"].([]any)
	if len(values) != 3 || len(values[0].([]any)) != 3 {
		t.Fatalf("grafana values = %v", values)
	}

	labels, err := db.PromQL().Labels(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if !slices.Contains(labels.Data, "sensor") {
		t.Fatalf("labels = %v", labels.Data)
	}

	// The metric name is the type name; the field is a column, not part of the name.
	q, err := db.PromQL().Query(ctx, generated.PromQLQueryParams{Query: tsType, Time: ptr("3")})
	if err != nil {
		t.Fatal(err)
	}
	if q.Status != "success" || q.Data.ResultType != "vector" {
		t.Fatalf("query = %+v", q)
	}
	vec, err := q.Data.Result.AsPromQLDataResponseDataResult0()
	if err != nil || len(vec) != 1 || vec[0].Metric["sensor"] != "a" {
		t.Fatalf("vector = %+v, %v", vec, err)
	}

	qr, err := db.PromQL().QueryRange(ctx, generated.PromQLQueryRangeParams{Query: tsType, Start: "0", End: "4", Step: "1"})
	if err != nil {
		t.Fatal(err)
	}
	if qr.Data.ResultType != "matrix" {
		t.Fatalf("range = %+v", qr)
	}
	mat, err := qr.Data.Result.AsPromQLDataResponseDataResult1()
	if err != nil || len(mat) != 1 || len(mat[0].Values) < 3 {
		t.Fatalf("matrix = %+v, %v", mat, err)
	}

	series, err := db.PromQL().Series(ctx, generated.PromQLSeriesParams{Match: []string{tsType}, Start: ptr("0"), End: ptr("4")})
	if err != nil {
		t.Fatal(err)
	}
	if len(series.Data) != 1 || series.Data[0]["sensor"] != "a" {
		t.Fatalf("series = %+v", series.Data)
	}
}
