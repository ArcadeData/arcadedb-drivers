package arcadedb

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/coder/websocket"
)

// InsertTransactionMode is when the server commits what an insert session wrote.
// Pass one to WithInsertTransactionMode.
type InsertTransactionMode string

const (
	// InsertPerStream (the server's default) writes every chunk into one transaction that
	// the commit frame commits and the rollback frame discards. It is the only mode in
	// which a rollback really undoes acknowledged chunks.
	InsertPerStream InsertTransactionMode = "per_stream"
	// InsertPerBatch commits each chunk in a transaction of its own. A rollback frame
	// cannot take back a chunk that was already acknowledged (InsertSummary.PartialCommit).
	InsertPerBatch InsertTransactionMode = "per_batch"
	// InsertPerRow commits each row in a transaction of its own. Same caveat as InsertPerBatch.
	InsertPerRow InsertTransactionMode = "per_row"
	// InsertNone writes into a transaction the caller owns, begun over HTTP; see
	// WithJoinCurrentTransaction, which is the way to ask for it.
	InsertNone InsertTransactionMode = "none"
)

// InsertConflictMode says what a session does with a row that collides with an existing
// one on its key columns. Pass one to WithInsertConflictMode.
type InsertConflictMode string

const (
	InsertConflictError  InsertConflictMode = "error"
	InsertConflictUpdate InsertConflictMode = "update"
	InsertConflictIgnore InsertConflictMode = "ignore"
	InsertConflictAbort  InsertConflictMode = "abort"
)

// InsertOutcomeDetached is the Outcome of the commit and rollback frames of a session that
// joined a transaction (WithJoinCurrentTransaction): neither frame decided anything. The
// rows become durable only when that transaction is committed over HTTP.
const InsertOutcomeDetached = "detached"

const (
	defaultInsertFrameTimeout = 60 * time.Second
	// insertReadLimit bounds one frame read from the server. coder/websocket's own default is
	// 32 KiB, which a batchAck listing per-row errors for a big chunk can exceed.
	insertReadLimit = 16 << 20
	// The title the server gives the unsolicited error frame the idle sweep pushes.
	expiredTitle = "Insert session expired"
)

// ErrNoTransactionToJoin is returned by Database.InsertSession when
// WithJoinCurrentTransaction was given on a handle that is not inside a transaction: there
// is nothing to join, and quietly opening a server-managed session instead would commit
// rows the caller expected to control. Use the handle Transaction passes to its callback.
var ErrNoTransactionToJoin = errors.New("arcadedb: the database handle has no open transaction to join; call InsertSession on the handle Transaction passes to its callback")

// ErrInsertSessionClosed is returned by a session method called after the session ended:
// by Commit, Rollback or Close, by a timeout or cancelled context, by a lost connection,
// or after the server answered with an error that ends the session (InsertSessionError.SessionEnded).
var ErrInsertSessionClosed = errors.New("arcadedb: the /ws insert session is closed")

// InsertSessionError is an error frame the server answered a frame with, or pushed
// unsolicited. A chunk refused as a whole for its row count, or for arriving out of
// sequence, is one of these and leaves the session open with its sequence number unspent;
// the caller may split the batch and send it again. Whether the session is still open is
// InsertSession.IsOpen.
//
// An error frame can arrive at any moment, not only as the answer to the frame just sent:
// when the idle sweep rolls an abandoned session back the server says so with an error
// frame nobody asked for. The next method call reports it, as an *InsertSessionError whose
// Title is "Insert session expired", and the session is then closed. Whatever the answer to
// that call would have been, the session is gone.
//
// SessionEnded says which kind of error it is. It is false only for the refusals that leave
// the session usable: the row cap, a chunk that "skips ahead", and malformed options or
// data. It is true, and the session is closed, for:
//
//   - "Insert session expired", the idle sweep;
//   - "Security error": the grant on the database was revoked (the server has already
//     rolled the session back) or the principal is no longer valid (it also closes the
//     connection);
//   - "Insert session error" whose detail says the session is "not found or expired" or
//     "is closed": the server no longer knows it, for instance after a commit it refused;
//   - "Internal error": the server failed in a way that says nothing about what the session
//     still holds, so it is treated as gone rather than written into further.
type InsertSessionError struct {
	SessionID string
	// Title is the server's short description ("Insert session error", "Security error", ...).
	Title string
	// Detail names the cause, e.g. the row limit a chunk exceeded.
	Detail string
	// Exception is the server-side exception class, when it sent one.
	Exception string
	// SessionEnded is true when the error ended the session; see above.
	SessionEnded bool
}

