package arcadedbgrpc_test

import (
	"os"
	"path/filepath"
	"reflect"
	"regexp"
	"sort"
	"strings"
	"testing"

	"github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc"
	"github.com/ArcadeData/arcadedb-drivers/go/arcadedbgrpc/generated"
)

// findProto walks up from the test's working directory to the directory holding contracts/
// and returns the single arcadedb-server-*.proto in it. It skips the test when no contract
// is found (for example when the module is vendored outside the repository).
func findProto(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	for {
		if st, err := os.Stat(filepath.Join(dir, "contracts")); err == nil && st.IsDir() {
			matches, err := filepath.Glob(filepath.Join(dir, "contracts", "arcadedb-server-*.proto"))
			if err != nil {
				t.Fatalf("glob: %v", err)
			}
			switch len(matches) {
			case 0:
				t.Skip("contracts/ holds no arcadedb-server-*.proto")
			case 1:
				return matches[0]
			default:
				t.Fatalf("contracts/ must hold exactly one .proto contract, found %d: %v", len(matches), matches)
			}
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Skip("no contracts/ directory found above the working directory")
		}
		dir = parent
	}
}

var (
	serviceRe = regexp.MustCompile(`(?m)^\s*service\s+(\w+)\s*\{`)
	rpcRe     = regexp.MustCompile(`\brpc\s+(\w+)\s*\(`)
)

var commentRe = regexp.MustCompile(`(?s)/\*.*?\*/|//[^\n]*`)

// stripComments removes // line comments and /* */ blocks so a brace or an "rpc Foo (" in a
// comment cannot truncate a service block or invent an RPC. Contract strings holding "//"
// (URLs in option values) are harmless here: only RPC names and braces are read.
func stripComments(src string) string { return commentRe.ReplaceAllString(src, "") }

// parseServices returns, per service name, the RPC names declared in its block. A block
// runs from the service's opening brace to the next top-level closing brace; the contract
// declares no nested braces inside a service except the occasional `{}` option body, so
// brace depth is tracked rather than assuming the first `}` closes it.
func parseServices(src string) map[string][]string {
	src = stripComments(src)
	out := map[string][]string{}
	for _, m := range serviceRe.FindAllStringSubmatchIndex(src, -1) {
		name := src[m[2]:m[3]]
		depth, end := 1, len(src)
		for i := m[1]; i < len(src); i++ {
			switch src[i] {
			case '{':
				depth++
			case '}':
				depth--
			}
			if depth == 0 {
				end = i
				break
			}
		}
		for _, r := range rpcRe.FindAllStringSubmatch(src[m[1]:end], -1) {
			out[name] = append(out[name], r[1])
		}
	}
	return out
}

// missingMethods returns the RPC names in rpcs that iface has no method for, sorted.
func missingMethods(iface reflect.Type, rpcs []string) []string {
	var missing []string
	for _, name := range rpcs {
		if _, ok := iface.MethodByName(name); !ok {
			missing = append(missing, name)
		}
	}
	sort.Strings(missing)
	return missing
}

func TestEveryRPCIsGenerated(t *testing.T) {
	raw, err := os.ReadFile(findProto(t))
	if err != nil {
		t.Fatalf("read proto: %v", err)
	}
	services := parseServices(string(raw))

	clients := map[string]reflect.Type{
		"ArcadeDbService":      reflect.TypeOf((*generated.ArcadeDbServiceClient)(nil)).Elem(),
		"ArcadeDbAdminService": reflect.TypeOf((*generated.ArcadeDbAdminServiceClient)(nil)).Elem(),
	}
	for svc, iface := range clients {
		rpcs := services[svc]
		if want := map[string]int{"ArcadeDbService": 21, "ArcadeDbAdminService": 44}[svc]; len(rpcs) != want {
			t.Errorf("%s: parsed %d RPCs, want %d; if the contract grew, update this count deliberately", svc, len(rpcs), want)
		}
		if len(rpcs) == 0 {
			t.Fatalf("found no RPCs for service %s in the contract; the parser or the contract changed", svc)
		}
		if missing := missingMethods(iface, rpcs); len(missing) > 0 {
			t.Errorf("%s: %d of %d RPCs are not generated on the client interface: %s",
				svc, len(missing), len(rpcs), strings.Join(missing, ", "))
		}
		t.Logf("%s: %d RPCs", svc, len(rpcs))
	}

	t.Run("parser ignores comments", func(t *testing.T) {
		src := "service S {\n  // rpc Commented (A) returns (B);\n  // stray { brace\n  rpc Real (A) returns (B);\n  /* rpc Block (A) returns (B); } */\n  rpc Real2 (A) returns (B);\n}\n"
		got := parseServices(src)["S"]
		if len(got) != 2 || got[0] != "Real" || got[1] != "Real2" {
			t.Fatalf("parser found %v, want [Real Real2]", got)
		}
	})

	t.Run("parser reports an RPC no interface has", func(t *testing.T) {
		fake := "service ArcadeDbService {\n  rpc ExecuteQuery (Req) returns (Resp);\n  rpc NoSuchRpcAnywhere (Req) returns (Resp);\n}\n"
		got := parseServices(fake)["ArcadeDbService"]
		if len(got) != 2 {
			t.Fatalf("parser found %v, want 2 RPCs", got)
		}
		missing := missingMethods(clients["ArcadeDbService"], got)
		if len(missing) != 1 || missing[0] != "NoSuchRpcAnywhere" {
			t.Fatalf("missing = %v, want [NoSuchRpcAnywhere]", missing)
		}
	})
}

func TestServerVersionMatchesProto(t *testing.T) {
	name := filepath.Base(findProto(t))
	want := strings.TrimSuffix(strings.TrimPrefix(name, "arcadedb-server-"), ".proto")
	if arcadedbgrpc.ServerVersion != want {
		t.Fatalf("ServerVersion = %q, but the contract file %s carries version %q; run scripts/adopt-contract-version.sh",
			arcadedbgrpc.ServerVersion, name, want)
	}
}
