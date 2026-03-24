from pathlib import Path

import pytest


@pytest.fixture
def configs_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "configs"


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parent.parent
