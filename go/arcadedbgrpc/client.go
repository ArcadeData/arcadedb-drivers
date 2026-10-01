package arcadedbgrpc

import (
	"errors"
	"fmt"
	"strings"
	"sync"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc/generated"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"
)

type config struct {
	auth     authMetadata
	authErr  error // a malformed auth option, reported by NewClient
	password bool  // auth carries a plaintext password (the #5048 guard keys on this)
	creds    credentials.TransportCredentials
	insecure bool
	dialOpts []grpc.DialOption
}

// Option configures NewClient.
type Option func(*config)

// WithPasswordAuth authenticates every call with x-arcade-user, x-arcade-password and,
// when database is non-empty, x-arcade-database metadata. The password travels as
// metadata, so NewClient refuses it over a plaintext connection unless WithInsecure is
// given (see ErrInsecureChannel). An empty user is an error from NewClient. It replaces
// any earlier WithPasswordAuth or WithBearerToken.
func WithPasswordAuth(user, password, database string) Option {
	return func(c *config) {
		c.auth = passwordMetadata(user, password, database)
		c.password = true
		c.authErr = nil
		if user == "" {
			c.authErr = errors.New("arcadedbgrpc: WithPasswordAuth: user is empty")
		}
	}
}

// WithBearerToken authenticates every call with "authorization: Bearer <token>" metadata.
// Unlike a password it is allowed over a plaintext connection without WithInsecure. An
// empty token is an error from NewClient. It replaces any earlier WithPasswordAuth or
// WithBearerToken.
func WithBearerToken(token string) Option {
	return func(c *config) {
		c.auth = bearerMetadata(token)
		c.password = false
		c.authErr = nil
		if token == "" {
			c.authErr = errors.New("arcadedbgrpc: WithBearerToken: token is empty")
		}
	}
}

// WithTransportCredentials secures the connection with creds, for example
// credentials.NewTLS(cfg). It satisfies both guards: password auth is allowed and
// RawAdmin is available. Pass TLS through this option, not WithDialOptions: the guards
// cannot see credentials inside WithDialOptions. These credentials are applied after the
// dial options, so when both set transport credentials, these are the ones used.
func WithTransportCredentials(creds credentials.TransportCredentials) Option {
	return func(c *config) { c.creds = creds }
}

// WithInsecure is the single explicit opt-in to a plaintext connection carrying
// credentials. It satisfies both guards: WithPasswordAuth is allowed without transport
// credentials (#5048), and RawAdmin is available. Without it, and without
// WithTransportCredentials, the connection is still plaintext (insecure.NewCredentials),
// but only bearer-token and unauthenticated data-plane calls are permitted.
func WithInsecure() Option {
	return func(c *config) { c.insecure = true }
}

// WithDialOptions passes extra options to grpc.NewClient, for anything this package has no
// option of its own for (keepalive, a custom dialer, message size limits). Repeated uses
// accumulate.
//
// Pass TLS through WithTransportCredentials; the guards cannot see credentials inside
// WithDialOptions. A grpc.WithTransportCredentials given here is still honoured, never
// downgraded: the package's plaintext default is applied before these options, so it only
// takes effect when nothing here overrides it. The guards stay conservative in that case:
// they see no transport credentials, so WithPasswordAuth and RawAdmin still need
// WithInsecure (or WithTransportCredentials) and otherwise fail closed.
func WithDialOptions(opts ...grpc.DialOption) Option {
	return func(c *config) { c.dialOpts = append(c.dialOpts, opts...) }
}

// Client is a client for one ArcadeDB gRPC endpoint. It is safe for concurrent use.
type Client struct {
	conn       *grpc.ClientConn
	raw        generated.ArcadeDbServiceClient
	admin      generated.ArcadeDbAdminServiceClient
	allowAdmin bool
	closeMu    sync.Mutex
	closed     bool
}

