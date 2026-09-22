"""Der Weg, auf dem jemand ohne Node an die Oberflaeche kommt.

frontend/dist liegt nicht mehr im Repository. Dafuer holt run.py das
Archiv aus dem letzten Release - und muss dabei zwei Dinge koennen:
nicht aus dem Zielordner ausbrechen und eine falsche Pruefsumme merken.
"""
import importlib.util
import io
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def lade_run():
    spec = importlib.util.spec_from_file_location("sparbit_run", ROOT / "run.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def archiv_mit(tmp_path: Path, name: str, inhalt: bytes = b"x") -> Path:
    pfad = tmp_path / "archiv.tar.gz"
    with tarfile.open(pfad, "w:gz") as tf:
        info = tarfile.TarInfo(name)
        info.size = len(inhalt)
        tf.addfile(info, io.BytesIO(inhalt))
    return pfad


def test_archiv_darf_nicht_aus_dem_zielordner_ausbrechen(tmp_path):
    run = lade_run()
    archiv = archiv_mit(tmp_path, "../ausbruch.txt")
    ziel = tmp_path / "ziel"
    with pytest.raises(ValueError, match="ausbruch"):
        run._sicher_entpacken(archiv, ziel)
    assert not (tmp_path / "ausbruch.txt").exists()


def test_absoluter_pfad_wird_abgewiesen(tmp_path):
    run = lade_run()
    archiv = archiv_mit(tmp_path, "/etc/sparbit-test")
    with pytest.raises(ValueError):
        run._sicher_entpacken(archiv, tmp_path / "ziel")


def test_symlink_im_archiv_wird_abgewiesen(tmp_path):
    """Ein Symlink nach aussen ist der zweite Weg aus dem Ordner heraus."""
    run = lade_run()
    pfad = tmp_path / "link.tar.gz"
    with tarfile.open(pfad, "w:gz") as tf:
        info = tarfile.TarInfo("dist/böse")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        tf.addfile(info)
    with pytest.raises(ValueError, match="kein normaler Eintrag"):
        run._sicher_entpacken(pfad, tmp_path / "ziel")


def test_gutartiges_archiv_wird_entpackt(tmp_path):
    run = lade_run()
    archiv = archiv_mit(tmp_path, "dist/index.html", b"<html>SparBit</html>")
    ziel = tmp_path / "ziel"
    ziel.mkdir()
    run._sicher_entpacken(archiv, ziel)
    assert (ziel / "dist" / "index.html").read_text() == "<html>SparBit</html>"


def test_falsche_pruefsumme_verwirft_den_download(tmp_path, monkeypatch):
    run = lade_run()
    monkeypatch.setattr(run, "FRONTEND", tmp_path)

    archiv = archiv_mit(tmp_path, "dist/index.html", b"echt")
    rohdaten = archiv.read_bytes()

    def fake_urlopen(req, timeout=0):
        url = req.full_url
        if url == run.RELEASE_API:
            koerper = (
                b'{"tag_name": "v1.2.3", "assets": ['
                b'{"name": "frontend-dist.tar.gz", "browser_download_url": "http://x/a"},'
                b'{"name": "frontend-dist.tar.gz.sha256", "browser_download_url": "http://x/b"}'
                b"]}"
            )
        elif url == "http://x/a":
            koerper = rohdaten
        else:
            koerper = b"0000000000000000000000000000000000000000000000000000000000000000  x\n"

        class Antwort:
            def read(self):
                return koerper

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        return Antwort()

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    assert run.hole_dist_aus_release() is False
    assert not (tmp_path / "dist").exists()
