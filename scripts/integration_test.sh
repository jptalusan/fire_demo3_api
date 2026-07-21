#!/usr/bin/env bash
#
# scripts/integration_test.sh - throwaway end-to-end integration test.
#
# EVERYTHING runs inside a temp dir under $HOME. An existing deployment
# (SRC_DEPLOY) is used ONLY as a read-only source for the gitignored data
# assets -- the script never executes anything in it, never writes to it, and
# never brings its stack up/down. The one filesystem touch on SRC_DEPLOY is a
# `cp -r data/` (+ `cp .env`). If that still feels too coupled, point
# SRC_DEPLOY at any read-only copy of the data assets instead of a live deploy.
#
# Flow: clone the code fresh into the temp dir, copy in the gitignored heavy
# artifacts (data/ incl. the container-compatible fire_simulator binary, plus
# .env) from SRC_DEPLOY, bring up an ISOLATED docker stack on its own port +
# container names + compose project (so it cannot touch a live /v2/ or /v3/),
# run the full backend live suite and a frontend build check, and delete the
# temp dir IFF everything passes. On failure it leaves the stack + dir up.
#
# Why the binary is copied, not built here: it runs inside the Debian-based
# container, so it must be built in a Debian-compatible environment. A binary
# compiled on the RHEL host links RHEL's glibc and can fail with
# 'GLIBC_2.xx not found' inside the container. The binary in SRC_DEPLOY/data
# is the one proven to work in that container, so copying it is the safe path.
# (To rebuild for the container, use the in-image multi-stage build instead.)
#
# Usage:
#   scripts/integration_test.sh
#   SRC_DEPLOY=~/fire_demo3_api BACKEND_PORT=8011 scripts/integration_test.sh
#
# Env knobs (all optional -- defaults shown):
#   SRC_DEPLOY   ~/fire_demo3_api-next   existing deploy w/ data/ + binary + .env
#   REPO         https://github.com/jptalusan/fire_demo3_api.git
#   BRANCH       backend-v2
#   PROJECT      fdemo3test              compose project namespace
#   BACKEND_PORT 8010                    host port for the test stack
#   SKIP_FRONTEND  (unset)               set to 1 to skip the npm build step
#
# Prereqs on the host: git, docker compose, uv (for pytest), and npm if you
# want the frontend build. OSRM is shared with the live stacks via the copied
# .env (read-only use), so no second OSRM is spun up.
#
# Exit codes: 0 = all passed (and cleaned up); non-zero = something failed
# (stack + temp dir left in place for debugging).

set -uo pipefail

SRC_DEPLOY="${SRC_DEPLOY:-$HOME/fire_demo3_api-next}"
REPO="${REPO:-https://github.com/jptalusan/fire_demo3_api.git}"
BRANCH="${BRANCH:-backend-v2}"
PROJECT="${PROJECT:-fdemo3test}"
BACKEND_PORT="${BACKEND_PORT:-8010}"

die() { echo "ERROR: $*" >&2; exit 1; }

# --------------------------------------------------------------------------- #
# Preconditions
# --------------------------------------------------------------------------- #
command -v git   >/dev/null || die "git not found"
command -v docker >/dev/null || die "docker not found"
command -v uv    >/dev/null || die "uv not found (needed for pytest); or edit step 6 to use a venv"
[ -d "$SRC_DEPLOY/data" ] || die "SRC_DEPLOY has no data/ dir: $SRC_DEPLOY"
[ -f "$SRC_DEPLOY/data/fire_simulator" ] || die "no fire_simulator binary under $SRC_DEPLOY/data/"
[ -f "$SRC_DEPLOY/.env" ] || die "no .env under $SRC_DEPLOY"

TEST_DIR="$(mktemp -d "$HOME/fdemo3_test.XXXXXX")"
echo ">>> test dir:        $TEST_DIR   (everything runs here)"
echo ">>> data source:     $SRC_DEPLOY   (READ-ONLY copy of data/ + .env; not executed, not modified)"
echo ">>> project:         $PROJECT   port: $BACKEND_PORT"

# --------------------------------------------------------------------------- #
# 1. Fresh code checkout
# --------------------------------------------------------------------------- #
git clone --depth 1 -b "$BRANCH" "$REPO" "$TEST_DIR/app" || die "git clone failed"
cd "$TEST_DIR/app"

# --------------------------------------------------------------------------- #
# 2. Bring in gitignored artifacts (full copy = true isolation; synthetic-CSV
#    writes during the test won't touch the live deployment's data).
# --------------------------------------------------------------------------- #
echo ">>> copying data/ (models, CSVs, binary) -- may take a moment"
cp -r "$SRC_DEPLOY/data" ./data || die "copy data/ failed"
cp "$SRC_DEPLOY/.env" ./.env
mkdir -p storage logs

