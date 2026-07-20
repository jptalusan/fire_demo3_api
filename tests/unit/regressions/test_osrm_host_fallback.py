"""Regression: OSRM_HOST must fall back to 'localhost' when the configured
host does not resolve, with a printed diagnostic -- and must NOT fall back
(or print anything) when the configured host does resolve.

Fixed in commit 1c090fa ("Auto-fallback OSRM_HOST to localhost when
configured host does not resolve"). 'host.docker.internal' is the default in
compose, but it doesn't resolve on native macOS (Docker Desktop absent) or
plain Linux hosts, which used to silently break the C++ simulator's OSRM
calls the first time someone ran uvicorn directly outside Docker.
"""

from __future__ import annotations

import importlib

import pytest

import core.config as config


@pytest.fixture(autouse=True)
def _restore_osrm_env(monkeypatch):
    yield
    monkeypatch.delenv("OSRM_HOST", raising=False)
    importlib.reload(config)


def test_unresolvable_host_falls_back_to_localhost_with_diagnostic(monkeypatch, capsys):
    monkeypatch.setenv("OSRM_HOST", "this-host-does-not-resolve-xyz")
    importlib.reload(config)

    assert config.OSRM_HOST == "localhost"
    captured = capsys.readouterr()
    assert "does not resolve" in captured.out
    assert "falling back to 'localhost'" in captured.out


def test_resolvable_host_is_kept_without_any_warning(monkeypatch, capsys):
    monkeypatch.setenv("OSRM_HOST", "localhost")
    importlib.reload(config)

    assert config.OSRM_HOST == "localhost"
    captured = capsys.readouterr()
    assert "does not resolve" not in captured.out
    assert "falling back" not in captured.out