// NewClient builds a Client for target, in grpc-go's native target form: "host:port",
// or a resolver-prefixed name such as "dns:///host:port", "passthrough:///host:port" or
// "unix:/path". It is not a URL: an http:// or https:// target is rejected, since
// grpc-go would otherwise read the scheme as an unknown resolver name. Like grpc.NewClient
// it performs no I/O; the connection is made on the first call.
//
// Without WithTransportCredentials the connection uses insecure.NewCredentials(). Combining
// WithPasswordAuth with a plaintext connection returns ErrInsecureChannel unless
// WithInsecure is given (ArcadeData/arcadedb#5048): the password would cross the wire in
// cleartext metadata. A bearer token over plaintext is allowed. The check keys on whether
// transport credentials were stated, never on inspecting the target.
//
// There is no default timeout; bound each call with its ctx.
func NewClient(target string, opts ...Option) (*Client, error) {
	if t := strings.ToLower(strings.TrimSpace(target)); strings.HasPrefix(t, "http://") || strings.HasPrefix(t, "https://") {
		return nil, fmt.Errorf("arcadedbgrpc: target %q is a URL; NewClient takes grpc-go's host:port form, e.g. \"localhost:50051\"", target)
	}

	cfg := &config{}
	for _, o := range opts {
		o(cfg)
	}
	if cfg.authErr != nil {
		return nil, cfg.authErr
	}
	if cfg.password && cfg.creds == nil && !cfg.insecure {
		return nil, fmt.Errorf("%w: NewClient would send a plaintext password to %q; pass WithTransportCredentials(creds), "+
			"switch to WithBearerToken, or pass WithInsecure() to opt in explicitly (ArcadeData/arcadedb#5048)",
			ErrInsecureChannel, target)
	}

	// grpc.WithTransportCredentials is last-wins. The implicit plaintext default goes
	// BEFORE the caller's dial options, so TLS supplied there is never silently replaced by
	// plaintext; explicit WithTransportCredentials goes AFTER them.
	dialOpts := []grpc.DialOption{grpc.WithTransportCredentials(insecure.NewCredentials())}
	dialOpts = append(dialOpts, cfg.dialOpts...)
	if cfg.creds != nil {
		dialOpts = append(dialOpts, grpc.WithTransportCredentials(cfg.creds))
	}
	if cfg.auth != nil {
		dialOpts = append(dialOpts,
			grpc.WithChainUnaryInterceptor(cfg.auth.unaryInterceptor()),
			grpc.WithChainStreamInterceptor(cfg.auth.streamInterceptor()))
	}

	conn, err := grpc.NewClient(target, dialOpts...)
	if err != nil {
		return nil, err
	}
	return &Client{
		conn:       conn,
		raw:        generated.NewArcadeDbServiceClient(conn),
		admin:      generated.NewArcadeDbAdminServiceClient(conn),
		allowAdmin: cfg.creds != nil || cfg.insecure,
	}, nil
}

// Raw returns the generated ArcadeDbService client. Every RPC the facade does not wrap is
// reached through it, already authenticated by the connection's interceptors.
func (c *Client) Raw() generated.ArcadeDbServiceClient { return c.raw }

// RawAdmin returns the generated ArcadeDbAdminService client, or ErrInsecureChannel unless
// the client was built with WithTransportCredentials or WithInsecure.
//
// The guard is unconditional on auth. 42 of the 44 admin RPCs authenticate from a
// DatabaseCredentials field inside the request message, not from the connection's auth
// interceptor, so those credentials would cross a plaintext connection whatever
// WithPasswordAuth or WithBearerToken says, and the #5048 check in NewClient cannot see
// them. It covers Health and Ready too, although they carry no credentials: the guard
// protects the client as a whole, and carving out two RPCs would mean wrapping the other
// 42. Python raises when its raw_admin property is read; Go returns an error, its idiom for
// a recoverable refusal. The check runs here rather than in NewClient, so a plaintext
// client keeps working for the data plane.
func (c *Client) RawAdmin() (generated.ArcadeDbAdminServiceClient, error) {
	if !c.allowAdmin {
		return nil, fmt.Errorf("%w: RawAdmin: refusing to expose ArcadeDbAdminService over a connection that may be plaintext. "+
			"42 of its 44 RPCs (everything but Health and Ready) carry DatabaseCredentials in the request body, "+
			"which would travel in cleartext regardless of any auth option. Pass WithTransportCredentials(creds) "+
			"or WithInsecure() to NewClient", ErrInsecureChannel)
	}
	return c.admin, nil
}

// Close closes the connection. It is safe to call more than once: the first call returns
// whatever grpc.ClientConn.Close returned, later calls return nil rather than grpc-go's
// "the client connection is closing" error.
func (c *Client) Close() error {
	c.closeMu.Lock()
	defer c.closeMu.Unlock()
	if c.closed {
		return nil
	}
	c.closed = true
	return c.conn.Close()
}