// Error includes the session id, the title and the detail.
func (e *InsertSessionError) Error() string {
	msg := fmt.Sprintf("arcadedb: /ws insert session %q: %s", e.SessionID, e.Title)
	if e.Detail != "" {
		msg += ": " + e.Detail
	}
	return msg
}

// InsertRowError describes one row of a chunk the server could not apply. RowIndex is the
// row's position in the chunk, or -1 when the whole chunk failed (see InsertAck.WholeChunkFailed).
type InsertRowError struct {
	RowIndex  int    `json:"rowIndex"`
	Code      string `json:"code"`
	Message   string `json:"message"`
	Exception string `json:"exception"`
}

// InsertAck is the server's batchAck for one chunk.
//
// A row the server cannot apply is not a refusal: it is counted in Failed, described in
// Errors, and the rest of the chunk still goes in. A chunk refused outright (too many rows,
// out of sequence) is an *InsertSessionError instead and has no InsertAck.
type InsertAck struct {
	SessionID string `json:"sessionId"`
	ChunkSeq  int64  `json:"chunkSeq"`
	Received  int64  `json:"received"`
	Inserted  int64  `json:"inserted"`
	Updated   int64  `json:"updated"`
	Ignored   int64  `json:"ignored"`
	Failed    int64  `json:"failed"`
	// Replay is true when the server had already applied this sequence and did nothing. The
	// client never causes one by itself.
	Replay bool             `json:"replay"`
	Errors []InsertRowError `json:"errors"`
	// WholeChunkFailed is true when the chunk's own transaction (InsertPerBatch) failed to
	// commit, so nothing in it is durable. The server leaves its watermark where it was and
	// expects the SAME sequence again, so the session's sequence number is not advanced:
	// the next SendChunk resends under it, which replaces this chunk's attempt.
	WholeChunkFailed bool `json:"-"`
	// Raw is the whole frame, for fields this struct does not name.
	Raw map[string]any `json:"-"`
}

// InsertSummary is the full-session totals of a committed frame, each chunk counted once as
// its latest attempt left it.
type InsertSummary struct {
	Received        int64 `json:"received"`
	Inserted        int64 `json:"inserted"`
	Updated         int64 `json:"updated"`
	Ignored         int64 `json:"ignored"`
	Failed          int64 `json:"failed"`
	ExecutionTimeMs int64 `json:"executionTimeMs"`
	// PartialCommit is true for InsertPerBatch and InsertPerRow, whose acknowledged chunks a
	// rollback cannot take back.
	PartialCommit bool `json:"partialCommit"`
	// ExternalTransaction is true when the session joined a transaction; TransactionID is then its id.
	ExternalTransaction bool   `json:"externalTransaction"`
	TransactionID       string `json:"transactionId"`
}

// InsertResult is the server's committed frame, the answer to both Commit and Rollback.
type InsertResult struct {
	SessionID string `json:"sessionId"`
	// Outcome is "commit", "rollback", or InsertOutcomeDetached for a joined transaction.
	Outcome string         `json:"outcome"`
	Summary InsertSummary  `json:"summary"`
	Raw     map[string]any `json:"-"`
}

type insertConfig struct {
	sessionID     string
	targetType    string
	txMode        InsertTransactionMode
	conflictMode  InsertConflictMode
	keyColumns    []string
	updateColumns []string
	validateOnly  bool
	join          bool
	onAck         func(InsertAck)
	frameTimeout  time.Duration
}

// InsertSessionOption configures Database.InsertSession.
type InsertSessionOption func(*insertConfig)

// WithInsertSessionID opens the session under an id of the caller's choosing. Left out, the
// server generates one, and InsertSession.SessionID returns it. A chosen id lives in ONE
// server-wide namespace, shared by every user, database and connection: that is what makes a
// second concurrent start of the same id refused, and it means two unrelated clients that
// both pick a house convention like "batch-1" collide. Name a session only when you need to.
func WithInsertSessionID(id string) InsertSessionOption {
	return func(c *insertConfig) { c.sessionID = id }
}

