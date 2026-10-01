package ndjson

import (
	"errors"
	"strings"
	"testing"
)

func collect(t *testing.T, in string) []string {
	t.Helper()
	var out []string
	for line, err := range Lines(strings.NewReader(in)) {
		if err != nil {
			t.Fatal(err)
		}
		out = append(out, string(line))
	}
	return out
}

func TestLinesSplitsOnNewlineOnly(t *testing.T) {
	got := collect(t, "{\"a\":\"x y\r\u0085z\"}\n{\"b\":1}")
	if len(got) != 2 {
		t.Fatalf("got %d lines: %q", len(got), got)
	}
	if !strings.Contains(got[0], " ") {
		t.Fatalf("first line lost U+2028: %q", got[0])
	}
}

func TestLinesSkipsBlankAndFlushesTail(t *testing.T) {
	got := collect(t, "\n{\"a\":1}\n\n  \n{\"b\":2}")
	if len(got) != 2 || got[0] != `{"a":1}` || got[1] != `{"b":2}` {
		t.Fatalf("got %q", got)
	}
}

func TestLinesNoLengthLimit(t *testing.T) {
	big := strings.Repeat("x", 1<<20)
	got := collect(t, big+"\n"+big)
	if len(got) != 2 || len(got[0]) != 1<<20 || len(got[1]) != 1<<20 {
		t.Fatal("long lines truncated")
	}
}

type errAfter struct {
	data string
	err  error
	done bool
}

func (e *errAfter) Read(p []byte) (int, error) {
	if e.done {
		return 0, e.err
	}
	e.done = true
	return copy(p, e.data), nil
}

func TestLinesReadErrorDropsPartialLine(t *testing.T) {
	boom := errors.New("boom")
	var lines, errs []string
	var gotErr error
	for line, err := range Lines(&errAfter{data: "{\"a\":1}\n{\"b\":", err: boom}) {
		if err != nil {
			gotErr = err
			errs = append(errs, err.Error())
			continue
		}
		lines = append(lines, string(line))
	}
	if len(lines) != 1 || lines[0] != `{"a":1}` || len(errs) != 1 || !errors.Is(gotErr, boom) {
		t.Fatalf("lines=%q errs=%q", lines, errs)
	}
}
