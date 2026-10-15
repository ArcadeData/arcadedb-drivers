package arcadedb

import (
	"context"
	"errors"
	"fmt"
	"maps"
	"net/http"
	"strings"
	"time"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

// sessionTokenPrefix starts every token POST /api/v1/login issues ("AU-<server name>-<uuid>").
// An API token starts with "at-" instead.
const sessionTokenPrefix = "AU-"

// ErrNotSessionToken is returned by Logout when the client does not present a session token
// from Login. The server answers 204 to a logout that carries Basic credentials or an API
// token and invalidates nothing, so without this check such a Logout would report a success
// that never happened. Match it with errors.Is.
var ErrNotSessionToken = errors.New("arcadedb: the client does not present a session token")

// ErrInvalidTokenHash is returned, wrapped, by DeleteAPIToken for an argument that is not a
// token hash: 64 lowercase hexadecimal characters, as ListAPITokens and CreateAPIToken report
// it in TokenHash. It is refused before anything is sent, because the argument travels in the
// query string, which proxies and access logs record, and the likeliest mistake is passing the
// plaintext token itself. The error does not repeat the argument, for the same reason. Match
// it with errors.Is.
var ErrInvalidTokenHash = errors.New("arcadedb: not an API token hash")

// LoginResult is what Login and LoginAs return: the session token and the user it
// authenticates.
type LoginResult struct {
	// Token is the session token, prefixed "AU-". Present it with WithToken or WithBearerToken.
	// It is a credential: anyone holding it acts as User until it is logged out or expires.
	Token string
	User  string
}

// Session is one authentication session as ListSessions returns it. These are the server's
// login sessions, not the transaction sessions Begin opens.
type Session struct {
	// Token is the session's live bearer token, a credential in its own right.
	Token string
	User  string
	// Issuer names the cluster node that issued the session when this node holds a copy of
	// it, and is empty for a session this node issued.
	Issuer     string
	CreatedAt  time.Time
	LastUpdate time.Time
	// Elapsed is the time since the session was last used, as the server measured it.
	Elapsed time.Duration
	// SourceIP, UserAgent, Country and City are empty when the server has none: Country and
	// City are only known behind a proxy that reports them.
	SourceIP  string
	UserAgent string
	Country   string
	City      string
}

// APITokenRequest is the token CreateAPIToken issues. Only Name is required.
type APITokenRequest struct {
	// Name must not already be in use; a taken name is a 409 *ArcadeDBError.
	Name string
	// Database scopes the token to one database; empty means "*", every database.
	Database string
	// ExpiresAt is when the token stops authenticating; the zero time means never.
	ExpiresAt time.Time
	// Permissions takes the shape a group's "types" map takes (see SaveGroup); nil grants
	// none.
	Permissions map[string]any
}

// APIToken is one issued API token, as metadata: the server keeps only the hash, so the
// token itself is never listed.
type APIToken struct {
	Name     string
	Database string
	// CreatedAt is when the token was issued. ExpiresAt is the zero time for a token that
	// never expires.
	CreatedAt time.Time
	ExpiresAt time.Time
	// Expired is only reported by ListAPITokens; CreateAPIToken always leaves it false. An
	// expired token authenticates nobody, but stays listed until the next token change
	// retires it.
	Expired     bool
	Permissions map[string]any
	// TokenHash is the SHA-256 hex of the token, and the argument DeleteAPIToken takes.
	TokenHash string
	// TokenSuffix is the token's last characters, to tell two entries apart.
	TokenSuffix string
}

// CreatedAPIToken is what CreateAPIToken returns: the token's metadata and, this once, the
// token itself.
type CreatedAPIToken struct {
	APIToken
	// Token is the plaintext token, prefixed "at-". The server stores only its hash, so this
	// is the only time it can be read: store it before dropping this value. This client never
	// logs or keeps it.
	Token string
}

// Login opens a session with the client's own credentials through POST /api/v1/login and
// returns its token. The client itself is unchanged: present the token with WithToken.
//
// Wrong Basic credentials are a 403 *ArcadeDBError ("Security error"), not a 401: the server
// answers a failed password check with 403 on every endpoint, so on Login it cannot be told
// apart from a forbidden user. 401 is what an invalid or expired bearer token gets. A server
// that has reached its limit of concurrent sessions answers 503.
//
// Each login opens a new session, and a user holds at most 100 by default
// (arcadedb.server.httpAuthSessionMaxPerUser): the next login silently evicts that user's
// oldest session, whose token then gets a 401. Log in once and reuse the token.
func (s *Server) Login(ctx context.Context) (LoginResult, error) {
	return s.login(ctx)
}

// LoginAs opens a session as user, whatever credentials the client is configured with, and
// returns its token. It is the way to act as one user from a client built for another: for
// per-user isolation, log in as the user once and keep s.WithToken(result.Token) rather than
// the user's password.
func (s *Server) LoginAs(ctx context.Context, user, password string) (LoginResult, error) {
	auth := basicAuthValue(user, password)
	return s.login(ctx, func(_ context.Context, req *http.Request) error {
		req.Header.Set("Authorization", auth)
		return nil
	})
}

func (s *Server) login(ctx context.Context, editors ...generated.RequestEditorFn) (LoginResult, error) {
	resp, err := s.raw.LoginWithResponse(ctx, nil, editors...)
	if err != nil {
		return LoginResult{}, err
	}
	if err := checkResponse(resp.HTTPResponse, resp.Body); err != nil {
		return LoginResult{}, err
	}
	r, err := nonEmpty(decodeBody(resp.JSON200, resp.Body))
	if err != nil {
		return LoginResult{}, err
	}
	return LoginResult{Token: r.Token, User: r.User}, nil
}

// WithToken returns a new Server that authenticates every request with token as a bearer
// token, and is otherwise configured like s: the same base URL, extra headers and http.Client.
// s itself is unchanged, so one client can hand out a token-authenticated client per user
// without a data race. It performs no request. Closing either Server closes the shared
// client's idle connections.
func (s *Server) WithToken(token string) *Server {
	headers := maps.Clone(s.headers)
	headers[http.CanonicalHeaderKey("Authorization")] = bearerAuthValue(token)
	srv, err := newServer(s.baseURL, s.client, headers)
	if err != nil {
		// Unreachable: s was built from the same base URL, and no option here can fail.
		panic(fmt.Sprintf("arcadedb: WithToken: %v", err))
	}
	return srv
}

// Logout invalidates the session token the client presents, through POST /api/v1/logout. A
// client that does not present a session token from Login (Basic credentials, or an API
// token) gets ErrNotSessionToken without a request. A token that is no longer valid, because
// it was already logged out or has expired, is a 401 *ArcadeDBError. Once Logout returns nil
// every request with the token, from any client, is a 401.
func (s *Server) Logout(ctx context.Context) error {
	if !strings.HasPrefix(s.headers[http.CanonicalHeaderKey("Authorization")], bearerAuthValue(sessionTokenPrefix)) {
		return ErrNotSessionToken
	}
	resp, err := s.raw.LogoutWithResponse(ctx, nil)
	if err != nil {
		return err
	}
	return checkResponse(resp.HTTPResponse, resp.Body)
}

// ListSessions returns every authentication session the server holds (root only; any other
// user gets a 403 *ArcadeDBError). Each carries its live token, so the result is as sensitive
// as the users' passwords. A missing result is an empty, non-nil slice.
func (s *Server) ListSessions(ctx context.Context) ([]Session, error) {
	resp, err := s.raw.ListSessionsWithResponse(ctx)
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
	sessions := []Session{}
	if list == nil {
		return sessions, nil
	}
	for _, r := range list.Result {
		sessions = append(sessions, Session{
			Token:      r.Token,
			User:       r.User,
			Issuer:     deref(r.Issuer),
			CreatedAt:  time.UnixMilli(int64(r.CreatedAt)),
			LastUpdate: time.UnixMilli(int64(r.LastUpdate)),
			Elapsed:    time.Duration(r.ElapsedMs) * time.Millisecond,
			SourceIP:   deref(r.SourceIp),
			UserAgent:  deref(r.UserAgent),
			Country:    deref(r.Country),
			City:       deref(r.City),
		})
	}
	return sessions, nil
}

// CreateAPIToken issues an API token (root only) through POST /api/v1/server/api-tokens. The
// plaintext token is in the result's Token and nowhere else, ever: see CreatedAPIToken.
//
// A name already in use is a 409 *ArcadeDBError and a blank name a 400. The server refuses to
// send the token in the clear: unless the request arrives over HTTPS, from a loopback address,
// or through a trusted proxy that terminated TLS, it answers 412 and issues nothing (see
// arcadedb.server.apiTokenRequireSecureTransport).
func (s *Server) CreateAPIToken(ctx context.Context, req APITokenRequest) (CreatedAPIToken, error) {
	body := generated.CreateApiTokenRequest{Name: req.Name}
	if req.Database != "" {
		body.Database = &req.Database
	}
	if !req.ExpiresAt.IsZero() {
		ms := int(req.ExpiresAt.UnixMilli())
		body.ExpiresAt = &ms
	}
	if req.Permissions != nil {
		body.Permissions = &req.Permissions
	}
	resp, err := s.raw.CreateApiTokenWithResponse(ctx, nil, body)
	if err != nil {
		return CreatedAPIToken{}, err
	}
	if err := checkResponse(resp.HTTPResponse, resp.Body); err != nil {
		return CreatedAPIToken{}, err
	}
	r, err := nonEmpty(decodeBody(resp.JSON201, resp.Body))
	if err != nil {
		return CreatedAPIToken{}, err
	}
	t := r.Result
	return CreatedAPIToken{
		APIToken: apiToken(t.Name, t.Database, t.CreatedAt, t.ExpiresAt, t.Expired, t.Permissions, t.TokenHash, t.TokenSuffix),
		Token:    t.Token,
	}, nil
}

// ListAPITokens returns every issued API token as metadata (root only). A missing result is
// an empty, non-nil slice.
func (s *Server) ListAPITokens(ctx context.Context) ([]APIToken, error) {
	resp, err := s.raw.ListApiTokensWithResponse(ctx)
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
	tokens := []APIToken{}
	if list == nil {
		return tokens, nil
	}
	for _, t := range list.Result {
		tokens = append(tokens, apiToken(t.Name, t.Database, t.CreatedAt, t.ExpiresAt, t.Expired, t.Permissions, t.TokenHash, t.TokenSuffix))
	}
	return tokens, nil
}

// DeleteAPIToken revokes the API token whose hash is tokenHash (root only), through DELETE
// /api/v1/server/api-tokens. It takes the TokenHash that ListAPITokens and CreateAPIToken
// report, never the token: anything but 64 lowercase hexadecimal characters is refused with
// ErrInvalidTokenHash before it is sent. A hash no token has is a 404 *ArcadeDBError.
func (s *Server) DeleteAPIToken(ctx context.Context, tokenHash string) error {
	if !isTokenHash(tokenHash) {
		return fmt.Errorf("%w: want the 64-character SHA-256 hex TokenHash, never the token itself", ErrInvalidTokenHash)
	}
	resp, err := s.raw.DeleteApiTokenWithResponse(ctx, &generated.DeleteApiTokenParams{Token: tokenHash})
	if err != nil {
		return err
	}
	return checkResponse(resp.HTTPResponse, resp.Body)
}

func isTokenHash(s string) bool {
	if len(s) != 64 {
		return false
	}
	for _, c := range s {
		if (c < '0' || c > '9') && (c < 'a' || c > 'f') {
			return false
		}
	}
	return true
}

func apiToken(name, database string, createdAt, expiresAt int, expired *bool, permissions map[string]any, hash, suffix string) APIToken {
	t := APIToken{
		Name:        name,
		Database:    database,
		CreatedAt:   time.UnixMilli(int64(createdAt)),
		Expired:     expired != nil && *expired,
		Permissions: permissions,
		TokenHash:   hash,
		TokenSuffix: suffix,
	}
	if expiresAt != 0 {
		t.ExpiresAt = time.UnixMilli(int64(expiresAt))
	}
	if t.Permissions == nil {
		t.Permissions = map[string]any{}
	}
	return t
}

func deref(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}