// WithInsertTargetType sets the type of every record that does not carry its own "@class".
func WithInsertTargetType(typeName string) InsertSessionOption {
	return func(c *insertConfig) { c.targetType = typeName }
}

// WithInsertTransactionMode sets the commit policy. The default is InsertPerStream.
func WithInsertTransactionMode(m InsertTransactionMode) InsertSessionOption {
	return func(c *insertConfig) { c.txMode = m }
}

// WithInsertConflictMode sets what happens to a row colliding on the key columns.
func WithInsertConflictMode(m InsertConflictMode) InsertSessionOption {
	return func(c *insertConfig) { c.conflictMode = m }
}

// WithInsertKeyColumns names the properties that identify an existing row.
func WithInsertKeyColumns(cols ...string) InsertSessionOption {
	return func(c *insertConfig) { c.keyColumns = cols }
}

// WithInsertUpdateColumnsOnConflict limits which properties InsertConflictUpdate overwrites.
func WithInsertUpdateColumnsOnConflict(cols ...string) InsertSessionOption {
	return func(c *insertConfig) { c.updateColumns = cols }
}

// WithInsertValidateOnly has the server receive, parse and count rows without writing any.
func WithInsertValidateOnly() InsertSessionOption {
	return func(c *insertConfig) { c.validateOnly = true }
}

// WithJoinCurrentTransaction makes the session write into the transaction the receiving
// handle is already inside, instead of opening one of its own: InsertSession must be called
// on the *Database that Transaction passes to its callback. The rows become durable when
// that transaction commits, and are undone when it rolls back; the session's own Commit and
// Rollback frames answer InsertOutcomeDetached and decide nothing. It implies
// InsertNone; combining it with another transaction mode is an error. Called on a handle
// outside a transaction, InsertSession returns ErrNoTransactionToJoin.
func WithJoinCurrentTransaction() InsertSessionOption {
	return func(c *insertConfig) { c.join = true }
}

// WithOnInsertAck registers a callback invoked, on the calling goroutine, with every
// acknowledgement before SendChunk returns it.
func WithOnInsertAck(fn func(InsertAck)) InsertSessionOption {
	return func(c *insertConfig) { c.onAck = fn }
}

// WithInsertFrameTimeout bounds one frame exchange (the connect and start frame included),
// on top of the context each call takes. The default is 60 seconds.
func WithInsertFrameTimeout(d time.Duration) InsertSessionOption {
	return func(c *insertConfig) { c.frameTimeout = d }
}

// InsertSession is a duplex insert session on the server's /ws WebSocket endpoint: the
// caller sees the acknowledgement of chunk n, and only then decides what to send next,
// including whether to Commit or Rollback at all. Open one with Database.InsertSession.
//
// Not safe for concurrent use: one session belongs to one goroutine. The protocol lets a
// client pipeline frames; this client deliberately does not, because a loader that wants
// the acknowledgements to mean anything has to look at them.
//
// Failure modes:
//
//   - A per-row failure is in the InsertAck (Failed, Errors); it is not an error.
//   - A chunk refused as a whole for its row count (wsMaxInsertChunkRows) or an
//     out-of-sequence number is an *InsertSessionError. The session stays open and the
//     sequence number is not spent, so a smaller chunk takes the same one.
//   - A chunk over wsMaxInsertFrameSize is different: the server closes the connection
//     (WebSocket status 1009) instead of answering, so the call fails with a connection
//     error and the session is closed, rolled back by the server. Keep chunks below it.
//   - A timeout or cancelled context abandons the exchange and closes the connection, since
//     the late answer could no longer be matched to its frame; the server rolls back.
//   - An unsolicited error frame (the idle sweep, wsInsertSessionExpireTimeout) is
//     reported by the next call; see InsertSessionError.
//   - A security error (revoked grant, invalid principal), a session the server no longer
//     knows, or an internal error closes the session; InsertSessionError.SessionEnded says
//     so, and IsOpen turns false.
type InsertSession struct {
	conn       *websocket.Conn
	in         chan []byte
	readErr    error // valid once in is closed
	stopRead   context.CancelFunc
	cfg        *insertConfig
	sessionID  string
	database   string
	txMode     string
	conflict   string
	validate   bool
	externalTx string
	chunkSeq   int64
	open       bool
}

