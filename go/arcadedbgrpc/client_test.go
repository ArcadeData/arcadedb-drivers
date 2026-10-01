package arcadedbgrpc

import (
	"context"
	"crypto/tls"
	"errors"
	"io"
	"slices"
	"strings"
	"testing"
	"time"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc/generated"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

func TestPasswordAuthOverPlaintextIsRefused(t *testing.T) {
	c, err := NewClient("localhost:50051", WithPasswordAuth("root", "pw", "db"))
	if c != nil {
		_ = c.Close()
	}
	if !errors.Is(err, ErrInsecureChannel) {
		t.Fatalf("err = %v, want ErrInsecureChannel", err)
	}
	for _, want := range []string{"WithInsecure", "WithTransportCredentials", "localhost:50051"} {
		if !strings.Contains(err.Error(), want) {
			t.Errorf("error %q does not mention %s", err, want)
		}
	}
}

func TestBearerOverPlaintextIsAllowed(t *testing.T) {
	c, err := NewClient("localhost:50051", WithBearerToken("tok"))
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	_ = c.Close()
}

func TestPasswordAuthWithInsecureIsAllowed(t *testing.T) {
	c := newFake(t, recordingService{}, nil, WithPasswordAuth("root", "pw", "db"), WithInsecure())
	if _, err := c.Raw().ExecuteQuery(context.Background(), &generated.ExecuteQueryRequest{}); err != nil {
		t.Fatalf("ExecuteQuery: %v", err)
	}
}

// drive makes one call of each of the four shapes through Raw().
func drive(t *testing.T, ctx context.Context, c *Client) {
	t.Helper()
	if _, err := c.Raw().ExecuteQuery(ctx, &generated.ExecuteQueryRequest{}); err != nil {
		t.Fatalf("ExecuteQuery: %v", err)
	}

	ss, err := c.Raw().StreamQuery(ctx, &generated.StreamQueryRequest{})
	if err != nil {
		t.Fatalf("StreamQuery: %v", err)
	}
	for {
		if _, err := ss.Recv(); err != nil {
			if !errors.Is(err, io.EOF) {
				t.Fatalf("StreamQuery Recv: %v", err)
			}
			break
		}
	}

	cs, err := c.Raw().InsertStream(ctx)
	if err != nil {
		t.Fatalf("InsertStream: %v", err)
	}
	if err := cs.Send(&generated.InsertChunk{}); err != nil {
		t.Fatalf("InsertStream Send: %v", err)
	}
	if _, err := cs.CloseAndRecv(); err != nil {
		t.Fatalf("InsertStream CloseAndRecv: %v", err)
	}

	bs, err := c.Raw().InsertBidirectional(ctx)
	if err != nil {
		t.Fatalf("InsertBidirectional: %v", err)
	}
	if err := bs.Send(&generated.InsertRequest{}); err != nil {
		t.Fatalf("InsertBidirectional Send: %v", err)
	}
	if err := bs.CloseSend(); err != nil {
		t.Fatalf("InsertBidirectional CloseSend: %v", err)
	}
	if _, err := bs.Recv(); !errors.Is(err, io.EOF) {
		t.Fatalf("InsertBidirectional Recv: %v, want io.EOF", err)
	}
}

var callShapes = []string{"ExecuteQuery", "StreamQuery", "InsertStream", "InsertBidirectional"}

func TestAuthMetadataOnEveryCallShape(t *testing.T) {
	c, rec := newRecordingFake(t, recordingService{}, nil, WithPasswordAuth("root", "pw", "mydb"))
	drive(t, context.Background(), c)
	for _, m := range callShapes {
		md := rec.last(t, m)
		for key, want := range map[string]string{"x-arcade-user": "root", "x-arcade-password": "pw", "x-arcade-database": "mydb"} {
			if got := md.Get(key); !slices.Equal(got, []string{want}) {
				t.Errorf("%s: %s = %q, want [%q]", m, key, got, want)
			}
		}
	}
}

func TestPasswordAuthOmitsEmptyDatabase(t *testing.T) {
	c, rec := newRecordingFake(t, recordingService{}, nil, WithPasswordAuth("root", "pw", ""))
	drive(t, context.Background(), c)
	for _, m := range callShapes {
		md := rec.last(t, m)
		if got := md.Get("x-arcade-database"); got != nil {
			t.Errorf("%s: x-arcade-database = %q, want absent", m, got)
		}
		if got := md.Get("x-arcade-user"); !slices.Equal(got, []string{"root"}) {
			t.Errorf("%s: x-arcade-user = %q", m, got)
		}
	}
}

func TestBearerAuthHeader(t *testing.T) {
	c, rec := newRecordingFake(t, recordingService{}, nil, WithBearerToken("tok"))
	drive(t, context.Background(), c)
	for _, m := range callShapes {
		md := rec.last(t, m)
		if got := md.Get("authorization"); !slices.Equal(got, []string{"Bearer tok"}) {
			t.Errorf("%s: authorization = %q, want [\"Bearer tok\"]", m, got)
		}
		if got := md.Get("x-arcade-user"); got != nil {
			t.Errorf("%s: x-arcade-user = %q, want absent under bearer auth", m, got)
		}
	}
}

func TestAuthAppendsToCallerMetadata(t *testing.T) {
	c, rec := newRecordingFake(t, recordingService{}, nil, WithPasswordAuth("root", "pw", "mydb"))
	ctx := metadata.AppendToOutgoingContext(context.Background(), "x-request-id", "r1", "x-arcade-database", "other")
	drive(t, ctx, c)
	for _, m := range callShapes {
		md := rec.last(t, m)
		if got := md.Get("x-request-id"); !slices.Equal(got, []string{"r1"}) {
			t.Errorf("%s: x-request-id = %q, want [r1]", m, got)
		}
		got := md.Get("x-arcade-database")
		if !slices.Contains(got, "other") || !slices.Contains(got, "mydb") || len(got) != 2 {
			t.Errorf("%s: x-arcade-database = %q, want both \"other\" and \"mydb\"", m, got)
		}
		if got := md.Get("x-arcade-password"); !slices.Equal(got, []string{"pw"}) {
			t.Errorf("%s: x-arcade-password = %q, want [pw]", m, got)
		}
	}
}

func TestRawAdminRefusedWithoutTLSOrInsecure(t *testing.T) {
	c, err := NewClient("localhost:50051", WithBearerToken("tok"))
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	defer func() { _ = c.Close() }()
	admin, err := c.RawAdmin()
	if !errors.Is(err, ErrInsecureChannel) {
		t.Fatalf("RawAdmin err = %v, want ErrInsecureChannel", err)
	}
	if admin != nil {
		t.Errorf("RawAdmin returned a client alongside its error")
	}
	for _, want := range []string{"WithInsecure", "WithTransportCredentials", "Health and Ready"} {
		if !strings.Contains(err.Error(), want) {
			t.Errorf("error %q does not mention %s", err, want)
		}
	}
}

func TestRawAdminRefusedWithoutAuth(t *testing.T) {
	c, err := NewClient("localhost:50051")
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	defer func() { _ = c.Close() }()
	if _, err := c.RawAdmin(); !errors.Is(err, ErrInsecureChannel) {
		t.Fatalf("RawAdmin err = %v, want ErrInsecureChannel even with no auth configured", err)
	}
}

func TestRawAdminAllowedWithInsecure(t *testing.T) {
	c, rec := newRecordingFake(t, nil, healthAdmin{}, WithBearerToken("tok"), WithInsecure())
	admin, err := c.RawAdmin()
	if err != nil {
		t.Fatalf("RawAdmin: %v", err)
	}
	if _, err := admin.Health(context.Background(), &generated.HealthRequest{}); err != nil {
		t.Fatalf("Health: %v", err)
	}
	if got := rec.last(t, "Health").Get("authorization"); !slices.Equal(got, []string{"Bearer tok"}) {
		t.Errorf("Health: authorization = %q, want the interceptor to cover admin calls too", got)
	}
}

func TestRawAdminAllowedWithTransportCredentials(t *testing.T) {
	c, err := NewClient("passthrough:///h:1", WithPasswordAuth("root", "pw", ""),
		WithTransportCredentials(credentials.NewTLS(&tls.Config{})))
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	defer func() { _ = c.Close() }()
	if _, err := c.RawAdmin(); err != nil {
		t.Fatalf("RawAdmin: %v", err)
	}
}

func TestCloseTwiceIsSafe(t *testing.T) {
	c, err := NewClient("localhost:50051")
	if err != nil {
		t.Fatalf("NewClient: %v", err)
	}
	if err := c.Close(); err != nil {
		t.Fatalf("first Close: %v", err)
	}
	if err := c.Close(); err != nil {
		t.Fatalf("second Close: %v", err)
	}
}

func TestNewClientRejectsURLTarget(t *testing.T) {
	for _, target := range []string{"http://localhost:50051", "https://h:1", "HTTPS://h:1", " HTTP://h:1"} {
		c, err := NewClient(target, WithInsecure())
		if err == nil {
			_ = c.Close()
			t.Errorf("NewClient(%q) succeeded, want an error", target)
			continue
		}
		if !strings.Contains(err.Error(), "host:port") {
			t.Errorf("NewClient(%q) error %q does not mention host:port", target, err)
		}
	}
	for _, target := range []string{
		"dns:///h:1", "passthrough:///h:1", "h:1", "unix:/tmp/arcadedb.sock",
		"http:50051", // a host literally named "http" is not a URL
		"[::1]:50051", "dns:///[::1]:50051",
	} {
		c, err := NewClient(target, WithInsecure())
		if err != nil {
			t.Errorf("NewClient(%q): %v", target, err)
			continue
		}
		_ = c.Close()
	}
}

// A caller who supplies TLS only through WithDialOptions must never have it silently
// replaced by the package's plaintext default: the RPC against the plaintext fake has to
// fail the handshake, not succeed in cleartext.
func TestDialOptionTLSIsNeverDowngraded(t *testing.T) {
	tlsCreds := credentials.NewTLS(&tls.Config{InsecureSkipVerify: true})
	c := newFake(t, recordingService{}, nil, WithBearerToken("tok"),
		WithDialOptions(grpc.WithTransportCredentials(tlsCreds)))
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_, err := c.Raw().ExecuteQuery(ctx, &generated.ExecuteQueryRequest{})
	if err == nil {
		t.Fatal("ExecuteQuery succeeded over plaintext; the caller's TLS dial option was downgraded")
	}
	if status.Code(err) != codes.Unavailable {
		t.Fatalf("ExecuteQuery err = %v, want Unavailable (a failed TLS handshake)", err)
	}
}

func TestEmptyCredentialsAreRejected(t *testing.T) {
	for name, opt := range map[string]Option{
		"empty bearer token": WithBearerToken(""),
		"empty user":         WithPasswordAuth("", "pw", "db"),
	} {
		c, err := NewClient("localhost:50051", opt, WithInsecure())
		if err == nil {
			_ = c.Close()
			t.Errorf("%s: NewClient succeeded, want an error", name)
		}
	}
}
