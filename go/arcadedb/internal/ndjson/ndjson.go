// Package ndjson splits a newline-delimited JSON stream into lines.
package ndjson

import (
	"bufio"
	"bytes"
	"errors"
	"io"
	"iter"
)

// Lines yields each non-blank line of r without its terminator. It splits on '\n' and
// nothing else: U+2028, U+2029, U+0085 and '\r' are legal raw characters inside a JSON
// string and must not end a line. A final unterminated line is flushed. There is no line
// length limit (bufio.Scanner would fail past 64 KiB). Each yielded slice is owned by the
// caller. A read error is yielded once and ends the sequence.
func Lines(r io.Reader) iter.Seq2[[]byte, error] {
	return func(yield func([]byte, error) bool) {
		br := bufio.NewReader(r)
		var pending []byte
		for {
			chunk, err := br.ReadSlice('\n')
			pending = append(pending, chunk...)
			if errors.Is(err, bufio.ErrBufferFull) {
				continue
			}
			line := bytes.TrimSuffix(pending, []byte("\n"))
			if len(bytes.TrimSpace(line)) > 0 {
				if !yield(append([]byte(nil), line...), nil) {
					return
				}
			}
			pending = pending[:0]
			if err != nil {
				if !errors.Is(err, io.EOF) {
					yield(nil, err)
				}
				return
			}
		}
	}
}