// SessionID is the id the session is known by on the server, generated by it unless chosen.
func (s *InsertSession) SessionID() string { return s.sessionID }

// DatabaseName is the database the server echoed back.
func (s *InsertSession) DatabaseName() string { return s.database }

// TransactionMode is the commit policy the server echoed back, which may differ from the
// alias sent.
func (s *InsertSession) TransactionMode() string { return s.txMode }

// ConflictMode is the conflict mode the server echoed back.
func (s *InsertSession) ConflictMode() string { return s.conflict }

// ExternalTransactionID is the transaction this session joined, or "" when it manages its own.
func (s *InsertSession) ExternalTransactionID() string { return s.externalTx }

// LastChunkSeq is the sequence number of the last chunk the server acknowledged and
// accepted. The next one is this plus one.
func (s *InsertSession) LastChunkSeq() int64 { return s.chunkSeq }

// IsOpen reports whether the session can still take frames.
func (s *InsertSession) IsOpen() bool { return s.open }

// InsertSession opens a duplex insert session on /ws for this database and returns it once
// the server has answered the start frame. ctx bounds the connect and the start exchange
// only. The connection authenticates with the Server's configured headers and uses its
// http.Client. The caller must Close the session.
//
// Nothing is written until the caller commits (InsertPerStream) or the session joins a
// transaction that commits; see InsertSession for the failure modes.
func (d *Database) InsertSession(ctx context.Context, opts ...InsertSessionOption) (*InsertSession, error) {
	cfg := &insertConfig{frameTimeout: defaultInsertFrameTimeout}
	for _, o := range opts {
		o(cfg)
	}
	if cfg.frameTimeout <= 0 {
		cfg.frameTimeout = defaultInsertFrameTimeout
	}
	if cfg.join {
		if cfg.txMode != "" && cfg.txMode != InsertNone {
			return nil, fmt.Errorf("arcadedb: WithJoinCurrentTransaction implies transaction mode %q, not %q", InsertNone, cfg.txMode)
		}
		if d.sessionID == "" {
			return nil, ErrNoTransactionToJoin
		}
		cfg.txMode = InsertNone
	}

	wsURL, err := d.srv.webSocketURL()
	if err != nil {
		return nil, err
	}
	header := http.Header{}
	applyHeaders(header, d.srv.headers)

	dialCtx, cancel := context.WithTimeout(ctx, cfg.frameTimeout)
	defer cancel()
	conn, _, err := websocket.Dial(dialCtx, wsURL, &websocket.DialOptions{
		HTTPClient:      d.srv.client,
		HTTPHeader:      header,
		CompressionMode: websocket.CompressionDisabled,
	})
	if err != nil {
		return nil, fmt.Errorf("arcadedb: opening the /ws insert session on %s: %w", wsURL, err)
	}
	conn.SetReadLimit(insertReadLimit)

	readCtx, stopRead := context.WithCancel(context.Background())
	s := &InsertSession{conn: conn, in: make(chan []byte, 8), stopRead: stopRead, cfg: cfg, sessionID: cfg.sessionID, open: true}
	go s.readLoop(readCtx)

	options := map[string]any{}
	if cfg.targetType != "" {
		options["targetType"] = cfg.targetType
	}
	if cfg.txMode != "" {
		options["transactionMode"] = string(cfg.txMode)
	}
	if cfg.conflictMode != "" {
		options["conflictMode"] = string(cfg.conflictMode)
	}
	if cfg.keyColumns != nil {
		options["keyColumns"] = cfg.keyColumns
	}
	if cfg.updateColumns != nil {
		options["updateColumnsOnConflict"] = cfg.updateColumns
	}
	if cfg.validateOnly {
		options["validateOnly"] = true
	}
	start := map[string]any{"action": "start", "database": d.name, "options": options}
	if cfg.sessionID != "" {
		start["sessionId"] = cfg.sessionID
	}
	if cfg.join {
		start["transactionId"] = d.sessionID
	}

	var started struct {
		SessionID       string `json:"sessionId"`
		Database        string `json:"database"`
		TransactionMode string `json:"transactionMode"`
		ConflictMode    string `json:"conflictMode"`
		ValidateOnly    bool   `json:"validateOnly"`
		TransactionID   string `json:"transactionId"`
	}
	if _, err := s.exchange(ctx, start, "started", &started); err != nil {
		s.abort()
		return nil, err
	}
	s.sessionID, s.database, s.txMode, s.conflict = started.SessionID, started.Database, started.TransactionMode, started.ConflictMode
	s.validate, s.externalTx = started.ValidateOnly, started.TransactionID
	return s, nil
}

