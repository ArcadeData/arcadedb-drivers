package arcadedbgrpc

import (
	"errors"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc/generated"
)

// IsolationLevel is a transaction isolation level the engine provides. The generated
// TransactionIsolation enum also has READ_UNCOMMITTED and SERIALIZABLE, but the server runs
// those as READ_COMMITTED and REPEATABLE_READ without saying so, so a caller who asked for
// SERIALIZABLE would get a weaker level than it named. Transaction accepts only these two;
// set BeginTransactionRequest.Isolation through Raw() for the enum itself.
type IsolationLevel string

const (
	// ReadCommitted: a record read twice inside the transaction shows a change another
	// session committed in between.
	ReadCommitted IsolationLevel = "READ_COMMITTED"
	// RepeatableRead: a record the transaction has read keeps the value it was read with,
	// even after another session commits a change to it.
	RepeatableRead IsolationLevel = "REPEATABLE_READ"
)

// ErrInvalidIsolationLevel is wrapped by the error Transaction returns, before any RPC, for
// an IsolationLevel other than ReadCommitted or RepeatableRead. Sending it as the enum's
// zero value instead would begin at a level nobody chose.
var ErrInvalidIsolationLevel = errors.New("arcadedbgrpc: unsupported isolation level")

var isolations = map[IsolationLevel]generated.TransactionIsolation{
	ReadCommitted:  generated.TransactionIsolation_READ_COMMITTED,
	RepeatableRead: generated.TransactionIsolation_REPEATABLE_READ,
}

type txOptions struct {
	isolation *IsolationLevel // nil when WithIsolationLevel was not given, so "" is refused
}

// TransactionOption configures a Transaction call. WithIsolationLevel is the only one.
type TransactionOption func(*txOptions)

// WithIsolationLevel runs a Transaction at level, sent as BeginTransactionRequest.Isolation.
// Without it the field is left unset and the server begins at READ_COMMITTED, which is also
// every database's default. It ignores a default an embedding application changed with
// setTransactionIsolationLevel, which the HTTP driver's Transaction honours with no level; no
// server configuration key changes it.
func WithIsolationLevel(level IsolationLevel) TransactionOption {
	return func(o *txOptions) { o.isolation = &level }
}
