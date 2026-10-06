#!/usr/bin/env bash
#
# Fetches the ArcadeDB contracts into contracts/: the OpenAPI spec (written as
# a jq -S normalised copy) and, in --release and --proto-from modes, the gRPC
# .proto. Every generated client, in every language this repository will ever
# host, derives from the files this script writes.
#
# Three modes:
#   --release <tag>   Downloads BOTH contracts from the matching GitHub release,
#                      arcadedb-openapi-<tag>.json and arcadedb-server-<tag>.proto,
#                      and verifies each against its published .sha256 checksum.
#                      Both or neither: nothing is written to contracts/ until
#                      both assets are present and both checksums pass, and the
#                      .proto is written only after the OpenAPI spec has passed
#                      the post-M0 gate below. A release that predates the
#                      .proto asset is refused rather than half-fetched; use
#                      --proto-from for it.
#   --image <image-reference>
#                      Starts the given Docker image on an
#                      ephemeral host port, waits for /api/v1/ready, and fetches
#                      /api/v1/openapi.json using a root password the script
#                      sets on the container itself.
#   --proto-from <path-to-arcadedb-checkout> [<version>]
#                      Copies grpc/src/main/proto/arcadedb-server.proto out of a
#                      local arcadedb checkout. A running server does not serve
#                      its own .proto, so --image cannot supply this the way it
#                      supplies the OpenAPI spec; for an unreleased (SNAPSHOT)
#                      build, which has no release assets, the checkout is the
#                      only source. The copy is named with the version the OpenAPI
#                      contract already carries (read from the existing
#                      contracts/arcadedb-openapi-*.json), so the REST and gRPC
#                      contracts stay legible as one pair. Pass <version>
#                      explicitly when a bump is in flight and two OpenAPI specs
#                      are momentarily present, which makes that derivation
#                      impossible.
#
# In the --release and --image modes, the resulting spec is refused unless it
# is structurally provably post-M0: the /api/v1/begin/{database} 204 response
# must carry the arcadedb-session-id header. A version string proves nothing
# about content; this marker cannot be true of any pre-M0 spec. The .proto,
# from either --release or --proto-from, is source text rather than JSON, so no
# such gate applies to it - the checksum (--release) or the version match
# against the OpenAPI contract (--proto-from) is the check.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONTRACTS_DIR="$REPO_ROOT/contracts"
GITHUB_REPO="ArcadeData/arcadedb"

usage() {
  echo "Usage: $0 --release <tag>" >&2
  echo "       $0 --image <image-reference>   e.g. arcadedata/arcadedb:26.9.1-SNAPSHOT" >&2
  echo "       $0 --proto-from <path-to-arcadedb-checkout> [<version>]" >&2
  exit 1
}

MODE=""
TARGET=""
EXPLICIT_VERSION=""

if [[ $# -lt 2 || $# -gt 3 ]]; then
  usage
fi

case "$1" in
  --release)
    MODE="release"
    ;;
  --image)
    MODE="image"
    ;;
  --proto-from)
    MODE="proto-from"
    ;;
  *)
    usage
    ;;
esac
TARGET="$2"
EXPLICIT_VERSION="${3:-}"

if [[ -n "$EXPLICIT_VERSION" && "$MODE" != "proto-from" ]]; then
  echo "ERROR: a version argument is only meaningful with --proto-from." >&2
  usage
fi

mkdir -p "$CONTRACTS_DIR"

CLEANUP_TMP_DIR=""
CLEANUP_CONTAINER=""

cleanup() {
  if [[ -n "$CLEANUP_CONTAINER" ]]; then
    docker rm -f "$CLEANUP_CONTAINER" > /dev/null 2>&1 || true
  fi
  if [[ -n "$CLEANUP_TMP_DIR" ]]; then
    rm -rf "$CLEANUP_TMP_DIR"
  fi
}
trap cleanup EXIT

RAW_SPEC=""
VERSION_TAG=""

RAW_PROTO=""