// SendChunk sends one chunk of records and returns the acknowledgement the server answered
// with, after handing it to the WithOnInsertAck callback if there is one. Every record is a
// JSON object; a record's own "@class" overrides the session's target type, and an edge
// names its endpoints with "@from" and "@to".
//
// The sequence number is managed here: it starts at 1, is contiguous, and is advanced only
// once the server has accepted the chunk, so a chunk refused as a whole is resent under the
// same number. See InsertSession for what each failure leaves behind.
func (s *InsertSession) SendChunk(ctx context.Context, records []map[string]any) (InsertAck, error) {
	if !s.open {
		return InsertAck{}, ErrInsertSessionClosed
	}
	if records == nil {
		records = []map[string]any{}
	}
	seq := s.chunkSeq + 1
	var ack InsertAck
	raw, err := s.exchange(ctx, map[string]any{
		"action": "chunk", "sessionId": s.sessionID, "chunkSeq": seq, "records": records,
	}, "batchAck", &ack)
	if err != nil {
		return InsertAck{}, err
	}
	ack.Raw = raw
	for _, e := range ack.Errors {
		if e.RowIndex == -1 {
			ack.WholeChunkFailed = true
		}
	}
	if !ack.WholeChunkFailed {
		s.chunkSeq = seq
	}
	if s.cfg.onAck != nil {
		s.cfg.onAck(ack)
	}
	return ack, nil
}

// Commit ends the session and commits what it wrote. A session that joined a transaction
// commits nothing here: the Outcome is InsertOutcomeDetached and the rows become durable
// when that transaction commits. The session is closed afterwards whatever the answer was:
// a commit the engine refused has already rolled the session back.
func (s *InsertSession) Commit(ctx context.Context) (InsertResult, error) {
	return s.finish(ctx, "commit")
}

// Rollback ends the session and discards what it wrote. Only InsertPerStream can undo
// chunks already acknowledged (Summary.PartialCommit says so). On a joined transaction it
// discards nothing; see Commit.
func (s *InsertSession) Rollback(ctx context.Context) (InsertResult, error) {
	return s.finish(ctx, "rollback")
}

// Close rolls the session back if it is still open, then closes the connection. It is
// idempotent, so it is safe to defer right after a successful Commit. The rollback is best
// effort, bounded by the frame timeout and not by any caller context: if it fails, the
// connection closing makes the server roll the session back anyway. Close returns nil.
func (s *InsertSession) Close() error {
	if s.open {
		_, _ = s.finish(context.Background(), "rollback")
	}
	s.abort()
	return nil
}

func (s *InsertSession) finish(ctx context.Context, action string) (InsertResult, error) {
	if !s.open {
		return InsertResult{}, ErrInsertSessionClosed
	}
	var res InsertResult
	raw, err := s.exchange(ctx, map[string]any{"action": action, "sessionId": s.sessionID}, "committed", &res)
	s.open = false
	if err != nil {
		return InsertResult{}, err
	}
	res.Raw = raw
	return res, nil
}

// exchange writes one frame and reads the one answer to it, decoding it into out. Every
// frame this client sends is answered by exactly one frame, so a frame already waiting is an
// unsolicited error and is reported rather than skipped.
func (s *InsertSession) exchange(ctx context.Context, frame map[string]any, want string, out any) (map[string]any, error) {
	ctx, cancel := context.WithTimeout(ctx, s.cfg.frameTimeout)
	defer cancel()

	payload, err := json.Marshal(frame)
	if err != nil {
		return nil, fmt.Errorf("arcadedb: encoding a /ws insert frame: %w", err)
	}
	if err := s.conn.Write(ctx, websocket.MessageText, payload); err != nil {
		// The server may have said why before it went away: an error frame already read.
		select {
		case raw, ok := <-s.in:
			if ok {
				if serr := s.asError(raw); serr != nil {
					s.abort()
					return nil, serr
				}
			}
		default:
		}
		s.abort()
		return nil, fmt.Errorf("arcadedb: sending a frame of /ws insert session %q: %w", s.sessionID, err)
	}

	select {
	case raw, ok := <-s.in:
		if !ok {
			s.abort()
			return nil, fmt.Errorf("arcadedb: the /ws connection of insert session %q closed: %w", s.sessionID, s.readErr)
		}
		return s.decode(raw, want, out)
	case <-ctx.Done():
		s.abort()
		return nil, fmt.Errorf("arcadedb: waiting for the answer to a frame of /ws insert session %q: %w", s.sessionID, ctx.Err())
	}
}

