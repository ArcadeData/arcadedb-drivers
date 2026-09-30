package arcadedb

import (
	"context"
	"net/http"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

type config struct {
	headers map[string]string
	client  *http.Client
}

// Option configures NewServer.
type Option func(*config)

// WithBasicAuth authenticates every request with HTTP Basic credentials.
func WithBasicAuth(user, password string) Option {
	return func(c *config) { c.headers[http.CanonicalHeaderKey("Authorization")] = basicAuthValue(user, password) }
}

// WithBearerToken authenticates every request with a bearer token.
func WithBearerToken(token string) Option {
	return func(c *config) { c.headers[http.CanonicalHeaderKey("Authorization")] = bearerAuthValue(token) }
}

// WithHeader adds a header to every request, overriding any built-in one of that name.
func WithHeader(name, value string) Option {
	return func(c *config) { c.headers[http.CanonicalHeaderKey(name)] = value }
}

// WithHTTPClient replaces the default http.Client; nil falls back to the default. The default has no timeout on purpose:
// deadlines belong to the context each call takes.
func WithHTTPClient(hc *http.Client) Option {
	return func(c *config) { c.client = hc }
}

// Server is a client for one ArcadeDB server. It is safe for concurrent use.
type Server struct {
	raw    *generated.ClientWithResponses
	client *http.Client
}

// NewServer builds a Server for baseURL. Every request carries the configured auth
// header, extra headers and "User-Agent: arcadedb-go/<Version>".
func NewServer(baseURL string, opts ...Option) (*Server, error) {
	cfg := &config{headers: map[string]string{"User-Agent": "arcadedb-go/" + Version}}
	for _, o := range opts {
		o(cfg)
	}
	if cfg.client == nil {
		cfg.client = &http.Client{}
	}
	raw, err := generated.NewClientWithResponses(baseURL,
		generated.WithHTTPClient(cfg.client),
		generated.WithRequestEditorFn(func(_ context.Context, req *http.Request) error {
			applyHeaders(req.Header, cfg.headers)
			return nil
		}),
	)
	if err != nil {
		return nil, err
	}
	return &Server{raw: raw, client: cfg.client}, nil
}

// DB returns a handle on the named database. It performs no request.
func (s *Server) DB(name string) *Database { return &Database{srv: s, name: name} }

// Raw returns the generated client. Unlike every facade method it never returns an error
// for a non-2xx status; inspect the response instead.
func (s *Server) Raw() *generated.ClientWithResponses { return s.raw }

// Close releases idle connections held by the underlying http.Client. It calls
// CloseIdleConnections on a caller-supplied client too, which may be shared.
func (s *Server) Close() error {
	s.client.CloseIdleConnections()
	return nil
}

// ListDatabases returns the databases the caller is authorized on. A missing result is an
// empty, non-nil slice.
func (s *Server) ListDatabases(ctx context.Context) ([]string, error) {
	resp, err := s.raw.ListDatabasesWithResponse(ctx)
	if err != nil {
		return nil, err
	}
	if err := checkResponse(resp.HTTPResponse, resp.Body); err != nil {
		return nil, err
	}
	list, err := decodeBody(resp.JSON200, resp.Body)
	if err != nil {
		return nil, err
	}
	if list == nil || list.Result == nil {
		return []string{}, nil
	}
	return list.Result, nil
}

// Exists reports whether the named database exists AND the caller is authorized to see
// it. A false result cannot prove absence: the server answers identically for a database
// that does not exist and one the caller may not access (unauthorized looks the same).
func (s *Server) Exists(ctx context.Context, name string) (bool, error) {
	resp, err := s.raw.CheckDatabaseExistsWithResponse(ctx, name)
	if err != nil {
		return false, err
	}
	if err := checkResponse(resp.HTTPResponse, resp.Body); err != nil {
		return false, err
	}
	res, err := decodeBody(resp.JSON200, resp.Body)
	if err != nil {
		return false, err
	}
	return res != nil && res.Result, nil
}

// ServerInfo returns the server's info document (basic mode).
func (s *Server) ServerInfo(ctx context.Context) (*generated.ServerInfo, error) {
	resp, err := s.raw.GetServerInfoWithResponse(ctx, nil)
	if err != nil {
		return nil, err
	}
	if err := checkResponse(resp.HTTPResponse, resp.Body); err != nil {
		return nil, err
	}
	return nonEmpty(decodeBody(resp.JSON200, resp.Body))
}

// Health succeeds only on 204, the server's healthy answer; any other status, 200
// included, is an *ArcadeDBError.
func (s *Server) Health(ctx context.Context) error {
	resp, err := s.raw.CheckHealthWithResponse(ctx)
	if err != nil {
		return err
	}
	if resp.HTTPResponse.StatusCode != http.StatusNoContent {
		return newError(resp.HTTPResponse.StatusCode, resp.Body, resp.HTTPResponse.Header.Get(requestIDHeader))
	}
	return nil
}

// Ready reports readiness: any 2xx is true, 503 is false with no error (the server is up
// but not ready), and any other status is an *ArcadeDBError.
func (s *Server) Ready(ctx context.Context) (bool, error) {
	resp, err := s.raw.CheckReadyWithResponse(ctx)
	if err != nil {
		return false, err
	}
	if resp.HTTPResponse.StatusCode == http.StatusServiceUnavailable {
		return false, nil
	}
	if err := checkResponse(resp.HTTPResponse, resp.Body); err != nil {
		return false, err
	}
	return true, nil
}
