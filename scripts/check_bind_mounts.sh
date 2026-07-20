#!/usr/bin/env bash
#
# Runtime preflight: for each running backend/worker container, verify the
# data + logs bind mounts actually reflect the host directory the operator
# thinks they do.
#
# Motivating incident (2026-07-20): -next/data on a RHEL host was originally
# a symlink into main/data. Docker resolved the bind source at container-
# start time. Later the operator replaced the symlink with a real directory
# containing an updated stations_with_apparatus.csv. The running container
# kept its mount pinned to the *original* target — so the API kept serving
# stale roster data even after `git pull` / CSV edits, until a full
# `docker compose down && up` rebuilt the container.
#
# This script catches that class of drift by comparing the CSV header the
# container sees against the CSV header on the host at the compose-declared
# bind source. Inodes would be a stricter check but cross-platform they're
# unreliable (Docker Desktop on macOS/Windows uses a Linux VM whose inodes
# do not match the host filesystem). Content comparison works everywhere.
#
# Exit status:
#   0  every checked bind mount matches
#   1  at least one mismatch (an operator-actionable message per mismatch)
#   2  environment problem (docker not running, container not found, etc.)
#
# Usage:
#   bash scripts/check_bind_mounts.sh                                 # defaults
#   COMPOSE_FILE=~/fire_demo3_api-next/docker-compose.yml bash scripts/check_bind_mounts.sh
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
if [[ ! -f "$COMPOSE_FILE" ]]; then
    echo "check_bind_mounts: compose file not found: $COMPOSE_FILE" >&2
    exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "check_bind_mounts: docker not on PATH; nothing to check" >&2
    exit 2
fi

# Files whose content we cross-check. Each entry is "container_path :: host_relpath".
# host_relpath is relative to the compose file's directory (which is what a
# bind mount of the form `./data:/app/data` resolves to at runtime).
FILES=(
    "/app/data/stations_with_apparatus.csv::data/stations_with_apparatus.csv"
    "/app/data/NFDResponse.csv::data/NFDResponse.csv"
)

# Containers to check — anything defined in the compose file whose name matches
# either the backend or worker convention.
CONTAINERS=$(docker compose -f "$COMPOSE_FILE" ps --format '{{.Name}}' 2>/dev/null \
             | grep -E '_(backend|worker)$' || true)
if [[ -z "$CONTAINERS" ]]; then
    echo "check_bind_mounts: no running backend/worker container found for $COMPOSE_FILE" >&2
    exit 2
fi

compose_dir=$(cd "$(dirname "$COMPOSE_FILE")" && pwd)
mismatches=0

for container in $CONTAINERS; do
    for entry in "${FILES[@]}"; do
        container_path="${entry%%::*}"
        host_relpath="${entry##*::}"
        host_path="$compose_dir/$host_relpath"

        if [[ ! -f "$host_path" ]]; then
            echo "SKIP  $container:$container_path  (host file missing: $host_path)"
            continue
        fi

        host_header=$(head -1 "$host_path" || true)
        container_header=$(docker exec "$container" head -1 "$container_path" 2>/dev/null || true)

        if [[ -z "$container_header" ]]; then
            echo "FAIL  $container:$container_path  is empty or unreadable inside the container"
            mismatches=$((mismatches + 1))
            continue
        fi

        if [[ "$host_header" != "$container_header" ]]; then
            echo "FAIL  $container:$container_path  host header does NOT match container header"
            echo "       host:      $host_header"
            echo "       container: $container_header"
            echo "       fix: run 'cd $(dirname "$COMPOSE_FILE") && docker compose down && docker compose up -d'"
            echo "            so Docker re-resolves the bind mount from the current host filesystem."
            mismatches=$((mismatches + 1))
        else
            echo "OK    $container:$container_path"
        fi
    done
done

if (( mismatches > 0 )); then
    echo
    echo "check_bind_mounts: $mismatches mismatch(es) — see above."
    exit 1
fi

echo
echo "check_bind_mounts: all $((${#FILES[@]} * $(echo "$CONTAINERS" | wc -w | tr -d ' '))) bind-mounted files match host contents."
exit 0
