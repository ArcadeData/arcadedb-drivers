package arcadedbgrpc

import "errors"

// RPC failures are not wrapped. A call through Raw(), RawAdmin() or any facade method that
// the server rejects returns grpc-go's status error unchanged: match it with status.Code(err)
// or status.FromError(err). There is no envelope to normalise, as there is over HTTP, which
// is why the Python client passes grpc.RpcError through and the TypeScript one ConnectError.
// The errors below are the facade's own refusals, raised before or instead of an RPC.

// ErrInsecureChannel is returned for either of two separate refusals to send credentials
// over a connection that may be plaintext. Match it with errors.Is; the returned error
// wraps it with a message naming the way out.
//
// NewClient returns it when WithPasswordAuth is combined with neither
// WithTransportCredentials nor WithInsecure (ArcadeData/arcadedb#5048): the password
// would travel in cleartext metadata.
//
// RawAdmin returns it, independently and whatever auth is configured, when the client has
// neither transport credentials nor WithInsecure: 42 of ArcadeDbAdminService's 44 RPCs
// carry DatabaseCredentials inside the request body, which the #5048 check cannot see.
var ErrInsecureChannel = errors.New("arcadedbgrpc: refusing to send credentials over a connection without transport credentials")

// ErrNoTransactionID is returned by Transaction when BeginTransaction answers with a blank
// transaction id. It is returned before the callback runs: every call the callback made
// would otherwise carry an empty id and run outside any transaction.
var ErrNoTransactionID = errors.New("arcadedbgrpc: BeginTransaction returned a blank transaction id")

// ErrNotCommitted is returned by Transaction when CommitTransaction answers
// committed=false without an error status, which is how the server answers a commit for a
// transaction it has already reaped (success=true, committed=false). The returned error
// wraps it with the server's message; match it with errors.Is. The check reads committed,
// not success, because success is true in exactly this case.
var ErrNotCommitted = errors.New("arcadedbgrpc: the server did not commit the transaction")
