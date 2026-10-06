// Package e2e runs the Go client against a real ArcadeDB container. Requires Docker.
package e2e

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"sync/atomic"
	"testing"
	"time"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb"
	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/wait"
)

// defaultImage is the release the committed OpenAPI contract was generated from, so the
// client under test and the server it runs against are the same version. It is a literal so
// adopt-contract-version.sh can rewrite it when the contract moves.
const defaultImage = "arcadedata/arcadedb:26.11.1-SNAPSHOT"

const rootPassword = "playwithdata"

// baseURL is the running container's HTTP address, set by TestMain.
var baseURL string

// dbCounter makes every test's database name unique within the one shared container.
var dbCounter atomic.Int64

func TestMain(m *testing.M) {
	os.Exit(run(m))
}

func run(m *testing.M) int {
	// ARCADEDB_DOCKER_IMAGE overrides the pin, for the smoke job in ArcadeData/arcadedb that
	// runs against an image built from the server commit under review.
	image := os.Getenv("ARCADEDB_DOCKER_IMAGE")
	if image == "" {
		image = defaultImage
	}
	ctx := context.Background()
	ctr, err := testcontainers.GenericContainer(ctx, testcontainers.GenericContainerRequest{
		ContainerRequest: testcontainers.ContainerRequest{
			Image:        image,
			ExposedPorts: []string{"2480/tcp"},
			Env: map[string]string{
				"JAVA_OPTS": "-Darcadedb.server.rootPassword=" + rootPassword,
			},
			WaitingFor: wait.ForHTTP("/api/v1/ready").WithPort("2480/tcp").
				WithStatusCodeMatcher(func(s int) bool { return s == 204 }).
				WithStartupTimeout(90 * time.Second),
		},
		Started: true,
	})
	if ctr != nil {
		defer func() { _ = testcontainers.TerminateContainer(ctr) }()
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "starting ArcadeDB container:", err)
		return 1
	}
	host, err := ctr.Host(ctx)
	if err != nil {
		fmt.Fprintln(os.Stderr, "container host:", err)
		return 1
	}
	port, err := ctr.MappedPort(ctx, "2480/tcp")
	if err != nil {
		fmt.Fprintln(os.Stderr, "container port:", err)
		return 1
	}
	baseURL = fmt.Sprintf("http://%s:%s", host, port.Port())

	// The gRPC container is separate from the HTTP one, so once both are up the two suites
	// share no server state. It is not isolation from startup failure: if the gRPC container
	// fails to start, TestMain returns 1 and no test runs, HTTP tests included. Its
	// termination is deferred here too, so both containers go down on every path, a setup
	// failure included.
	gctr, err := startGrpcContainer(ctx, image)
	if gctr != nil {
		defer func() { _ = testcontainers.TerminateContainer(gctr) }()
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "starting ArcadeDB gRPC container:", err)
		return 1
	}
	return m.Run()
}

func newServer(t *testing.T) *arcadedb.Server {
	t.Helper()
	srv, err := arcadedb.NewServer(baseURL, arcadedb.WithBasicAuth("root", rootPassword))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = srv.Close() })
	return srv
}

// newDatabase creates a uniquely named database and returns a handle to it.
//
// No dedicated create-database endpoint exists: creation goes through the generic
// server-command endpoint (POST /api/v1/server). It is issued through the plain generated
// operation, not the typed ExecuteServerCommandWithResponse, deliberately: the contract
// declares that endpoint's 200 body as QueryResponse (result: array), but the server answers
// an admin command with {"result":"ok"}, a string. The typed decoder would mis-model it, so
// the status is checked here and the body is not decoded.
func newDatabase(t *testing.T) *arcadedb.Database {
	t.Helper()
	srv := newServer(t)
	name := fmt.Sprintf("e2e%d", dbCounter.Add(1))
	payload, err := json.Marshal(map[string]string{"command": "create database " + name, "language": "sql"})
	if err != nil {
		t.Fatal(err)
	}
	resp, err := srv.Raw().ExecuteServerCommandWithBody(context.Background(), nil, "application/json", bytes.NewReader(payload))
	if err != nil {
		t.Fatal(err)
	}
	body, _ := io.ReadAll(resp.Body)
	_ = resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode > 299 {
		t.Fatalf("create database %s: status %d: %s", name, resp.StatusCode, body)
	}
	return srv.DB(name)
}

// mustCommand runs a SQL command and fails the test on error.
func mustCommand(t *testing.T, db *arcadedb.Database, sql string) {
	t.Helper()
	if _, err := db.Command(context.Background(), arcadedb.SQL, sql, nil); err != nil {
		t.Fatalf("%s: %v", sql, err)
	}
}
