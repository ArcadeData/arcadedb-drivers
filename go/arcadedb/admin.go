package arcadedb

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

// ErrInvalidName is returned, wrapped, by CreateDatabase and DropDatabase for a name they
// refuse before sending anything: an empty name, or one with leading or trailing white
// space. The server trims the name it reads out of the command string, so " db" would
// silently create or drop "db" rather than the database the caller named. Match it with
// errors.Is.
var ErrInvalidName = errors.New("arcadedb: invalid name")

// User is one server user as ListUsers returns it. The password hash is never returned.
// Databases maps a database name, or "*" for every database, to the groups the user holds
// on it; it is empty, never nil, for a user with no assignment.
type User struct {
	Name      string
	Databases map[string][]string
}

// UserUpdate is the change UpdateUser applies. A zero field is left alone: an empty Password
// keeps the current one (the server refuses a password shorter than 8 characters anyway, so
// "" is never a password to set), and a nil Databases keeps the current assignments. A
// non-nil, empty Databases is sent, and replaces the assignments with none.
type UserUpdate struct {
	Password  string
	Databases map[string][]string
}

// ServerCommand runs one command through POST /api/v1/server and returns the whole JSON
// body unaltered. Most server commands are root-only; see the contract's executeServerCommand
// for the list and for which ones any user may run.
//
// It calls the plain generated Client and decodes the body itself, never the typed
// ExecuteServerCommandWithResponse: the contract declares the 200 body as QueryResponse with
// an array "result", but an administrative command answers {"result": "ok"}, a string, and
// other commands answer with shapes of their own, so the typed parse would report fields the
// wire never carried. A non-2xx status is an *ArcadeDBError and an empty 2xx body is
// ErrEmptyBody.
//
// The command is sent as given. Prefer CreateDatabase and DropDatabase, which refuse a name
// the server would silently trim, and the user and group methods, which use the dedicated
// endpoints with a structured body instead of a command string.
func (s *Server) ServerCommand(ctx context.Context, command string) (map[string]any, error) {
	// "language" is required by the contract's CommandRequest; the server ignores it here.
	payload, err := json.Marshal(generated.CommandRequest{Command: command, Language: string(SQL)})
	if err != nil {
		return nil, err
	}
	resp, err := s.raw.ExecuteServerCommandWithBody(ctx, nil, "application/json", bytes.NewReader(payload))
	return decodeMap(resp, err)
}

// CreateDatabase creates the named database (root only). There is no dedicated endpoint, so
// it sends "create database <name>" through ServerCommand. A name that already exists is
// refused with a 409 *ArcadeDBError (ErrorMessage "Database already exists"), so a caller can
// treat a 409 as "already there" to create a database only when it is missing. A server built
// before ArcadeData/arcadedb#10079 answers 400 "Cannot execute command" instead, with the
// reason only in Detail, which this client does not match on; against such a server, ask
// Exists first: as root, Exists sees every database, so its false is reliable, although
// another client can still create the database between the two calls.
//
// Beyond that check the name is sent as given, embedded spaces included, and the server takes
// the rest of the command as the name: one request runs one command, so a name cannot smuggle
// in a second one, but validate a name built from untrusted input yourself.
func (s *Server) CreateDatabase(ctx context.Context, name string) error {
	return s.databaseCommand(ctx, "create database", name)
}

// DropDatabase drops the named database and deletes its files (root only). There is no
// dedicated endpoint, so it sends "drop database <name>" through ServerCommand. A database
// that does not exist is refused with a 400 *ArcadeDBError.
func (s *Server) DropDatabase(ctx context.Context, name string) error {
	return s.databaseCommand(ctx, "drop database", name)
}

func (s *Server) databaseCommand(ctx context.Context, verb, name string) error {
	if name == "" || strings.TrimSpace(name) != name {
		return fmt.Errorf("%w: database name %q is empty or has leading or trailing white space", ErrInvalidName, name)
	}
	_, err := s.ServerCommand(ctx, verb+" "+name)
	return err
}

