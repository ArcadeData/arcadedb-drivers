package arcadedb

import (
	"context"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

// PromQL is the Prometheus-compatible query namespace of a Database. Obtain it with
// Database.PromQL.
//
// Unlike TS and Grafana these methods use the generated typed models: the PromQL response
// schemas carry no bare-object scalars, and a sample's value is already a string on the
// wire. Each method takes the generated params struct and returns the whole generated
// response. A params struct whose ArcadedbSessionId is nil gets the Database's session id,
// so a call inside a Transaction joins it; one the caller set is left alone.
//
// PromQLDataResponse.Data.Result is a union: read it according to Data.ResultType
// ("vector", "matrix" or "scalar").
type PromQL struct {
	db *Database
}

// PromQL returns the PromQL namespace. It performs no request.
func (d *Database) PromQL() *PromQL { return &PromQL{db: d} }

func (p *PromQL) session(own *string) *string {
	if own != nil {
		return own
	}
	return p.db.sessionParam()
}

// Query evaluates an instant query. Time defaults to now server-side.
func (p *PromQL) Query(ctx context.Context, params generated.PromQLQueryParams) (*generated.PromQLDataResponse, error) {
	params.ArcadedbSessionId = p.session(params.ArcadedbSessionId)
	resp, err := p.db.srv.raw.PromQLQueryWithResponse(ctx, p.db.name, &params)
	if err != nil {
		return nil, err
	}
	if err := checkResponse(resp.HTTPResponse, resp.Body); err != nil {
		return nil, err
	}
	return nonEmpty(decodeBody(resp.JSON200, resp.Body))
}

// QueryRange evaluates a query over a range. Start and End are Unix seconds and Step is a
// number of seconds or a duration such as "1m", all as strings.
func (p *PromQL) QueryRange(ctx context.Context, params generated.PromQLQueryRangeParams) (*generated.PromQLDataResponse, error) {
	params.ArcadedbSessionId = p.session(params.ArcadedbSessionId)
	resp, err := p.db.srv.raw.PromQLQueryRangeWithResponse(ctx, p.db.name, &params)
	if err != nil {
		return nil, err
	}
	if err := checkResponse(resp.HTTPResponse, resp.Body); err != nil {
		return nil, err
	}
	return nonEmpty(decodeBody(resp.JSON200, resp.Body))
}

// Labels lists the label names.
func (p *PromQL) Labels(ctx context.Context) (*generated.PromQLLabelsResponse, error) {
	resp, err := p.db.srv.raw.PromQLLabelsWithResponse(ctx, p.db.name,
		&generated.PromQLLabelsParams{ArcadedbSessionId: p.db.sessionParam()})
	if err != nil {
		return nil, err
	}
	if err := checkResponse(resp.HTTPResponse, resp.Body); err != nil {
		return nil, err
	}
	return nonEmpty(decodeBody(resp.JSON200, resp.Body))
}

// Series lists the series matching every selector in params.Match, which is sent as the
// repeated "match[]" parameter; the results are unioned.
func (p *PromQL) Series(ctx context.Context, params generated.PromQLSeriesParams) (*generated.PromQLSeriesResponse, error) {
	params.ArcadedbSessionId = p.session(params.ArcadedbSessionId)
	resp, err := p.db.srv.raw.PromQLSeriesWithResponse(ctx, p.db.name, &params)
	if err != nil {
		return nil, err
	}
	if err := checkResponse(resp.HTTPResponse, resp.Body); err != nil {
		return nil, err
	}
	return nonEmpty(decodeBody(resp.JSON200, resp.Body))
}