if [[ "$MODE" == "release" ]]; then
  VERSION_TAG="$TARGET"
  ASSET_NAME="arcadedb-openapi-${VERSION_TAG}.json"
  PROTO_ASSET_NAME="arcadedb-server-${VERSION_TAG}.proto"

  TMP_DIR="$(mktemp -d)"
  CLEANUP_TMP_DIR="$TMP_DIR"

  echo "Downloading ${ASSET_NAME} and ${PROTO_ASSET_NAME} from release ${VERSION_TAG}..." >&2
  gh release download "$VERSION_TAG" \
    --repo "$GITHUB_REPO" \
    --pattern "$ASSET_NAME" \
    --pattern "${ASSET_NAME}.sha256" \
    --pattern "$PROTO_ASSET_NAME" \
    --pattern "${PROTO_ASSET_NAME}.sha256" \
    --dir "$TMP_DIR"

  # gh exits 0 as long as ANY pattern matched, so a release missing one asset
  # downloads the rest silently. Check each one, before anything is written.
  for asset in "$ASSET_NAME" "${ASSET_NAME}.sha256" "$PROTO_ASSET_NAME" "${PROTO_ASSET_NAME}.sha256"; do
    if [[ ! -f "$TMP_DIR/$asset" ]]; then
      echo "ERROR: release ${VERSION_TAG} has no ${asset} asset; nothing was written." >&2
      if [[ "$asset" == "$PROTO_ASSET_NAME"* ]]; then
        echo "For a release that predates the .proto asset, copy the .proto from an arcadedb" >&2
        echo "checkout at that tag: $0 --proto-from <checkout> ${VERSION_TAG}" >&2
      fi
      exit 1
    fi
  done

  echo "Verifying checksums..." >&2
  (cd "$TMP_DIR" && shasum -a 256 -c "${ASSET_NAME}.sha256" && shasum -a 256 -c "${PROTO_ASSET_NAME}.sha256")

  RAW_SPEC="$TMP_DIR/$ASSET_NAME"
  RAW_PROTO="$TMP_DIR/$PROTO_ASSET_NAME"