// CreateUser creates a server user (root only) through POST /api/v1/server/users. databases
// maps a database name, or "*" for every database, to the groups the user holds there; nil
// sends no assignment. The server refuses a blank name, a name starting with "apitoken:" and
// a password shorter than 8 or longer than 256 characters, each with a 400 *ArcadeDBError.
//
// A name that already exists is refused with a 409 *ArcadeDBError (ErrorMessage "User already
// exists"), so a caller can treat a 409 as "already there" to create a user only when it is
// missing. A server built before ArcadeData/arcadedb#10076 answers 403 "Security error"
// instead, the same status a caller without root gets; against such a server, look for the
// user in ListUsers first rather than reading a 403 as "already exists".
func (s *Server) CreateUser(ctx context.Context, name, password string, databases map[string][]string) error {
	body := generated.CreateUserRequest{Name: name, Password: password}
	if databases != nil {
		body.Databases = &databases
	}
	resp, err := s.raw.CreateUserWithResponse(ctx, nil, body)
	if err != nil {
		return err
	}
	return checkResponse(resp.HTTPResponse, resp.Body)
}

// UpdateUser changes an existing user's password, database assignments, or both (root only)
// through PUT /api/v1/server/users. See UserUpdate for what a zero field means. A user that
// does not exist is a 404 *ArcadeDBError.
func (s *Server) UpdateUser(ctx context.Context, name string, update UserUpdate) error {
	var body generated.UpdateUserRequest
	if update.Password != "" {
		body.Password = &update.Password
	}
	if update.Databases != nil {
		body.Databases = &update.Databases
	}
	resp, err := s.raw.UpdateUserWithResponse(ctx, &generated.UpdateUserParams{Name: name}, body)
	if err != nil {
		return err
	}
	return checkResponse(resp.HTTPResponse, resp.Body)
}

// DropUser deletes a server user (root only) through DELETE /api/v1/server/users. A user
// that does not exist is a 404 *ArcadeDBError, and root cannot be deleted (400).
func (s *Server) DropUser(ctx context.Context, name string) error {
	resp, err := s.raw.DeleteUserWithResponse(ctx, &generated.DeleteUserParams{Name: name})
	if err != nil {
		return err
	}
	return checkResponse(resp.HTTPResponse, resp.Body)
}

// ListUsers returns every server user (root only). A missing result is an empty, non-nil
// slice.
func (s *Server) ListUsers(ctx context.Context) ([]User, error) {
	resp, err := s.raw.ListUsersWithResponse(ctx)
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
	users := []User{}
	if list == nil {
		return users, nil
	}
	for _, u := range list.Result {
		dbs := u.Databases
		if dbs == nil {
			dbs = map[string][]string{}
		}
		users = append(users, User{Name: u.Name, Databases: dbs})
	}
	return users, nil
}

// ListGroups returns every security group (root only), keyed by database name ("*" covers
// every database) and then by group name. A missing result is an empty, non-nil map. The
// group document's schema version is not returned.
func (s *Server) ListGroups(ctx context.Context) (map[string]map[string]generated.GroupDefinition, error) {
	resp, err := s.raw.ListGroupsWithResponse(ctx)
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
	groups := map[string]map[string]generated.GroupDefinition{}
	if list == nil {
		return groups, nil
	}
	for db, d := range list.Result.Databases {
		groups[db] = d.Groups
	}
	return groups, nil
}

// SaveGroup creates the group req names on req.Database, or replaces it if it exists (root
// only), through POST /api/v1/server/groups.
func (s *Server) SaveGroup(ctx context.Context, req generated.SaveGroupRequest) error {
	resp, err := s.raw.CreateOrUpdateGroupWithResponse(ctx, nil, req)
	if err != nil {
		return err
	}
	return checkResponse(resp.HTTPResponse, resp.Body)
}

// DeleteGroup deletes one group of one database (root only) through DELETE
// /api/v1/server/groups. A group that does not exist is a 404 *ArcadeDBError.
func (s *Server) DeleteGroup(ctx context.Context, database, name string) error {
	resp, err := s.raw.DeleteGroupWithResponse(ctx, &generated.DeleteGroupParams{Database: database, Name: name})
	if err != nil {
		return err
	}
	return checkResponse(resp.HTTPResponse, resp.Body)
}
