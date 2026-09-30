// Package batchrows turns structured rows into ArcadeDB's GraphBatch ndjson line format,
// a port of the Python driver's _internal/batch_rows.py:
//
//	{"@type":"vertex","@class":"Person","@id":"p1","name":"Alice"}
//	{"@type":"edge","@class":"Knows","@from":"p1","@to":"p2","since":2020}
//
// The contract's BatchLine schema describes ONE line, not the newline-delimited body, so no
// generator can produce this encoder; it is hand-written, and three of its properties are
// load-bearing rather than stylistic:
//
//  1. Properties are flattened beside the control keys, never nested. The server accepts a
//     nested "properties" object, answers 200 with correct counters, and stores a property
//     literally named "properties" holding the map; nothing fails until someone queries for
//     a field that is not there. Taking Properties as its own map and flattening it here
//     means a caller cannot produce that payload.
//  2. Every vertex is written before any edge. The server resolves an edge's @from/@to
//     against temp ids declared earlier in the SAME payload only, and answers 400 otherwise;
//     since a batch is not atomic, that 400 can arrive after earlier chunks have durably
//     committed. Vertices and edges arrive as separate sequences so the wrong order cannot
//     be expressed.
//  3. A property named like a control key (@type, @class, @id, @from, @to) is rejected
//     rather than written. Python's dict merge lets such a property silently override the
//     control key, turning a vertex into an edge or re-typing it; here the row fails with
//     ErrPropertyShadowsControlKey and is never written.
//
// Unlike the Python module, nothing is materialised: rows are encoded one line at a time as
// the sequences yield them, so a payload larger than memory can be loaded.
package batchrows

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"iter"
	"slices"
)

// ErrPropertyShadowsControlKey is wrapped by the error Write returns for a row whose
// Properties contain one of the control keys @type, @class, @id, @from or @to.
var ErrPropertyShadowsControlKey = errors.New("property shadows a batch control key")

// Vertex mirrors arcadedb.VertexRow; see there for the field semantics.
type Vertex struct {
	Type       string
	ID         string
	Properties map[string]any
}

// Edge mirrors arcadedb.EdgeRow; see there for the field semantics.
type Edge struct {
	Type       string
	From       string
	To         string
	Properties map[string]any
}

var controlKeys = map[string]bool{"@type": true, "@class": true, "@id": true, "@from": true, "@to": true}

// Write encodes every vertex, then every edge, as one JSON object plus "\n" each. Control
// keys come first (@type, @class, @id for a vertex, @id only when ID is non-empty; @type,
// @class, @from, @to for an edge), then the properties in sorted key order. HTML characters
// are not escaped. A nil sequence means none.
//
// Each line is fully encoded and validated before any of it is written, so a row that fails
// (a shadowed control key, an unencodable value) writes nothing; earlier rows have already
// been written. The first failure, of encoding or of w, stops iteration and is returned.
func Write(w io.Writer, vertices iter.Seq[Vertex], edges iter.Seq[Edge]) error {
	e := newEncoder(w)
	if vertices != nil {
		i := 0
		for v := range vertices {
			control := []string{"@type", "vertex", "@class", v.Type}
			if v.ID != "" {
				control = append(control, "@id", v.ID)
			}
			if err := e.line("vertex", i, control, v.Properties); err != nil {
				return err
			}
			i++
		}
	}
	if edges != nil {
		i := 0
		for ed := range edges {
			control := []string{"@type", "edge", "@class", ed.Type, "@from", ed.From, "@to", ed.To}
			if err := e.line("edge", i, control, ed.Properties); err != nil {
				return err
			}
			i++
		}
	}
	return nil
}

type encoder struct {
	w   io.Writer
	buf bytes.Buffer
	enc *json.Encoder
}

func newEncoder(w io.Writer) *encoder {
	e := &encoder{w: w}
	e.enc = json.NewEncoder(&e.buf)
	e.enc.SetEscapeHTML(false)
	return e
}

// value appends v's JSON encoding to the line buffer, without Encode's trailing newline.
func (e *encoder) value(v any) error {
	if err := e.enc.Encode(v); err != nil {
		return err
	}
	e.buf.Truncate(e.buf.Len() - 1)
	return nil
}

// line encodes one row into the buffer and writes it only once it is complete. control
// holds key/value pairs, in order.
func (e *encoder) line(kind string, index int, control []string, props map[string]any) error {
	keys := make([]string, 0, len(props))
	for k := range props {
		if controlKeys[k] {
			return fmt.Errorf("arcadedb: %s %d: %q: %w", kind, index, k, ErrPropertyShadowsControlKey)
		}
		keys = append(keys, k)
	}
	slices.Sort(keys)
	e.buf.Reset()
	e.buf.WriteByte('{')
	for i := 0; i < len(control); i += 2 {
		if i > 0 {
			e.buf.WriteByte(',')
		}
		// Encoding a string cannot fail.
		_ = e.value(control[i])
		e.buf.WriteByte(':')
		_ = e.value(control[i+1])
	}
	for _, k := range keys {
		e.buf.WriteByte(',')
		_ = e.value(k)
		e.buf.WriteByte(':')
		if err := e.value(props[k]); err != nil {
			return fmt.Errorf("arcadedb: %s %d: property %q: %w", kind, index, k, err)
		}
	}
	e.buf.WriteString("}\n")
	_, err := e.w.Write(e.buf.Bytes())
	return err
}
