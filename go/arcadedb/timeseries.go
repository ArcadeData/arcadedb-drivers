package arcadedb

import (
	"bytes"
	"context"
	"encoding/json"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

// TimeSeries is the time-series namespace of a Database: line-protocol ingest, queries
// and the latest sample per series. Obtain it with Database.TS.
//
// Query and Latest return the whole JSON body as a map[string]any and deliberately do
// NOT route through the generated typed parser (they call the plain generated Client and
// decode the body themselves). Do not "fix" that back to the ...WithResponse methods:
//
//   - The contract types the response as a oneOf of a raw and an aggregated model with no
//     discriminator. The generated union is a bare json.RawMessage, and both As...
//     accessors succeed on either payload (the all-optional aggregated model "parses" a
//     raw response into an empty-looking one), so a typed caller can silently read the
//     wrong shape.
//   - The typed raw model has no limit or truncated field, so the parse discards the
//     very flag that says the rows are a partial answer (Query stops at the row limit,
//     20000 by default, and reports truncated: true). The map keeps it.
//   - Scalar elements (a timestamp, a measurement) are typed as bare objects in the
//     contract. In Go that generates interface{}, so unlike the Python client's models
//     they do not crash; through the map they arrive as float64 (a JSON number decodes
//     to float64, so a timestamp above 2^53 would lose precision), string or bool, exactly
//     as the server sent them.
//
// Every call sends the session header when the Database is inside a Transaction. For
// Write that only refreshes the session's idle timer and turns an unknown session into a
// 404: the samples are committed as they are appended, and a rollback does not remove
// them.
type TimeSeries struct {
	db *Database
}

// TS returns the time-series namespace. It performs no request.
func (d *Database) TS() *TimeSeries { return &TimeSeries{db: d} }

// Write ingests samples in InfluxDB Line Protocol, sent as a text/plain body. precision is
// the unit of the timestamps in the payload: "ns", "us", "ms" or "s"; "" omits the
// parameter and the server then reads nanoseconds. The value is passed through, not
// validated: an unknown unit is the server's 400. A successful write answers 204.
func (t *TimeSeries) Write(ctx context.Context, lineProtocol string, precision string) error {
	params := &generated.WriteTimeSeriesParams{ArcadedbSessionId: t.db.sessionParam()}
	if precision != "" {
		p := generated.WriteTimeSeriesParamsPrecision(precision)
		params.Precision = &p
	}
	resp, err := t.db.srv.raw.WriteTimeSeriesWithTextBody(ctx, t.db.name, params, lineProtocol)
	if err != nil {
		return err
	}
	_, err = readChecked(resp)
	return err
}

// Query queries samples, raw or (when body carries "aggregation") bucketed, and returns the
// parsed JSON body unaltered. See TimeSeries for why it bypasses the typed parser. Check
// "truncated" on a raw result: it is true when the row limit cut the answer short.
//
// A name in body["tags"] that is no TAG column of the type is refused with a 400 rather
// than dropped.
func (t *TimeSeries) Query(ctx context.Context, body map[string]any) (map[string]any, error) {
	payload, err := json.Marshal(body)
	if err != nil {
		return nil, err
	}
	resp, err := t.db.srv.raw.QueryTimeSeriesWithBody(ctx, t.db.name,
		&generated.QueryTimeSeriesParams{ArcadedbSessionId: t.db.sessionParam()}, "application/json", bytes.NewReader(payload))
	return decodeMap(resp, err)
}

// Latest returns the most recent sample per series, as the parsed JSON body. "latest" is
// null for an empty series. tag is one name:value filter, omitted when ""; a tag with no
// ':' or whose name is no TAG column of the type is refused with a 400 rather than ignored.
// See TimeSeries for why it bypasses the typed parser.
func (t *TimeSeries) Latest(ctx context.Context, typ, tag string) (map[string]any, error) {
	params := &generated.GetTimeSeriesLatestParams{Type: typ, ArcadedbSessionId: t.db.sessionParam()}
	if tag != "" {
		params.Tag = &[]string{tag}
	}
	resp, err := t.db.srv.raw.GetTimeSeriesLatest(ctx, t.db.name, params)
	return decodeMap(resp, err)
}
