// Package arcadedbgrpc is the Go client for ArcadeDB's gRPC API.
//
// The client is generated from ArcadeDB's protobuf contract (package generated) with a thin
// hand-written facade on top. [NewClient] opens one connection; [Client.Raw] returns the
// generated client for ArcadeDbService, the data plane, through which every RPC of that
// service is reachable, and [Client.RawAdmin] the generated client for ArcadeDbAdminService,
// the control plane. The facade adds only what the generated client alone handles badly:
// [Client.StreamQuery] and [Client.TimeSeriesQuery] (lazy, re-rangeable iterators over a
// server stream), [Client.InsertStream] and [Client.TimeSeriesWriteStream] (client streams
// sent in chunks), and [Client.Transaction], which runs a callback against a [TxHandle] and
// commits or rolls back for it. Everything else is called through Raw directly. There is no
// default timeout: bound every call with a context deadline.
//
// # Authentication
//
// [WithPasswordAuth] and [WithBearerToken] install auth as a pair of connection
// interceptors, one unary and one stream, not as per-call metadata, so calls made through
// Raw carry the same credentials as the facade methods.
//
// # The two guards
//
// Both refusals return [ErrInsecureChannel], matched with errors.Is, and both are satisfied
// by [WithTransportCredentials] or by the explicit opt-in [WithInsecure]:
//
//   - NewClient refuses WithPasswordAuth over a connection with no stated transport
//     credentials, because the password would cross the wire as cleartext metadata
//     (ArcadeData/arcadedb#5048). A bearer token never trips it.
//   - RawAdmin refuses, whatever auth is configured, on such a connection: 42 of
//     ArcadeDbAdminService's 44 RPCs carry DatabaseCredentials inside the request body,
//     which the first guard cannot see. A plaintext client keeps working for the data plane.
//
// Credentials passed through [WithDialOptions] are honoured but invisible to both guards,
// which therefore stay closed.
//
// # Errors
//
// A failed RPC returns grpc-go's status error unchanged, from Raw, RawAdmin and every facade
// method alike: match it with status.Code or status.FromError. There is no package error
// type wrapping RPC failures. The package's own errors ([ErrInsecureChannel],
// [ErrNoTransactionID], [ErrNotCommitted], [TxError]) are refusals the facade raises before
// or instead of an RPC.
//
// The module's README covers each of these at length, including the RPCs a TxHandle does not
// bind and why.
package arcadedbgrpc
