"""Preflight: env-var resolution rules in core.config must hold.

Bug classes this test prevents:
- (Incident 4) `.env` with OSRM_HOST=localhost inside docker -> simulator
  reaches for a dead upstream. The fallback + diagnostic pathway makes
  that visible; this test locks it in.
- (Incident 6) HOST_ONNXRUNTIME_DIR unset when the simulator needs a
  specific libonnxruntime.so -> segfault at first fire. This test at
  least warns on Linux (where the mount is used).
"""

from __future__ import annotations

import importlib
import os
import platform
from pathlib import Path

import pytest

import core.config as config


@pytest.fixture(autouse=True)
def _restore_env(monkeypatch):
    """Every test here mutates env + reloads core.config; put it back."""
    yield
    for k in ("BASE_DIR", "DATA_DIR", "LOGS_DIR", "OSRM_HOST"):
        monkeypatch.delenv(k, raising=False)
    importlib.reload(config)


def test_all_three_dirs_win_when_all_set(monkeypatch, tmp_path: Path):
    base = tmp_path / "base"
    data = tmp_path / "otherdata"
    logs = tmp_path / "otherlogs"
    monkeypatch.setenv("BASE_DIR", str(base))
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setenv("LOGS_DIR", str(logs))
    importlib.reload(config)

    assert config.BASE_DIR == base, "BASE_DIR env override should win"
    assert config.DATA_DIR == data, "DATA_DIR env override should win"
    assert config.LOGS_DIR == logs, "LOGS_DIR env override should win"


def test_only_base_dir_set_derives_the_other_two(monkeypatch, tmp_path: Path):
    base = tmp_path / "base"
    monkeypatch.setenv("BASE_DIR", str(base))
    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.delenv("LOGS_DIR", raising=False)
    importlib.reload(config)

    assert config.BASE_DIR == base
    assert config.DATA_DIR == base / "data", (
        f"DATA_DIR should derive from BASE_DIR; got {config.DATA_DIR}"
    )
    assert config.LOGS_DIR == base / "logs", (
        f"LOGS_DIR should derive from BASE_DIR; got {config.LOGS_DIR}"
    )


def test_defaults_resolve_from_file_parent_chain(monkeypatch):
    for k in ("BASE_DIR", "DATA_DIR", "LOGS_DIR"):
        monkeypatch.delenv(k, raising=False)
    importlib.reload(config)

    expected_base = Path(config.__file__).resolve().parent.parent.parent
    assert config.BASE_DIR == expected_base


def test_unresolvable_osrm_host_falls_back_with_diagnostic(monkeypatch, capsys):
    monkeypatch.setenv("OSRM_HOST", "this-host-does-not-resolve-preflight")
    importlib.reload(config)

    assert config.OSRM_HOST == "localhost", (
        "OSRM_HOST should fall back to 'localhost' when the configured host does "
        "not resolve (see src/core/config.py::_resolve_osrm_host)."
    )
    captured = capsys.readouterr()
    assert "does not resolve" in captured.out, (
        "Fallback happened silently; the diagnostic banner is missing. Operators "
        "need the stdout line to notice they hit the fallback."
    )


@pytest.mark.skipif(
    platform.system() != "Linux",
    reason="HOST_ONNXRUNTIME_DIR is only consumed by the Linux docker bind-mount.",
)
def test_host_onnxruntime_dir_if_set_points_at_libonnxruntime():
    """.env may set HOST_ONNXRUNTIME_DIR to bind-mount a specific onnxruntime
    version into the container. If set, it must actually exist AND contain a
    libonnxruntime.so* -- otherwise the simulator crashes at load time with
    a symbol-lookup error that operators struggle to diagnose."""
    raw = os.getenv("HOST_ONNXRUNTIME_DIR")
    if not raw:
        pytest.skip("HOST_ONNXRUNTIME_DIR not set; docker-compose default will be used.")

    d = Path(raw)
    assert d.is_dir(), (
        f"\n\nPREFLIGHT: HOST_ONNXRUNTIME_DIR={raw!r} does not exist.\n"
        f"  fix: point HOST_ONNXRUNTIME_DIR at the directory containing\n"
        f"       libonnxruntime.so.<version>, or unset it to use the version\n"
        f"       baked into the image.\n"
    )
    matches = list(d.glob("libonnxruntime.so*"))
    assert matches, (
        f"\n\nPREFLIGHT: HOST_ONNXRUNTIME_DIR={raw!r} contains no libonnxruntime.so*\n"
        f"  fix: bind-mount a directory that actually contains the shared library,\n"
        f"       e.g. .../fire_simulator/external/onnxruntime/usr/local/lib64\n"
    )
