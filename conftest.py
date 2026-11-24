import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.container import build_services  # noqa: E402


@pytest.fixture
def services(tmp_path):
    return build_services(tmp_path / "test.db", tmp_path / "photos")
