// Command checkzip checks that a directory would make a valid Go module zip, before its
// version is tagged. Once a version is fetched through proxy.golang.org it can be neither
// deleted nor replaced, so a file the module-zip rules reject would leave that version
// permanently unfetchable. This is the check that runs before the tag, not after.
//
// Usage: go run ./cmd/checkzip <module path> <version> <module dir> <required file>...
//
// It validates the module path and version as a pair (module.Check: a v2+ version needs a
// /vN path suffix), lists the files zip.CheckDir omits and rejects, and exits 1 if any file
// is invalid, the tree is too large, or one of the required files (relative to the module root,
// at least one, named by the caller because each module needs different ones) is missing from
// the zip.
//
// CheckDir reads the working tree, not a git commit, while the proxy builds its zip from the
// tagged commit. Run it in a clean checkout (as release.yml and publish-go.yml do) so the two
// see the same files.
package main

import (
	"fmt"
	"os"
	"path/filepath"
	"slices"

	"golang.org/x/mod/module"
	"golang.org/x/mod/zip"
)

func main() {
	if len(os.Args) < 5 {
		fmt.Fprintln(os.Stderr, "usage: checkzip <module path> <version> <module dir> <required file>...")
		os.Exit(2)
	}
	os.Exit(run(os.Args[1], os.Args[2], os.Args[3], os.Args[4:]))
}

// run checks dir as the module modPath at version. required are the files, relative to the
// module root, that the published module must carry (typically go.mod, LICENSE, version.go and
// its generated code).
func run(modPath, version, dir string, required []string) int {
	if err := module.Check(modPath, version); err != nil {
		fmt.Fprintf(os.Stderr, "checkzip: %v\n", err)
		return 1
	}

	cf, err := zip.CheckDir(dir)
	for _, f := range cf.Omitted {
		fmt.Printf("omitted: %s: %v\n", f.Path, f.Err)
	}
	for _, f := range cf.Invalid {
		fmt.Fprintf(os.Stderr, "invalid: %s: %v\n", f.Path, f.Err)
	}
	failed := false
	if err != nil {
		// Invalid files and a size error both surface here, as does an I/O error that
		// left cf empty; all of them fail the check.
		fmt.Fprintf(os.Stderr, "checkzip: %s is not a valid module zip for %s@%s:\n%v\n", dir, modPath, version, err)
		failed = true
	}

	// CheckDir reports Valid paths joined onto dir; compare them relative to it.
	valid := make([]string, 0, len(cf.Valid))
	for _, p := range cf.Valid {
		rel, relErr := filepath.Rel(dir, p)
		if relErr != nil {
			fmt.Fprintf(os.Stderr, "checkzip: %v\n", relErr)
			return 1
		}
		valid = append(valid, filepath.ToSlash(rel))
	}
	for _, want := range required {
		if !slices.Contains(valid, want) {
			fmt.Fprintf(os.Stderr, "checkzip: %s would not be in the module zip - the published module would be broken\n", want)
			failed = true
		}
	}

	if failed {
		return 1
	}
	fmt.Printf("OK: %s@%s zips cleanly (%d files, %d omitted)\n", modPath, version, len(cf.Valid), len(cf.Omitted))
	return 0
}
