"""Optional docker-exec-level sanity checks.

Run when both:
  - the `docker` CLI is available on PATH
  - `LIVE_CONTAINER_NAME` is set (e.g. `fire_demo3_v3_backend`)

Otherwise every test skips. These catch the class of bugs we hit multiple
times where the container's view of a file didn't match the host's after
a symlink swap / bind-mount rebind."""
from __future__ import annotations

import os
import shutil
import subprocess

import pytest


CONTAINER = os.environ.get("LIVE_CONTAINER_NAME")
HOST_DATA_DIR = os.environ.get("LIVE_HOST_DATA_DIR")


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()


pytestmark = pytest.mark.skipif(
    not _docker_available() or not CONTAINER,
    reason=(
        "docker CLI or LIVE_CONTAINER_NAME missing. Set LIVE_CONTAINER_NAME "
        "(e.g. fire_demo3_v3_backend) to enable these checks."
    ),
)


def test_container_reads_expected_csv_headers():
    """The container's view of the CSVs the C++ simulator will read must
    have the split-chief header (Suppression_Chief, EMS_Chief)."""
    for name in ("stations_with_apparatus.csv", "NFDResponse.csv"):
        header = _run([
            "docker", "exec", CONTAINER, "head", "-1", f"/app/data/{name}",
        ])
        assert "Suppression_Chief" in header, (
            f"{name}: missing Suppression_Chief in header: {header!r}"
        )
        assert "EMS_Chief" in header, (
            f"{name}: missing EMS_Chief in header: {header!r}"
        )
        assert "\r" not in header, (
            f"{name}: CRLF line endings detected in the container-visible "
            f"file — the simulator will crash on the last field of every row "
            f"with std::stoi invalid_argument. Fix on host with `sed -i "
            f"'s/\\r$//' data/{name}` and restart the stack."
        )


@pytest.mark.skipif(not HOST_DATA_DIR, reason="LIVE_HOST_DATA_DIR not set")
def test_bind_mount_inodes_match_host():
    """Bind mount must be pointing at the current host directory, not a
    stale symlink target left over from a previous compose down/up. Compares
    inodes across the veil."""
    for name in ("stations_with_apparatus.csv", "NFDResponse.csv"):
        container_inode = _run([
            "docker", "exec", CONTAINER, "stat", "-c", "%i", f"/app/data/{name}",
        ])
        host_inode = _run([
            "stat", "-c", "%i", os.path.join(HOST_DATA_DIR, name),
        ])
        assert container_inode == host_inode, (
            f"{name}: bind-mount stale.\n"
            f"  container sees inode {container_inode}\n"
            f"  host {HOST_DATA_DIR}/{name} inode {host_inode}\n"
            f"  fix: `docker compose down && docker compose up -d` to rebind."
        )


def test_container_can_reach_osrm():
    """The simulator's `--OSRM_URL` target must actually respond from
    inside the container. If the container can't reach OSRM, every
    dispatch call fails silently and the job dies with `OSRMError`."""
    # Read the effective OSRM host/port from env.
    env = _run(["docker", "exec", CONTAINER, "printenv"])
    host = "host.docker.internal"
    port = "8085"
    for line in env.splitlines():
        if line.startswith("OSRM_HOST="):
            host = line.split("=", 1)[1]
        elif line.startswith("OSRM_PORT="):
            port = line.split("=", 1)[1]

    url = f"http://{host}:{port}/route/v1/driving/-86.78,36.16;-86.66,36.15"
    try:
        _run([
            "docker", "exec", CONTAINER, "curl", "-fsS", "-m", "5",
            "-o", "/dev/null", "-w", "http=%{http_code}", url,
        ])
    except subprocess.CalledProcessError as e:
        pytest.fail(
            f"container cannot reach OSRM at {url}\n"
            f"  curl output: {e.output}\n"
            f"  fix: verify OSRM is running on the host at {host}:{port}, and\n"
            f"       that host.docker.internal:host-gateway is in extra_hosts."
        )


def test_container_binary_is_executable_for_current_arch():
    """The `data/fire_simulator` bind-mounted binary has to be an ELF for
    the container's arch — catches the 'shipped a macOS binary' class of
    bug we hit repeatedly."""
    filed = _run([
        "docker", "exec", CONTAINER, "file", "/app/data/fire_simulator",
    ])
    arch = _run(["docker", "exec", CONTAINER, "uname", "-m"])
    expected_tokens = {"x86_64": ("x86-64",), "aarch64": ("aarch64",),
                       "arm64": ("aarch64",)}
    tokens = expected_tokens.get(arch, ())
    assert any(tok in filed for tok in tokens), (
        f"fire_simulator arch mismatch:\n"
        f"  file(1) says : {filed}\n"
        f"  container arch: {arch}\n"
        f"  fix: rebuild the C++ binary on this host and drop into data/."
    )
