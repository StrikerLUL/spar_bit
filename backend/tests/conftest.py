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


def lade_app_neu():
    """app.main mit der aktuellen Umgebung frisch importieren.

    Wichtig ist, auch das Paket "app" selbst zu entfernen: bleibt es liegen,
    findet "from .. import updater" das alte Submodul als Attribut des
    Pakets und importiert es gar nicht neu - die Einstellungen von vorhin
    leben dann im frisch gebauten Router weiter.
    """
    import importlib

    for name in [n for n in sys.modules if n == "app" or n.startswith("app.")]:
        del sys.modules[name]
    import app.main as main
    return importlib.reload(main)


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
