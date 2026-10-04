"""Fixtures for the orchestrator tests: a throwaway copy of the repository config."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator_samples import make_config_dir


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    return make_config_dir(tmp_path)
