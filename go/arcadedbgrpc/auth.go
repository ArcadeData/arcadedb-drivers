package arcadedbgrpc

import (
	"context"

	"google.golang.org/grpc"
	"google.golang.org/grpc/metadata"
)

// Auth is applied by a pair of client interceptors on the connection, one unary and one
// stream, rather than by per-call metadata on the facade methods. That way every call made
// through Raw() and RawAdmin() is authenticated too, and most RPCs are reachable only there.
//
// grpc-go splits interceptors by call shape: the unary interceptor sees unary RPCs, the
// stream interceptor sees server-stream, client-stream and bidi RPCs alike. Installing only
// one of the two would leave whole call shapes silently anonymous, which is exactly the
// defect Python's async client once shipped (its streaming RPCs came back UNAUTHENTICATED
// against a real server). The unit tests drive all four shapes.
//
// grpc.PerRPCCredentials is deliberately not used: grpc-go refuses to send it over a
// connection without transport security unless the credentials opt out, and password auth
// over a plaintext connection (WithInsecure) is a configuration this client supports. It
// is the same reason Python avoids metadata_call_credentials.

// authMetadata is the flat key/value list auth appends to every call.
type authMetadata []string

// passwordMetadata sends x-arcade-user, x-arcade-password and, only when non-empty,
// x-arcade-database.
func passwordMetadata(user, password, database string) authMetadata {
	kv := authMetadata{"x-arcade-user", user, "x-arcade-password", password}
	if database != "" {
		kv = append(kv, "x-arcade-database", database)
	}
	return kv
}

// bearerMetadata sends authorization: Bearer <token>.
func bearerMetadata(token string) authMetadata {
	return authMetadata{"authorization", "Bearer " + token}
}

// outgoing APPENDS the auth pairs to ctx's outgoing metadata. It never replaces: metadata
// the caller set (a request id, even its own x-arcade-database) reaches the server
// alongside the auth pairs, and dropping it would be silent data loss.
func (kv authMetadata) outgoing(ctx context.Context) context.Context {
	return metadata.AppendToOutgoingContext(ctx, kv...)
}

func (kv authMetadata) unaryInterceptor() grpc.UnaryClientInterceptor {
	return func(ctx context.Context, method string, req, reply any, cc *grpc.ClientConn, invoker grpc.UnaryInvoker, opts ...grpc.CallOption) error {
		return invoker(kv.outgoing(ctx), method, req, reply, cc, opts...)
	}
}

func (kv authMetadata) streamInterceptor() grpc.StreamClientInterceptor {
	return func(ctx context.Context, desc *grpc.StreamDesc, cc *grpc.ClientConn, method string, streamer grpc.Streamer, opts ...grpc.CallOption) (grpc.ClientStream, error) {
		return streamer(kv.outgoing(ctx), desc, cc, method, opts...)
	}
}
