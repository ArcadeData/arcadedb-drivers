package batchrows

import (
	"bytes"
	"errors"
	"slices"
	"strings"
	"testing"
)

func write(t *testing.T, vs []Vertex, es []Edge) string {
	t.Helper()
	var buf bytes.Buffer
	if err := Write(&buf, slices.Values(vs), slices.Values(es)); err != nil {
		t.Fatal(err)
	}
	return buf.String()
}

// The example in python's batch_rows.py module docstring, byte for byte.
func TestLineFormatMatchesPythonExample(t *testing.T) {
	got := write(t,
		[]Vertex{{Type: "Person", ID: "p1", Properties: map[string]any{"name": "Alice"}}},
		[]Edge{{Type: "Knows", From: "p1", To: "p2", Properties: map[string]any{"since": 2020}}})
	want := `{"@type":"vertex","@class":"Person","@id":"p1","name":"Alice"}` + "\n" +
		`{"@type":"edge","@class":"Knows","@from":"p1","@to":"p2","since":2020}` + "\n"
	if got != want {
		t.Fatalf("got\n%s\nwant\n%s", got, want)
	}
}

func TestPropertiesFollowControlKeysInSortedOrder(t *testing.T) {
	got := write(t, []Vertex{{Type: "V", Properties: map[string]any{"c": 3, "a": 1, "b": "<&>"}}}, nil)
	want := `{"@type":"vertex","@class":"V","a":1,"b":"<&>","c":3}` + "\n"
	if got != want {
		t.Fatalf("got %s want %s", got, want)
	}
}

func TestPropertiesAreFlattenedNotNested(t *testing.T) {
	got := write(t, []Vertex{{Type: "V", Properties: map[string]any{"n": map[string]any{"x": 1}}}}, nil)
	if strings.Contains(got, `"properties"`) || !strings.Contains(got, `"n":{"x":1}`) {
		t.Fatalf("got %s", got)
	}
}

func TestOmitsEmptyID(t *testing.T) {
	got := write(t, []Vertex{{Type: "V"}}, nil)
	if got != `{"@type":"vertex","@class":"V"}`+"\n" {
		t.Fatalf("got %s", got)
	}
}

func TestVerticesBeforeEdges(t *testing.T) {
	var order []string
	vs := func(yield func(Vertex) bool) {
		for _, id := range []string{"a", "b"} {
			order = append(order, "v"+id)
			if !yield(Vertex{Type: "V", ID: id}) {
				return
			}
		}
	}
	es := func(yield func(Edge) bool) {
		order = append(order, "e")
		yield(Edge{Type: "E", From: "a", To: "b"})
	}
	var buf bytes.Buffer
	if err := Write(&buf, vs, es); err != nil {
		t.Fatal(err)
	}
	lines := strings.Split(strings.TrimSuffix(buf.String(), "\n"), "\n")
	if len(lines) != 3 || !strings.Contains(lines[2], `"@type":"edge"`) {
		t.Fatalf("lines = %q", lines)
	}
	if strings.Join(order, ",") != "va,vb,e" {
		t.Fatalf("edges seq started before vertices were done: %v", order)
	}
}

func TestNilSeqsMeanNone(t *testing.T) {
	var buf bytes.Buffer
	if err := Write(&buf, nil, nil); err != nil || buf.Len() != 0 {
		t.Fatalf("err=%v out=%q", err, buf.String())
	}
}

func TestRejectsPropertyShadowingControlKey(t *testing.T) {
	for _, key := range []string{"@type", "@class", "@id", "@from", "@to"} {
		t.Run("vertex "+key, func(t *testing.T) {
			var buf bytes.Buffer
			err := Write(&buf, slices.Values([]Vertex{
				{Type: "Ok", ID: "first"},
				{Type: "V", ID: "offender", Properties: map[string]any{key: "X"}},
				{Type: "Never"},
			}), nil)
			if !errors.Is(err, ErrPropertyShadowsControlKey) {
				t.Fatalf("err = %v", err)
			}
			if !strings.Contains(err.Error(), key) || !strings.Contains(err.Error(), "vertex 1") {
				t.Fatalf("error does not name the row and key: %v", err)
			}
			if out := buf.String(); strings.Contains(out, "offender") || strings.Contains(out, "Never") || !strings.Contains(out, "first") {
				t.Fatalf("out = %q", out)
			}
		})
		t.Run("edge "+key, func(t *testing.T) {
			var buf bytes.Buffer
			err := Write(&buf, nil, slices.Values([]Edge{
				{Type: "E", From: "a", To: "b", Properties: map[string]any{key: "X"}},
			}))
			if !errors.Is(err, ErrPropertyShadowsControlKey) || !strings.Contains(err.Error(), "edge 0") {
				t.Fatalf("err = %v", err)
			}
			if buf.Len() != 0 {
				t.Fatalf("offending line written: %q", buf.String())
			}
		})
	}
}

func TestUnencodablePropertyWritesNothingForThatRow(t *testing.T) {
	var buf bytes.Buffer
	err := Write(&buf, slices.Values([]Vertex{{Type: "V", Properties: map[string]any{"f": func() {}}}}), nil)
	if err == nil || buf.Len() != 0 {
		t.Fatalf("err=%v out=%q", err, buf.String())
	}
}

type failWriter struct{ err error }

func (f failWriter) Write([]byte) (int, error) { return 0, f.err }

func TestWriteErrorStopsIteration(t *testing.T) {
	boom := errors.New("boom")
	stopped := false
	vs := func(yield func(Vertex) bool) {
		for {
			if !yield(Vertex{Type: "V"}) {
				stopped = true
				return
			}
		}
	}
	if err := Write(failWriter{boom}, vs, nil); !errors.Is(err, boom) {
		t.Fatalf("err = %v", err)
	}
	if !stopped {
		t.Fatal("seq was not told to stop")
	}
}
