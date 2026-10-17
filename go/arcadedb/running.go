package arcadedb

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

// QueryStatus is what a terminate command answers for one statement or transaction.
type QueryStatus string

const (
	// QueryTerminated means the statement stopped and what it wrote was rolled back.
	QueryTerminated QueryStatus = "terminated"
	// QueryCompleted means the statement ended on its own before it noticed the request, so
	// what it did stands: a caller undoing its work has to undo this one too.
	QueryCompleted QueryStatus = "completed"
	// QueryTerminating means the statement has not stopped yet, within the wait. Some
	// statements (SQL SLEEP, for one) only notice at their next checkpoint.
	QueryTerminating QueryStatus = "terminating"
	// QueryNotFound means no such statement runs on this server, or it belongs to another
	// user: someone else's statement reads as not found, never as forbidden.
	QueryNotFound QueryStatus = "not found"
)

// RunningQuery is one statement as ListQueries returns it. SessionID is empty for a
// statement that does not run inside a transaction, and Tag is empty for one sent without
// an X-ArcadeDB-Query-Tag (see WithQueryTag).
type RunningQuery struct {
	ID            string `json:"id"`
	Database      string `json:"database"`
	User          string `json:"user"`
	Protocol      string `json:"protocol"`
	Language      string `json:"language"`
	Text          string `json:"text"`
	StartedAt     int64  `json:"startedAt"` // epoch milliseconds
	ElapsedMs     int64  `json:"elapsedMs"`
	Terminating   bool   `json:"terminating"`
	SessionID     string `json:"sessionId"`
	Tag           string `json:"tag"`
	ClientAddress string `json:"clientAddress"`
	Server        string `json:"server"`
}

// TerminateResult is the answer for one statement or transaction. SessionID and
// SessionOpen are set only for a statement that ran inside a transaction: a command
// terminated there ends the transaction too (SessionOpen false), a terminated read leaves
// it open. For a QueryTerminating statement SessionOpen is the state at the time of the
// answer, since a command ends its session as it stops.
type TerminateResult struct {
	ID          string      `json:"id"`
	Status      QueryStatus `json:"status"`
	SessionID   string      `json:"sessionId"`
	SessionOpen *bool       `json:"sessionOpen"`
}

// OpenTransaction is one transaction session as ListTransactions returns it.
// RunningQueries holds the ids of the statements running in it, which TerminateQuery takes.
type OpenTransaction struct {
	ID             string   `json:"id"`
	User           string   `json:"user"`
	Database       string   `json:"database"`
	IdleMs         int64    `json:"idleMs"`
	Busy           bool     `json:"busy"`
	RunningQueries []string `json:"runningQueries"`
	Server         string   `json:"server"`
}

// ListQueriesOptions narrows ListQueries. An empty field is no filter.
type ListQueriesOptions struct {
	Database string
	Tag      string
}

// TerminateOptions bounds how long a terminate command waits for the statements to stop.
// Zero leaves the server's default, 5 seconds; the server caps it at 10 seconds. A
// statement still running when the wait ends is answered QueryTerminating.
type TerminateOptions struct {
	Wait time.Duration
}

// queryTerminatedException is the exception the server names in the 409 a terminated
// request receives. The 409 status alone is shared with a request still in flight under the
// same X-Request-Id, so IsQueryTerminated matches this, not the status or the message.
const queryTerminatedException = "com.arcadedb.exception.QueryTerminatedException"

// IsQueryTerminated reports whether err is the answer to a request that TerminateQuery,
// TerminateQueriesByTag or TerminateTransaction stopped: a 409 *ArcadeDBError whose
// Exception is com.arcadedb.exception.QueryTerminatedException. Not retryable: somebody
// stopped this work on purpose, and what it wrote was rolled back. Another 409, such as a
// request still in flight under the same X-Request-Id, is not matched.
func IsQueryTerminated(err error) bool {
	var ae *ArcadeDBError
	return errors.As(err, &ae) && ae.Status == 409 && ae.Exception == queryTerminatedException
}

// ListQueries lists the statements running on this server, with the tag each was sent
// with. Root sees every statement, another user only their own. Like every method in this
// file it goes through POST /api/v1/server, and is never forwarded to the cluster leader:
// behind a load balancer it sees only the server this client happened to reach.
//
// opts.Database must not contain a space or control character (anything at or below U+0020),
// since the server reads it as one word, and opts.Tag must not start or end with one, since the
// server trims it. Either is refused with an error wrapping ErrInvalidName before anything is
// sent.
func (s *Server) ListQueries(ctx context.Context, opts ListQueriesOptions) ([]RunningQuery, error) {
	command := "list queries"
	if opts.Database != "" {
		if err := checkWord("database name", opts.Database); err != nil {
			return nil, err
		}
		command += " database " + opts.Database
	}
	if opts.Tag != "" {
		if err := checkTag(opts.Tag); err != nil {
			return nil, err
		}
		command += " tag " + opts.Tag
	}
	var out []RunningQuery
	if err := s.runningCommand(ctx, command, 0, &out); err != nil {
		return nil, err
	}
	return nonNil(out), nil
}

// TerminateQuery stops the statement with the given id (RunningQuery.ID) and waits for it
// to end, up to opts.Wait. See QueryStatus for what each answer means; another user's
// statement is answered QueryNotFound. The stopped request itself receives a 409 that
// IsQueryTerminated matches. An id that is empty or contains a space or control character is
// refused with an error wrapping ErrInvalidName before anything is sent.
func (s *Server) TerminateQuery(ctx context.Context, id string, opts TerminateOptions) (TerminateResult, error) {
	if err := checkWord("query id", id); err != nil {
		return TerminateResult{}, err
	}
	var out TerminateResult
	err := s.runningCommand(ctx, "terminate query "+id, opts.Wait, &out)
	return out, err
}

