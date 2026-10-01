package e2e

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"testing"
	"time"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb"
	"github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc"
	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/wait"
)

var (
	// grpcBaseURL is the gRPC container's HTTP address, used for DDL and for minting a
	// bearer token; no data-plane RPC creates a database.
	grpcBaseURL string
	// grpcTarget is the gRPC container's host:port for the data-plane service.
	grpcTarget string
)

// startGrpcContainer starts an ArcadeDB container with the GRPC plugin enabled and sets
// grpcBaseURL and grpcTarget. It returns the container even when it fails after starting,
// so the caller can terminate it.
//
// Two facts that are easy to get wrong: the GRPC plugin is not enabled by default (without
// the plugins property nothing listens on 50051), and the root password must be at least 8
// characters or the whole server refuses to start, which reads as "gRPC is broken".
func startGrpcContainer(ctx context.Context, image string) (testcontainers.Container, error) {
	ctr, err := testcontainers.GenericContainer(ctx, testcontainers.GenericContainerRequest{
		ContainerRequest: testcontainers.ContainerRequest{
			Image:        image,
			ExposedPorts: []string{"2480/tcp", "50051/tcp"},
			Env: map[string]string{
				"JAVA_OPTS": "-Darcadedb.server.rootPassword=" + rootPassword +
					" -Darcadedb.server.plugins=GRPC:com.arcadedb.server.grpc.GrpcServerPlugin",
			},
			// The log line appears only once the plugin is actually listening, so it is the
			// signal, not the open TCP port.
			WaitingFor: wait.ForAll(
				wait.ForHTTP("/api/v1/ready").WithPort("2480/tcp").
					WithStatusCodeMatcher(func(s int) bool { return s == 204 }),
				wait.ForLog("gRPC server started on 0.0.0.0:50051"),
			).WithDeadline(90 * time.Second),
		},
		Started: true,
	})
	if err != nil {
		return ctr, err
	}
	host, err := ctr.Host(ctx)
	if err != nil {
		return ctr, err
	}
	httpPort, err := ctr.MappedPort(ctx, "2480/tcp")
	if err != nil {
		return ctr, err
	}
	grpcPort, err := ctr.MappedPort(ctx, "50051/tcp")
	if err != nil {
		return ctr, err
	}
	grpcBaseURL = fmt.Sprintf("http://%s:%s", host, httpPort.Port())
	grpcTarget = fmt.Sprintf("%s:%s", host, grpcPort.Port())
	return ctr, nil
}

// newGrpcClient returns a client authenticated as root against db, over plaintext (the
// container speaks no TLS, so the insecure guard has to be opted out of explicitly).
func newGrpcClient(t *testing.T, db string, opts ...arcadedbgrpc.Option) *arcadedbgrpc.Client {
	t.Helper()
	all := append([]arcadedbgrpc.Option{
		arcadedbgrpc.WithPasswordAuth("root", rootPassword, db),
		arcadedbgrpc.WithInsecure(),
	}, opts...)
	c, err := arcadedbgrpc.NewClient(grpcTarget, all...)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = c.Close() })
	return c
}

// Index names are ArcadeDB's Type[property] form for an unnamed index.
const (
	vectorIndexName   = "VectorItem[embedding]"
	fulltextIndexName = "VectorItem[description]"
	grpcTsType        = "GrpcTsPoint"
)

// newGrpcDatabase creates a uniquely named database in the gRPC container over HTTP and
// gives it the Person, VectorItem (LSM_VECTOR dimension 4 plus FULL_TEXT, three rows) and
// GrpcTsPoint schema.
//
// The DDL was worked out against a live server for the Python suite: embedding must be
// ARRAY_OF_FLOATS, CREATE INDEX ... LSM_VECTOR refuses to run without METADATA naming
// dimensions, and a TIMESERIES type's tag and field columns must be named inline in
// CREATE TIMESERIES TYPE (a later CREATE PROPERTY adds a column no write ever populates).
// red-apple's embedding is the query vector every vector test searches for, so it is
// always the nearest neighbour at distance 0.
func newGrpcDatabase(t *testing.T) string {
	t.Helper()
	srv, err := arcadedb.NewServer(grpcBaseURL, arcadedb.WithBasicAuth("root", rootPassword))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = srv.Close() })
	name := fmt.Sprintf("grpc%d", dbCounter.Add(1))
	// Create-database goes through the plain generated operation for the reason newDatabase
	// documents: the typed decoder mis-models the {"result":"ok"} answer.
	resp, err := srv.Raw().ExecuteServerCommandWithBody(context.Background(), nil, "application/json",
		jsonBody(t, map[string]string{"command": "create database " + name, "language": "sql"}))
	if err != nil {
		t.Fatal(err)
	}
	_ = resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("create database %s: status %d", name, resp.StatusCode)
	}
	db := srv.DB(name)
	for _, sql := range []string{
		"CREATE VERTEX TYPE Person IF NOT EXISTS",
		"CREATE DOCUMENT TYPE VectorItem IF NOT EXISTS",
		"CREATE PROPERTY VectorItem.name STRING",
		"CREATE PROPERTY VectorItem.embedding ARRAY_OF_FLOATS",
		"CREATE PROPERTY VectorItem.description STRING",
		`CREATE INDEX ON VectorItem (embedding) LSM_VECTOR METADATA {"dimensions": 4}`,
		"INSERT INTO VectorItem SET name = 'red-apple', embedding = [1,0,0,0], description = 'a bright red apple'",
		"INSERT INTO VectorItem SET name = 'green-apple', embedding = [0.9,0.1,0,0], description = 'a crisp green apple'",
		"INSERT INTO VectorItem SET name = 'blue-car', embedding = [0,0,1,0], description = 'a fast blue car engine'",
		"CREATE INDEX ON VectorItem (description) FULL_TEXT",
		"CREATE TIMESERIES TYPE " + grpcTsType + " TIMESTAMP ts TAGS (sensor STRING) FIELDS (value DOUBLE)",
	} {
		mustCommand(t, db, sql)
	}
	return name
}

func jsonBody(t *testing.T, v any) io.Reader {
	t.Helper()
	b, err := json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	return bytes.NewReader(b)
}