// asError returns the *InsertSessionError an error frame carries, or nil for any other frame.
func (s *InsertSession) asError(raw []byte) *InsertSessionError {
	var f struct {
		Result    string `json:"result"`
		Action    string `json:"action"`
		Error     string `json:"error"`
		Detail    string `json:"detail"`
		SessionID string `json:"sessionId"`
		Exception string `json:"exception"`
	}
	if json.Unmarshal(raw, &f) != nil || (f.Result != "error" && f.Action != "error") {
		return nil
	}
	id := f.SessionID
	if id == "" {
		id = s.sessionID
	}
	return &InsertSessionError{SessionID: id, Title: f.Error, Detail: f.Detail, Exception: f.Exception,
		SessionEnded: endsSession(f.Error, f.Detail)}
}

// endsSession classifies a server error frame by its title and detail, which is all the
// server gives: there is no structured marker. Matched against WebSocketInsertProtocol,
// WebSocketInsertSessionManager.resolve and WebSocketInsertSession.requireOpen.
func endsSession(title, detail string) bool {
	switch title {
	case expiredTitle, "Security error", "Internal error":
		return true
	case "Insert session error":
		return strings.Contains(detail, "not found or expired") || strings.Contains(detail, "' is closed")
	}
	return false
}

func (s *InsertSession) decode(raw []byte, want string, out any) (map[string]any, error) {
	if serr := s.asError(raw); serr != nil {
		// A refused frame leaves the session open; an error that ended it does not.
		if serr.SessionEnded {
			s.abort()
		}
		return nil, serr
	}
	var head struct {
		Action string `json:"action"`
	}
	if err := json.Unmarshal(raw, &head); err != nil {
		s.abort()
		return nil, fmt.Errorf("arcadedb: undecodable frame on /ws insert session %q: %w", s.sessionID, err)
	}
	if head.Action != want {
		s.abort()
		return nil, fmt.Errorf("arcadedb: unexpected frame %q on /ws insert session %q, expected %q", head.Action, s.sessionID, want)
	}
	if err := json.Unmarshal(raw, out); err != nil {
		s.abort()
		return nil, fmt.Errorf("arcadedb: decoding the %q frame of /ws insert session %q: %w", want, s.sessionID, err)
	}
	var m map[string]any
	_ = json.Unmarshal(raw, &m)
	return m, nil
}

// abort marks the session closed and drops the connection without a closing handshake.
func (s *InsertSession) abort() {
	s.open = false
	s.stopRead()
	// CloseNow, not Close: the handshake would wait on a peer that may be gone.
	_ = s.conn.CloseNow()
}

// readLoop feeds whole text frames to s.in until the connection ends, then closes it.
func (s *InsertSession) readLoop(ctx context.Context) {
	defer close(s.in)
	for {
		typ, data, err := s.conn.Read(ctx)
		if err != nil {
			s.readErr = err
			return
		}
		if typ != websocket.MessageText {
			continue
		}
		select {
		case s.in <- data:
		case <-ctx.Done():
			s.readErr = ctx.Err()
			return
		}
	}
}

// webSocketURL is the server's /ws endpoint, under whatever path prefix the base URL carries.
func (s *Server) webSocketURL() (string, error) {
	u, err := url.Parse(s.baseURL)
	if err != nil {
		return "", fmt.Errorf("arcadedb: parsing the server URL: %w", err)
	}
	u.Path = strings.TrimRight(u.Path, "/") + "/ws"
	u.RawQuery, u.Fragment = "", ""
	return u.String(), nil
}