elif [[ "$MODE" == "image" ]]; then
  IMAGE="$TARGET"
  VERSION_TAG="${IMAGE##*:}"

  CONTAINER_NAME="arcadedb-contract-fetch-$$"
  ROOT_PASSWORD="contract-fetch-$$-$(date +%s)"
  CLEANUP_CONTAINER="$CONTAINER_NAME"

  echo "Starting ${IMAGE} as ${CONTAINER_NAME} on an ephemeral host port..." >&2
  # Bind to an ephemeral host port (never 2480: a developer machine may
  # already have ArcadeDB listening there).
  docker run -d \
    --name "$CONTAINER_NAME" \
    -p 127.0.0.1::2480 \
    -e JAVA_OPTS="-Darcadedb.server.rootPassword=${ROOT_PASSWORD}" \
    "$IMAGE" > /dev/null

  HOST_PORT="$(docker inspect \
    --format='{{(index (index .NetworkSettings.Ports "2480/tcp") 0).HostPort}}' \
    "$CONTAINER_NAME")"
  BASE_URL="http://127.0.0.1:${HOST_PORT}"

  echo "Waiting for ${IMAGE} to become ready on ${BASE_URL}..." >&2
  ATTEMPTS=0
  MAX_ATTEMPTS=90
  until [[ "$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/api/v1/ready" || true)" == "204" ]]; do
    ATTEMPTS=$((ATTEMPTS + 1))
    if [[ "$ATTEMPTS" -ge "$MAX_ATTEMPTS" ]]; then
      echo "ERROR: ${IMAGE} did not become ready within $((MAX_ATTEMPTS * 2))s" >&2
      docker logs "$CONTAINER_NAME" >&2 || true
      exit 1
    fi
    sleep 2
  done

  TMP_DIR="$(mktemp -d)"
  CLEANUP_TMP_DIR="$TMP_DIR"
  RAW_SPEC="$TMP_DIR/openapi.json"

  echo "Fetching /api/v1/openapi.json..." >&2
  # The spec endpoint requires authentication (GetOpenApiHandler.isRequireAuthentication()
  # returns true), so use the root password this script just set on the container.
  curl --fail -s -u "root:${ROOT_PASSWORD}" "${BASE_URL}/api/v1/openapi.json" -o "$RAW_SPEC"

elif [[ "$MODE" == "proto-from" ]]; then
  ARCADEDB_CHECKOUT="$TARGET"
  SOURCE_PROTO="$ARCADEDB_CHECKOUT/grpc/src/main/proto/arcadedb-server.proto"

  if [[ ! -f "$SOURCE_PROTO" ]]; then
    echo "ERROR: no proto at $SOURCE_PROTO" >&2
    echo "Pass the path to an arcadedb checkout containing grpc/src/main/proto/arcadedb-server.proto." >&2
    exit 1
  fi

  # An explicit version short-circuits the derivation below. That is not a
  # convenience: DURING A VERSION BUMP the derivation cannot work. --image has
  # just written the new spec beside the old one, so there are two, and deriving
  # a version by insisting on exactly one would abort here - in the one scenario
  # this whole pipeline exists to handle. The caller that knows the target
  # version (contract-watch.yml reads it from arcadedb's pom) passes it.
  if [[ -n "$EXPLICIT_VERSION" ]]; then
    PROTO_OUT="$CONTRACTS_DIR/arcadedb-server-${EXPLICIT_VERSION}.proto"
    cp "$SOURCE_PROTO" "$PROTO_OUT"
    echo "Wrote $PROTO_OUT" >&2
    exit 0
  fi

  # Reuse the version the OpenAPI contract already carries, so the REST and
  # gRPC contracts stay legible as one pair rather than drifting apart.
  shopt -s nullglob
  EXISTING_OPENAPI_SPECS=("$CONTRACTS_DIR"/arcadedb-openapi-*.json)
  shopt -u nullglob
  if [[ "${#EXISTING_OPENAPI_SPECS[@]}" -eq 0 ]]; then
    echo "ERROR: no contracts/arcadedb-openapi-*.json found to read the version from." >&2
    echo "Run this script's --release or --image mode first." >&2
    exit 1
  fi
  if [[ "${#EXISTING_OPENAPI_SPECS[@]}" -ne 1 ]]; then
    echo "ERROR: expected exactly one contracts/arcadedb-openapi-*.json, found ${#EXISTING_OPENAPI_SPECS[@]}:" >&2
    printf '  %s\n' "${EXISTING_OPENAPI_SPECS[@]}" >&2
    exit 1
  fi
  OPENAPI_BASENAME="$(basename "${EXISTING_OPENAPI_SPECS[0]}")"
  VERSION_TAG="${OPENAPI_BASENAME#arcadedb-openapi-}"
  VERSION_TAG="${VERSION_TAG%.json}"

  PROTO_OUT="$CONTRACTS_DIR/arcadedb-server-${VERSION_TAG}.proto"
  cp "$SOURCE_PROTO" "$PROTO_OUT"
  echo "Wrote $PROTO_OUT" >&2
  exit 0
fi

OUT="$CONTRACTS_DIR/arcadedb-openapi-${VERSION_TAG}.json"
jq -S . "$RAW_SPEC" > "$OUT"

# Refuse a contract we cannot confirm is post-M0. Structural check, not a
# version-string comparison: M0 both moved begin's success response to 204
# and attached the session header to it, so the presence of that header
# under the 204 key cannot be true of any pre-M0 spec.
if ! jq -e '.paths."/api/v1/begin/{database}".post.responses."204".headers."arcadedb-session-id"' \
     "$OUT" > /dev/null; then
  echo "REFUSING: this spec predates the M0 contract fixes." >&2
  echo "It lacks the arcadedb-session-id response header on beginTransaction, which means it also" >&2
  echo "declares 200 where the server sends 204 and leaves PromQL results untyped." >&2
  echo "A client generated from it cannot use transactions. Use a server at or after fa599b7516." >&2
  rm -f "$OUT"
  exit 1
fi

echo "Wrote $OUT" >&2

# Only now, with the OpenAPI spec through its gate, does the .proto land: a
# refused spec must not leave its .proto behind as half of a contract pair.
if [[ -n "$RAW_PROTO" ]]; then
  PROTO_OUT="$CONTRACTS_DIR/arcadedb-server-${VERSION_TAG}.proto"
  cp "$RAW_PROTO" "$PROTO_OUT"
  echo "Wrote $PROTO_OUT" >&2
fi
