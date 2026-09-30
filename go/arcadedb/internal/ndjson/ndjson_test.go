package ndjson

import (
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
