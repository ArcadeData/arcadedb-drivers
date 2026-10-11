package arcadedb

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"

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
//
// A 400 whose body is a JSON object is a *TimeSeriesWriteError, carrying how many samples
// were written and dropped and why; errors.As matches it as *ArcadeDBError too. A write is
// not atomic: the samples it reports Written landed even though the call failed. Any other
// failure is a plain *ArcadeDBError.
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
	var body []byte
	if resp.Body != nil {
		body, _ = io.ReadAll(resp.Body)
		_ = resp.Body.Close()
	}
	if isSuccess(resp.StatusCode) {
		return nil
	}
	base := errorFromHeaders(resp.StatusCode, body, resp.Header)
	if resp.StatusCode != http.StatusBadRequest {
		return base
	}
	if tse := timeSeriesWriteError(base, body); tse != nil {
		return tse
	}
	return base
}

// timeSeriesWriteError wraps base with the counts and reason lists of a 400 body, or
// returns nil when the body is not a JSON object. Like newError it never fails: a count that
// is not a non-negative whole number reads 0, and a list element that is not a string is
// dropped.
func timeSeriesWriteError(base *ArcadeDBError, body []byte) *TimeSeriesWriteError {
	var parsed map[string]any
	if json.Unmarshal(body, &parsed) != nil || parsed == nil {
		return nil
	}
	strs := func(key string) []string {
		items, _ := parsed[key].([]any)
		var out []string
		for _, it := range items {
			if s, ok := it.(string); ok {
				out = append(out, s)
			}
		}
		return out
	}
	e := &TimeSeriesWriteError{
		ArcadeDBError:      base,
		UnknownTypes:       strs("unknownTypes"),
		NonTimeSeriesTypes: strs("nonTimeSeriesTypes"),
		UnavailableTypes:   strs("unavailableTypes"),
		UndeclaredKeys:     strs("undeclaredKeys"),
	}
	e.Written, _ = jsonNonNegative(parsed["written"])
	e.Dropped, _ = jsonNonNegative(parsed["dropped"])
	return e
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
