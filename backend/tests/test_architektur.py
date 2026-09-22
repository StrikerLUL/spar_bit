"""Die drei Umbauten: Paket statt Monolith, andere Datenbank, Plugins."""
import pytest

# --- pipeline ist jetzt ein Paket ----------------------------------------

def test_der_alte_import_funktioniert_weiter():
    """Der Schnitt darf nach aussen nicht sichtbar sein."""
    from app.pipeline import (
        buendele,
        check_price_alarms,
        dispatch,
        dispatch_alarms,
        dispatch_preisfehler,
        dispatch_watchdog,
        in_quiet_hours,
        ingest,
        match_rules,
        send_digest,
        waechter_aktiv,
    )
    for f in (ingest, match_rules, dispatch, send_digest, buendele,
              in_quiet_hours, check_price_alarms, dispatch_alarms,
              dispatch_watchdog, dispatch_preisfehler, waechter_aktiv):
        assert callable(f)


def test_die_teile_kennen_ihre_richtung():
    """Aufnahme darf nichts vom Versand wissen - sonst waere der Schnitt
    nur eine verlagerte Schleife."""
    import pathlib

    import app.pipeline.aufnahme as aufnahme
    quelle = pathlib.Path(aufnahme.__file__).read_text(encoding="utf-8")
    assert "from .versand" not in quelle
    assert "from .regeln" not in quelle


# --- Datenbank-Adresse ----------------------------------------------------

def test_ohne_angabe_bleibt_es_sqlite():
    from app.config import Settings
    s = Settings()
    assert s.db_url.startswith("sqlite:///")
    assert s.ist_sqlite is True


def test_eigene_adresse_wird_uebernommen(monkeypatch):
    """Wer die Daten in einem vorhandenen Postgres halten will, soll das
    koennen, ohne den Code anzufassen."""
    monkeypatch.setenv("SPARBIT_DB_URL_OVERRIDE",
                       "postgresql+psycopg://sparbit:geheim@db/sparbit")
    from app.config import Settings
    s = Settings()
    assert s.db_url == "postgresql+psycopg://sparbit:geheim@db/sparbit"
    assert s.ist_sqlite is False


# --- Plugins --------------------------------------------------------------

@pytest.fixture
def plugin_ordner(tmp_path, monkeypatch):
    from app import plugins
    monkeypatch.setattr(plugins.settings, "plugin_dir", tmp_path)
    return tmp_path


def test_ohne_ordner_wird_nichts_geladen(monkeypatch):
    from app import plugins
    monkeypatch.setattr(plugins.settings, "plugin_dir", None)
    assert plugins.lade() == []


def test_eine_eigene_quelle_landet_in_der_registry(plugin_ordner):
    from app import plugins
    from app.sources import all_sources, get_source

    (plugin_ordner / "meinshop.py").write_text('''
from app.sources import Source, Category, Verification, register


class MeinShop(Source):
    id = "meinshop"
    display_name = "Mein Shop"
    category = Category.EXPERIMENTAL
    verification = Verification.UNVERIFIED

    async def fetch(self, ctx):
        return []


register(MeinShop())
''', encoding="utf-8")

    assert plugins.lade() == ["meinshop.py"]
    assert get_source("meinshop") is not None
    assert "meinshop" in {q.id for q in all_sources()}


def test_ein_kaputtes_plugin_verhindert_den_start_nicht(plugin_ordner):
    """Nach einem Tippfehler soll nicht die ganze Installation stehen."""
    from app import plugins

    (plugin_ordner / "kaputt.py").write_text("das ist kein Python(", encoding="utf-8")
    (plugin_ordner / "heil.py").write_text("WERT = 1\n", encoding="utf-8")

    geladen = plugins.lade()
    assert geladen == ["heil.py"]
    assert "kaputt.py" in plugins.stand()["fehler"]


def test_unterstrich_dateien_bleiben_liegen(plugin_ordner):
    """Damit sich Hilfsmodule ablegen lassen, ohne selbst zu laufen."""
    from app import plugins
    (plugin_ordner / "_hilfe.py").write_text("raise RuntimeError('nie')\n",
                                             encoding="utf-8")
    assert plugins.lade() == []
