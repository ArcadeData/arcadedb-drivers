package arcadedb_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"testing"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb"
	"github.com/ArcadeData/arcadedb-drivers/go/arcadedb/generated"
)

// findContract walks up from the test's working directory to the directory holding
// contracts/ and returns the single arcadedb-openapi-*.json in it. It skips the test when
// no contract is found (for example when the module is vendored outside the repository).
func findContract(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	for {
		if st, err := os.Stat(filepath.Join(dir, "contracts")); err == nil && st.IsDir() {
			matches, err := filepath.Glob(filepath.Join(dir, "contracts", "arcadedb-openapi-*.json"))
			if err != nil {
				t.Fatalf("glob: %v", err)
			}
			switch len(matches) {
			case 0:
				t.Skip("contracts/ holds no arcadedb-openapi-*.json")
			case 1:
				return matches[0]
			default:
				t.Fatalf("contracts/ must hold exactly one OpenAPI contract, found %d: %v", len(matches), matches)
			}
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Skip("no contracts/ directory found above the working directory")
		}
		dir = parent
	}
}

type contractDoc struct {
	Info struct {
		Version string `json:"info_version"`
	}
	RawInfo json.RawMessage                       `json:"info"`
	Paths   map[string]map[string]json.RawMessage `json:"paths"`
}

func readContract(t *testing.T) ([]byte, contractDoc) {
	t.Helper()
	path := findContract(t)
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	var doc contractDoc
	if err := json.Unmarshal(raw, &doc); err != nil {
		t.Fatalf("parse %s: %v", path, err)
	}
	var info struct {
		Version string `json:"version"`
	}
	if err := json.Unmarshal(doc.RawInfo, &info); err != nil {
		t.Fatalf("parse info: %v", err)
	}
	doc.Info.Version = info.Version
	return raw, doc
}

func TestEveryOperationIsGenerated(t *testing.T) {
	_, doc := readContract(t)
	methods := []string{"get", "post", "put", "delete", "patch", "head"}
	clientType := reflect.TypeOf(&generated.Client{})

	total := 0
	var missing []string
	for path, item := range doc.Paths {
		for _, m := range methods {
			rawOp, ok := item[m]
			if !ok {
				continue
			}
			var op struct {
				OperationID string `json:"operationId"`
			}
			if err := json.Unmarshal(rawOp, &op); err != nil {
				t.Fatalf("parse %s %s: %v", m, path, err)
			}
			if op.OperationID == "" {
				t.Errorf("%s %s has no operationId", strings.ToUpper(m), path)
				continue
			}
			total++
			name := strings.ToUpper(op.OperationID[:1]) + op.OperationID[1:]
			// An operation with no JSON request body (ndjson, text or protobuf) is generated
			// only as <Name>WithBody, taking an io.Reader; every other one as <Name>.
			_, plain := clientType.MethodByName(name)
			_, withBody := clientType.MethodByName(name + "WithBody")
			if !plain && !withBody {
				missing = append(missing, name+" ("+op.OperationID+")")
			}
		}
	}
	if total == 0 {
		t.Fatal("no operations found in the contract")
	}
	if len(missing) > 0 {
		sort.Strings(missing)
		t.Errorf("%d of %d operations have no method on *generated.Client:\n  %s",
			len(missing), total, strings.Join(missing, "\n  "))
	}
}

func TestOverlayStillNeeded(t *testing.T) {
	raw, _ := readContract(t)
	if !strings.Contains(string(raw), `"/unreadableFiles"`) {
		t.Fatal("upstream fixed /unreadableFiles: delete generated/overlay.yaml and its config key")
	}
}

func TestServerVersionMatchesContract(t *testing.T) {
	_, doc := readContract(t)
	if arcadedb.ServerVersion != doc.Info.Version {
		t.Fatalf("ServerVersion = %q, contract info.version = %q", arcadedb.ServerVersion, doc.Info.Version)
	}
}