// TerminateQueriesByTag stops every statement sent with the given tag and waits for them to
// end, up to opts.Wait, answering each with its own TerminateResult. No statement with that
// tag is an empty slice, not an error. A tag that is empty or has leading or trailing white
// space is refused with an error wrapping ErrInvalidName before anything is sent.
func (s *Server) TerminateQueriesByTag(ctx context.Context, tag string, opts TerminateOptions) ([]TerminateResult, error) {
	if tag == "" {
		return nil, fmt.Errorf("%w: tag is empty", ErrInvalidName)
	}
	if err := checkTag(tag); err != nil {
		return nil, err
	}
	var out []TerminateResult
	if err := s.runningCommand(ctx, "terminate queries tag "+tag, opts.Wait, &out); err != nil {
		return nil, err
	}
	return nonNil(out), nil
}

// ListTransactions lists the open transaction sessions on this server. Root sees every
// session, another user only their own.
func (s *Server) ListTransactions(ctx context.Context) ([]OpenTransaction, error) {
	var out []OpenTransaction
	if err := s.runningCommand(ctx, "list transactions", 0, &out); err != nil {
		return nil, err
	}
	return nonNil(out), nil
}

// TerminateTransaction rolls back and ends the transaction session with the given id
// (OpenTransaction.ID, the arcadedb-session-id a begin returned), waiting up to opts.Wait for
// a statement running in it to stop, as TerminateQuery does: the answer is QueryTerminating
// when it has not. A statement running in it is stopped, and its request receives a 409 that
// IsQueryTerminated matches. A statement or commit sent on the session afterwards gets a 404, so
// the owner's Transaction returns an error (a server built before ArcadeData/arcadedb#10164
// answers that commit 204, and Transaction returns nil for work that is gone). An unknown
// session, or another user's, is answered QueryNotFound.
// A session id that is empty or contains a space or control character is refused with an error
// wrapping ErrInvalidName before anything is sent.
func (s *Server) TerminateTransaction(ctx context.Context, sessionID string, opts TerminateOptions) (TerminateResult, error) {
	if err := checkWord("session id", sessionID); err != nil {
		return TerminateResult{}, err
	}
	var out TerminateResult
	err := s.runningCommand(ctx, "terminate transaction "+sessionID, opts.Wait, &out)
	return out, err
}

// Progress lists the long-running maintenance operations running on this server for the
// database, with their step-by-step progress; Result is empty when none is. The server reads
// a lock-free snapshot, so polling it at any rate cannot interfere with what it watches. It
// is never forwarded to the cluster leader.
func (d *Database) Progress(ctx context.Context) (*generated.ProgressResponse, error) {
	resp, err := d.srv.raw.GetOperationProgressWithResponse(ctx, d.name)
	if err != nil {
		return nil, err
	}
	if err := checkResponse(resp.HTTPResponse, resp.Body); err != nil {
		return nil, err
	}
	return nonEmpty(decodeBody(resp.JSON200, resp.Body))
}

// runningCommand sends command through POST /api/v1/server, with "wait" in whole milliseconds,
// rounded up, when wait is positive, and decodes the body's "result" into out. It does not go through
// ServerCommand because the contract's CommandRequest has no "wait" field, although the server
// reads one, and because the results are typed here rather than returned as a map.
func (s *Server) runningCommand(ctx context.Context, command string, wait time.Duration, out any) error {
	body := map[string]any{"command": command, "language": string(SQL)}
	if wait > 0 {
		// Rounded up, as the Python and TypeScript clients do: truncating would send 1.5ms as 1,
		// and a positive sub-millisecond wait as 0, which the server reads as "do not wait".
		body["wait"] = int64((wait + time.Millisecond - 1) / time.Millisecond)
	}
	payload, err := json.Marshal(body)
	if err != nil {
		return err
	}
	resp, err := s.raw.ExecuteServerCommandWithBody(ctx, nil, "application/json", bytes.NewReader(payload))
	if err != nil {
		return err
	}
	raw, err := readChecked(resp)
	if err != nil {
		return err
	}
	var envelope struct {
		Result json.RawMessage `json:"result"`
	}
	if len(bytes.TrimSpace(raw)) == 0 {
		return ErrEmptyBody
	}
	if err := json.Unmarshal(raw, &envelope); err != nil {
		return err
	}
	if len(envelope.Result) == 0 || string(envelope.Result) == "null" {
		return ErrEmptyBody
	}
	return json.Unmarshal(envelope.Result, out)
}

// spaceOrControl is what the server, in Java, trims and splits on: every character at or below
// U+0020. It is deliberately not unicode.IsSpace, which would refuse a no-break space the server
// keeps and accept a control character it strips. The Python and TypeScript clients use the
// same rule.
func spaceOrControl(r rune) bool { return r <= ' ' }

// checkWord refuses a value the server would split: it reads a database name, a query id and
// a session id as one word.
func checkWord(what, v string) error {
	if v == "" || strings.ContainsFunc(v, spaceOrControl) {
		return fmt.Errorf("%w: %s %q is empty or contains a space or control character", ErrInvalidName, what, v)
	}
	return nil
}

// checkTag refuses a tag the server would silently change: it takes the rest of the command
// as the tag, trimmed, so " a" would match "a" rather than the tag the caller named.
func checkTag(tag string) error {
	if strings.TrimFunc(tag, spaceOrControl) != tag {
		return fmt.Errorf("%w: tag %q starts or ends with a space or control character", ErrInvalidName, tag)
	}
	return nil
}

func nonNil[T any](s []T) []T {
	if s == nil {
		return []T{}
	}
	return s
}
