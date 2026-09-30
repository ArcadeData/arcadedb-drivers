package arcadedb

import (
	"bytes"
	"context"
	"encoding/json"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

// Grafana is the Grafana data-source namespace of a Database. Obtain it with
// Database.Grafana.
//
// Query returns the whole JSON body as a map[string]any and does NOT route through the
// generated typed parser (it calls the plain generated Client and decodes the body
// itself). Do not route it back through the ...WithResponse method. The contract types the
// per-element DataFrame values as bare objects; in Go that generates interface{} and the
// values survive, so unlike the Python client the typed path does not crash. It is still
// bypassed so the whole family (TS().Query, TS().Latest, Grafana().Query) hands back one
// shape with nothing dropped or defaulted.
//
// A 200 can carry a per-target failure: check results[refId]["error"], which is set with an
// empty "frames" when a target is malformed (for example a missing target type).
type Grafana struct {
	db *Database
}

// Grafana returns the Grafana namespace. It performs no request.
func (d *Database) Grafana() *Grafana { return &Grafana{db: d} }

// Query runs a Grafana query request and returns the parsed JSON body unaltered.
func (g *Grafana) Query(ctx context.Context, body map[string]any) (map[string]any, error) {
	payload, err := json.Marshal(body)
	if err != nil {
		return nil, err
	}
	resp, err := g.db.srv.raw.QueryGrafanaWithBody(ctx, g.db.name,
		&generated.QueryGrafanaParams{ArcadedbSessionId: g.db.sessionParam()}, "application/json", bytes.NewReader(payload))
	return decodeMap(resp, err)
}
