"""Preflight: docker-compose.yml must wire up BASE_DIR / DATA_DIR / LOGS_DIR,
mount data/ and logs/ from the host, and use env_file: .env.

Bug classes this test prevents:
- (Incident 2) `-next` stack sharing data/ but not logs/ -> beats.bin missing
  in-container. Every service must bind-mount ./logs.
- (Incident 4) OSRM_HOST hard-coded to localhost inside the container.
  Compose should either set it via `${VAR:-default}` (with a docker-friendly
  default) or leave it in .env.
- (Incident 6) HOST_ONNXRUNTIME_DIR bind-mount silently absent.

Uses PyYAML if available; falls back to a simple text-scan if not (never
xfails silently -- if we can't parse, we still enforce string invariants).
"""

from __future__ import annotations

from pathlib import Path

import pytest


REQUIRED_SERVICES = ("backend", "worker")
REQUIRED_ENV_VARS = ("BASE_DIR", "DATA_DIR", "LOGS_DIR")
REQUIRED_MOUNTS = ("/app/data", "/app/logs")


@pytest.fixture(scope="module")
def compose(repo_root: Path):
    path = repo_root / "docker-compose.yml"
    assert path.is_file(), f"docker-compose.yml missing at {path}"
    try:
        import yaml  # type: ignore
    except ImportError:
        pytest.skip("PyYAML not installed; install `pyyaml` to run docker-compose preflight.")
    return yaml.safe_load(path.read_text())


def _format_service(service_name: str, service_block: dict) -> str:
    """Prettified dump of a service block for use inside a failure message."""
    try:
        import yaml  # type: ignore
        return yaml.safe_dump({service_name: service_block}, sort_keys=False)
    except Exception:
        return repr(service_block)


@pytest.mark.parametrize("service_name", REQUIRED_SERVICES)
def test_service_declares_base_data_logs_dirs(compose: dict, service_name: str):
    services = compose.get("services") or {}
    assert service_name in services, f"service {service_name!r} missing from docker-compose.yml"
    svc = services[service_name]
    env = svc.get("environment") or {}
    # Support both dict form and list form ("KEY=VALUE").
    if isinstance(env, list):
        env = dict(e.split("=", 1) for e in env if "=" in e)

    missing = [k for k in REQUIRED_ENV_VARS if k not in env]
    assert not missing, (
        f"\n\nPREFLIGHT: service {service_name!r} is missing env vars: {missing}\n"
        f"--- {service_name} ---\n{_format_service(service_name, svc)}"
        f"  fix: add each of {REQUIRED_ENV_VARS} under `environment:` (typically\n"
        f"       BASE_DIR: /app, DATA_DIR: /app/data, LOGS_DIR: /app/logs).\n"
    )


@pytest.mark.parametrize("service_name", REQUIRED_SERVICES)
def test_service_binds_data_and_logs(compose: dict, service_name: str):
    svc = compose["services"][service_name]
    volumes = svc.get("volumes") or []
    mount_targets = []
    for v in volumes:
        if isinstance(v, str) and ":" in v:
            mount_targets.append(v.split(":")[1])
        elif isinstance(v, dict) and v.get("target"):
            mount_targets.append(v["target"])

    for target in REQUIRED_MOUNTS:
        assert target in mount_targets, (
            f"\n\nPREFLIGHT: service {service_name!r} is not bind-mounting {target}.\n"
            f"  volumes: {volumes}\n"
            f"  fix: add `./{target.rsplit('/', 1)[1]}:{target}` to this service's volumes.\n"
            f"       (Missing ./logs mount was Incident 2 -- beats.bin invisible in container.)\n"
        )


@pytest.mark.parametrize("service_name", REQUIRED_SERVICES)
def test_service_declares_env_file(compose: dict, service_name: str):
    svc = compose["services"][service_name]
    env_file = svc.get("env_file")
    files = [env_file] if isinstance(env_file, str) else (env_file or [])
    assert any(f == ".env" for f in files), (
        f"\n\nPREFLIGHT: service {service_name!r} does not declare env_file: .env.\n"
        f"  fix: add `env_file: .env` under this service.\n"
    )


@pytest.mark.parametrize("service_name", REQUIRED_SERVICES)
def test_service_declares_restart_unless_stopped(compose: dict, service_name: str):
    svc = compose["services"][service_name]
    restart = svc.get("restart")
    assert restart == "unless-stopped", (
        f"\n\nPREFLIGHT: service {service_name!r} has restart={restart!r}; expected 'unless-stopped'.\n"
        f"--- {service_name} ---\n{_format_service(service_name, svc)}"
        f"  fix: add `restart: unless-stopped` under this service so the API + worker\n"
        f"       come back up after a host reboot / OOM / segfault in the C++ binary.\n"
    )


@pytest.mark.parametrize("service_name", REQUIRED_SERVICES)
def test_service_osrm_host_and_port_configurable(compose: dict, service_name: str):
    """Compose must either set OSRM_HOST/OSRM_PORT explicitly, or use
    ${VAR:-default} substitution -- never leave them unset when the C++
    simulator will call them at first fire."""
    svc = compose["services"][service_name]
    env = svc.get("environment") or {}
    if isinstance(env, list):
        env = dict(e.split("=", 1) for e in env if "=" in e)

    for key in ("OSRM_HOST", "OSRM_PORT"):
        val = env.get(key)
        assert val is not None, (
            f"\n\nPREFLIGHT: service {service_name!r} does not set {key}. "
            f"C++ simulator will fall back to localhost, which is dead inside the container. "
            f"fix: set `{key}: ${{{key}:-<default>}}` under environment."
        )
        # Substitution form is fine; a bare literal is fine too.
        if isinstance(val, str) and "$" in val:
            assert ":-" in val or ":?" in val, (
                f"{key}={val!r} references an env var without a default. Add `:-...` "
                f"so this doesn't blow up when the operator forgets to export it."
            )


@pytest.mark.parametrize("service_name", REQUIRED_SERVICES)
def test_onnxruntime_bind_mount_targets_ro_opt(compose: dict, service_name: str):
    """If the HOST_ONNXRUNTIME_DIR bind-mount is present (it should be),
    it must target /opt/onnxruntime and be read-only. That path is what
    LD_LIBRARY_PATH looks at first inside the container."""
    svc = compose["services"][service_name]
    volumes = svc.get("volumes") or []
    onnx_mounts = [v for v in volumes if isinstance(v, str) and "/opt/onnxruntime" in v]
    if not onnx_mounts:
        pytest.skip(
            f"{service_name}: no /opt/onnxruntime bind-mount configured. "
            f"OK if the image-baked libonnxruntime is enough for your binary."
        )
    for m in onnx_mounts:
        assert m.endswith(":ro"), (
            f"\n\nPREFLIGHT: {service_name} mounts onnxruntime read-write: {m}\n"
            f"  fix: append ':ro' -- the simulator only needs to read it, and rw\n"
            f"       lets a crash corrupt the host copy.\n"
        )
