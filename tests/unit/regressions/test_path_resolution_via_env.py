"""Regression: BASE_DIR / DATA_DIR / LOGS_DIR must honor explicit env var
overrides instead of always deriving from __file__'s parent chain.

Fixed in commits 071924d ("Override BASE_DIR via env + install libonnxruntime
in image") and 2ec4e5e ("Resolve growth_poisson_v1 bundle via DATA_DIR, not
__file__.parents"). Once the package is installed into site-packages (e.g.
`uv pip install --system .` in Docker), `__file__` resolves under
site-packages and `.parent.parent.parent` walks up to the wrong place --
BASE_DIR/DATA_DIR/LOGS_DIR must be overridable via env, and
engine.incidents_variants.BUNDLE_DIR must follow DATA_DIR rather than
independently re-deriving its own path from __file__.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import core.config as config


@pytest.fixture(autouse=True)
def _restore_config_state(monkeypatch):
    """Every test in this module reloads core.config (and possibly
    engine.incidents_variants) with mutated env vars. Always leave both
    modules back in their real, env-free state for the rest of the suite."""
    yield
    monkeypatch.delenv("BASE_DIR", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.delenv("LOGS_DIR", raising=False)
    monkeypatch.delenv("GROWTH_V1_DATA_DIR", raising=False)
    importlib.reload(config)
    import engine.incidents_variants as variants
    importlib.reload(variants)


def test_base_data_logs_dir_honor_env_overrides(monkeypatch):
    monkeypatch.setenv("BASE_DIR", "/tmp/foo")
    monkeypatch.setenv("DATA_DIR", "/tmp/foo/data")
    monkeypatch.setenv("LOGS_DIR", "/tmp/foo/logs")
    importlib.reload(config)

    assert config.BASE_DIR == Path("/tmp/foo")
    assert config.DATA_DIR == Path("/tmp/foo/data")
    assert config.LOGS_DIR == Path("/tmp/foo/logs")


def test_defaults_derive_from_file_parent_chain_when_env_absent(monkeypatch):
    monkeypatch.delenv("BASE_DIR", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.delenv("LOGS_DIR", raising=False)
    importlib.reload(config)

    expected_base = Path(config.__file__).resolve().parent.parent.parent
    assert config.BASE_DIR == expected_base
    assert config.DATA_DIR == expected_base / "data"
    assert config.LOGS_DIR == expected_base / "logs"


def test_incidents_variants_bundle_dir_follows_data_dir_env(monkeypatch, tmp_path):
    fake_data_dir = tmp_path / "custom_data"
    monkeypatch.setenv("DATA_DIR", str(fake_data_dir))
    monkeypatch.delenv("GROWTH_V1_DATA_DIR", raising=False)
    importlib.reload(config)

    import engine.incidents_variants as variants
    importlib.reload(variants)

    assert variants.BUNDLE_DIR == fake_data_dir / "models" / "growth_poisson_v1", (
        "engine.incidents_variants.BUNDLE_DIR did not follow the DATA_DIR env override -- "
        "it must resolve via core.config.DATA_DIR, not its own __file__.parents walk-up."
    )
