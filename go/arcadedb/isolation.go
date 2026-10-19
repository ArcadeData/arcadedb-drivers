package arcadedb

import "errors"

// IsolationLevel is a transaction isolation level the /begin endpoint accepts. The engine
// has ReadCommitted and RepeatableRead and no others; the server refuses any other value,
// a differently-cased one included, with 400, and Transaction refuses it before sending
// anything.
type IsolationLevel string

const (
	// ReadCommitted: a record read twice inside the transaction shows a change another
	// session committed in between.
	ReadCommitted IsolationLevel = "READ_COMMITTED"
	// RepeatableRead: a record the transaction has read keeps the value it was read with,
	// even after another session commits a change to it.
	RepeatableRead IsolationLevel = "REPEATABLE_READ"
)

// ErrInvalidIsolationLevel is wrapped by the error Transaction returns, unsent, for an
// IsolationLevel other than ReadCommitted or RepeatableRead.
var ErrInvalidIsolationLevel = errors.New("arcadedb: unsupported isolation level")

// IsolationLevelOption is what WithIsolationLevel returns: a TransactionOption only.
type IsolationLevelOption struct{ level IsolationLevel }

func (i IsolationLevelOption) applyTransaction(o *callOptions) { l := i.level; o.isolation = &l }

// WithIsolationLevel runs a Transaction at level, sent in the begin request's body. Without
// it no level is sent and the server begins at the database's default isolation level. It
// is a TransactionOption only: passing it to Query or Command does not compile.
func WithIsolationLevel(level IsolationLevel) IsolationLevelOption {
	return IsolationLevelOption{level: level}
}
