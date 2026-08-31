import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIXTURES = Path(__file__).parent / "fixtures"

os.environ.setdefault("SPARBIT_DATA_DIR", "/tmp/sparbit-tests")
os.environ.setdefault("SPARBIT_LOG_JSON", "false")


def pytest_addoption(parser):
    parser.addoption("--live-fixtures", default=None,
                     help="Ordner mit echten, per tools/verify_endpoints.py "
                          "aufgezeichneten Antworten.")


@pytest.fixture(scope="session")
def fixture_dir(request):
    live = request.config.getoption("--live-fixtures")
    return Path(live) if live else FIXTURES


@pytest.fixture
def load_text(fixture_dir):
    def _load(name):
        path = fixture_dir / name
        if not path.exists():
            pytest.skip(f"Fixture {name} fehlt in {fixture_dir}")
        return path.read_text("utf-8")
    return _load


@pytest.fixture
def load_json(load_text):
    return lambda name: json.loads(load_text(name))
