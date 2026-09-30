package arcadedb

// Database is a handle on one database of a Server. Obtain it with Server.DB; it holds no
// connection of its own.
type Database struct {
	srv       *Server
	name      string
	sessionID string
}

// Name returns the database name.
func (d *Database) Name() string { return d.name }

// sessionParam returns the arcadedb-session-id value for generated calls, or nil outside
// a transaction.
func (d *Database) sessionParam() *string {
	if d.sessionID == "" {
		return nil
	}
	s := d.sessionID
	return &s
}