# FIREBEATS dispatch reads logs/beats.bin (the precomputed run-order matrix).
# It lives under logs/, not data/, so a fresh logs/ dir would leave FIREBEATS
# jobs failing with "status=error with no message" while NEAREST works. Carry
# the beats matrix over from the source deploy if present.
if [ -f "$SRC_DEPLOY/logs/beats.bin" ]; then
  cp "$SRC_DEPLOY/logs/beats.bin" ./logs/beats.bin
  echo ">>> copied logs/beats.bin (FIREBEATS dispatch matrix)"
else
  echo "WARN: $SRC_DEPLOY/logs/beats.bin not found -- FIREBEATS jobs will fail; NEAREST unaffected"
fi

# Drop any cached synthetic-incident CSVs carried in from the source deploy.
# Old caches predate the datetime/comma/category fixes and get served as-is by
# /api/incidents/generate-incidents (it returns the cached file if present),
# which would resurface already-fixed bugs. Force regeneration with current code.
rm -rf ./data/incidents/synthetic 2>/dev/null || true
echo ">>> cleared cached synthetic incident CSVs (force regeneration)"

# Sanity: binary + split-format CSVs must line up, else jobs will fail.
file ./data/fire_simulator | grep -qiE "ELF|Mach-O" || die "data/fire_simulator is not an executable"
head -1 ./data/NFDResponse.csv | grep -q "Suppression_Chief" \
  || echo "WARN: NFDResponse.csv is not split-format -- binary must be a pre-chief build for this to work"

# --------------------------------------------------------------------------- #
# 3. Isolate from the running stacks: unique container names + host port.
#    (compose hardcodes fire_demo3_v2_* container names and 8000:8000)
# --------------------------------------------------------------------------- #
sed -i 's/fire_demo3_v2_/fire_demo3_test_/g' docker-compose.yml
sed -i "s/\"8000:8000\"/\"${BACKEND_PORT}:8000\"/" docker-compose.yml

# --------------------------------------------------------------------------- #
# 4. Bring the test stack up in its own compose project namespace.
# --------------------------------------------------------------------------- #
echo ">>> building + starting test stack"
sudo docker compose -p "$PROJECT" up -d --build || die "docker compose up failed"

# --------------------------------------------------------------------------- #
# 5. Wait for health (up to ~2 min).
# --------------------------------------------------------------------------- #
echo -n ">>> waiting for /health "
HEALTHY=0
for _ in $(seq 1 60); do
  if curl -sf "http://localhost:${BACKEND_PORT}/health" >/dev/null 2>&1; then HEALTHY=1; echo " ok"; break; fi
  echo -n "."; sleep 2
done
[ "$HEALTHY" -eq 1 ] || { echo; echo ">>> health never came up; leaving stack for inspection"; \
  echo "    sudo docker compose -p $PROJECT logs --tail 80"; exit 1; }

# --------------------------------------------------------------------------- #
# 6. BACKEND: full live integration suite.
# --------------------------------------------------------------------------- #
echo ">>> backend live tests"
LIVE_BASE_URL="http://localhost:${BACKEND_PORT}" \
LIVE_CONTAINER_NAME="fire_demo3_test_backend" \
LIVE_HOST_DATA_DIR="$TEST_DIR/app/data" \
  uv run --with pytest --with pandas --with numpy --with fastapi \
         --with 'pydantic>=2' --with pydantic-settings --with sqlalchemy \
    pytest tests/live -v
BACKEND_RC=$?

# --------------------------------------------------------------------------- #
# 7. FRONTEND: build check (compiles against the API contract).
# --------------------------------------------------------------------------- #
FRONTEND_RC=0
if [ -n "${SKIP_FRONTEND:-}" ]; then
  echo ">>> SKIP_FRONTEND set -- skipping frontend build"
elif [ -d frontend ] && command -v npm >/dev/null; then
  echo ">>> frontend build"
  ( cd frontend && npm ci && npm run build )
  FRONTEND_RC=$?
else
  echo ">>> no frontend/ dir or npm missing -- skipping frontend build"
fi

# --------------------------------------------------------------------------- #
# 8. Gate: clean up IFF both passed; otherwise leave everything for debugging.
# --------------------------------------------------------------------------- #
echo ">>> results: backend_rc=$BACKEND_RC frontend_rc=$FRONTEND_RC"
if [ "$BACKEND_RC" -eq 0 ] && [ "$FRONTEND_RC" -eq 0 ]; then
  echo ">>> ALL PASSED -- tearing down + deleting $TEST_DIR"
  sudo docker compose -p "$PROJECT" down -v
  cd "$HOME"
  rm -rf "$TEST_DIR"
  echo ">>> clean. integration test passed."
  exit 0
else
  echo ">>> FAILURES -- leaving stack + dir up for inspection:"
  echo "    logs:  sudo docker compose -p $PROJECT logs --tail 80"
  echo "    dir:   $TEST_DIR"
  echo "    clean: sudo docker compose -p $PROJECT down -v && rm -rf $TEST_DIR"
  exit 1
fi
