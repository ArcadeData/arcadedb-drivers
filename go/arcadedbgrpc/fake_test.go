package arcadedbgrpc

import (
	"context"
	"errors"
	"io"
	"net"
	"strings"
	"sync"
	"testing"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc/generated"
	"google.golang.org/grpc"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/test/bufconn"
)

// fakeTarget is the target every bufconn-backed client dials. The passthrough resolver
// hands the name straight to the context dialer, which ignores it and dials the listener.
const fakeTarget = "passthrough:///bufnet"

// mdRecorder captures the incoming metadata of every call the fake server receives, keyed
// by the full method name. It is filled by server interceptors, so it records calls to
// every RPC whatever service implementation the test supplied.
type mdRecorder struct {
	mu    sync.Mutex
	calls map[string][]metadata.MD
}

func (r *mdRecorder) record(ctx context.Context, fullMethod string) {
	md, _ := metadata.FromIncomingContext(ctx)
	r.mu.Lock()
	defer r.mu.Unlock()
	r.calls[fullMethod] = append(r.calls[fullMethod], md.Copy())
}

// last returns the metadata of the most recent call to the RPC named method (its short
// name, e.g. "ExecuteQuery"), or fails the test if there was none.
func (r *mdRecorder) last(t *testing.T, method string) metadata.MD {
	t.Helper()
	r.mu.Lock()
	defer r.mu.Unlock()
	for full, mds := range r.calls {
		if strings.HasSuffix(full, "/"+method) && len(mds) > 0 {
			return mds[len(mds)-1]
		}
	}
	t.Fatalf("no call to %s was recorded", method)
	return nil
}

// newFake starts an in-process server on a bufconn listener, registers svc and admin
// (a nil one is replaced by the generated Unimplemented server), and returns a Client
// dialled to it. WithInsecure is added unless opts already choose WithInsecure or
// WithTransportCredentials. t.Cleanup closes the client and stops the server.
func newFake(t *testing.T, svc generated.ArcadeDbServiceServer, admin generated.ArcadeDbAdminServiceServer, opts ...Option) *Client {
	t.Helper()
	c, _ := newRecordingFake(t, svc, admin, opts...)
	return c
}

// newRecordingFake is newFake that also returns the recorder of incoming metadata.
func newRecordingFake(t *testing.T, svc generated.ArcadeDbServiceServer, admin generated.ArcadeDbAdminServiceServer, opts ...Option) (*Client, *mdRecorder) {
	t.Helper()
	if svc == nil {
		svc = generated.UnimplementedArcadeDbServiceServer{}
	}
	if admin == nil {
		admin = generated.UnimplementedArcadeDbAdminServiceServer{}
	}
	rec := &mdRecorder{calls: map[string][]metadata.MD{}}
	lis := bufconn.Listen(1 << 20)
	srv := grpc.NewServer(
		grpc.ChainUnaryInterceptor(func(ctx context.Context, req any, info *grpc.UnaryServerInfo, h grpc.UnaryHandler) (any, error) {
			rec.record(ctx, info.FullMethod)
			return h(ctx, req)
		}),
		grpc.ChainStreamInterceptor(func(s any, ss grpc.ServerStream, info *grpc.StreamServerInfo, h grpc.StreamHandler) error {
			rec.record(ss.Context(), info.FullMethod)
			return h(s, ss)
		}),
	)
	generated.RegisterArcadeDbServiceServer(srv, svc)
	generated.RegisterArcadeDbAdminServiceServer(srv, admin)
	go func() { _ = srv.Serve(lis) }()

	probe := &config{}
	for _, o := range opts {
		o(probe)
	}
	all := []Option{WithDialOptions(grpc.WithContextDialer(func(ctx context.Context, _ string) (net.Conn, error) {
		return lis.DialContext(ctx)
	}))}
	if probe.creds == nil && !probe.insecure {
		all = append(all, WithInsecure())
	}
	all = append(all, opts...)

	c, err := NewClient(fakeTarget, all...)
	if err != nil {
		srv.Stop()
		t.Fatalf("NewClient: %v", err)
	}
	t.Cleanup(func() {
		_ = c.Close()
		srv.Stop()
	})
	return c, rec
}

// recordingService answers the four call shapes the auth tests exercise with empty
// replies. Tests that need other behaviour embed generated.UnimplementedArcadeDbServiceServer
// (or this type) and override individual methods.
type recordingService struct {
	generated.UnimplementedArcadeDbServiceServer
}

func (recordingService) ExecuteQuery(context.Context, *generated.ExecuteQueryRequest) (*generated.ExecuteQueryResponse, error) {
	return &generated.ExecuteQueryResponse{}, nil
}

func (recordingService) StreamQuery(_ *generated.StreamQueryRequest, s grpc.ServerStreamingServer[generated.QueryResult]) error {
	return s.Send(&generated.QueryResult{})
}

func (recordingService) InsertStream(s grpc.ClientStreamingServer[generated.InsertChunk, generated.InsertSummary]) error {
	for {
		if _, err := s.Recv(); err != nil {
			if errors.Is(err, io.EOF) {
				return s.SendAndClose(&generated.InsertSummary{})
			}
			return err
		}
	}
}

func (recordingService) InsertBidirectional(s grpc.BidiStreamingServer[generated.InsertRequest, generated.InsertResponse]) error {
	for {
		if _, err := s.Recv(); err != nil {
			if errors.Is(err, io.EOF) {
				return nil
			}
			return err
		}
	}
}

// healthAdmin answers Health, so tests can prove an admin call goes through.
type healthAdmin struct {
	generated.UnimplementedArcadeDbAdminServiceServer
}

func (healthAdmin) Health(context.Context, *generated.HealthRequest) (*generated.HealthResponse, error) {
	return &generated.HealthResponse{}, nil
}
