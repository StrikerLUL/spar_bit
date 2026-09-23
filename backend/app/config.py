from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Projektwurzel: .../spar_bit  (config.py liegt in backend/app/)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def in_docker() -> bool:
    """Laeuft dieser Prozess im Container?

    Nur explizite Signale zaehlen: das Dockerfile setzt SPARBIT_IN_DOCKER, und
    /.dockerenv legt die Container-Laufzeit selbst an. Ein blosses vorhandenes
    /data reicht nicht - das gibt es auch auf manchen normalen Rechnern.
    """
    return bool(os.environ.get("SPARBIT_IN_DOCKER")) or Path("/.dockerenv").exists()


def _default_data_dir() -> Path:
    """Wo die Datenbank liegt - im Container anders als auf dem eigenen Rechner.

    Im Docker-Image ist /data ein Volume. Startet man SparBit dagegen lokal
    (python run.py), soll nichts nach / geschrieben werden - dann landet alles
    in <projekt>/data neben dem Code.
    """
    if os.environ.get("SPARBIT_DATA_DIR"):
        return Path(os.environ["SPARBIT_DATA_DIR"])
    return Path("/data") if in_docker() else PROJECT_ROOT / "data"


def _default_claimer_dir() -> Path:
    if os.environ.get("SPARBIT_CLAIMER_LOG_DIR"):
        return Path(os.environ["SPARBIT_CLAIMER_LOG_DIR"])
    return Path("/claimer-data") if in_docker() else PROJECT_ROOT / "claimer-data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPARBIT_", env_file=".env",
                                      env_file_encoding="utf-8", extra="ignore")

    data_dir: Path = _default_data_dir()
    db_file: str = "sparbit.db"
    # Leer heisst: SQLite im Datenverzeichnis - der Normalfall und das,
    # was SparBit sein will. Wer die Daten lieber in einem vorhandenen
    # Postgres haelt, traegt hier dessen Adresse ein
    # (postgresql+psycopg://benutzer:passwort@host/datenbank).
    db_url_override: str = ""

    # Sitzungs-Signatur. Wird beim ersten Start erzeugt, wenn nicht gesetzt.
    secret_key: str = ""
    session_cookie: str = "sparbit_session"
    session_max_age: int = 60 * 60 * 24 * 30

    user_agent: str = (
        "SparBit/1.0 (self-hosted deal monitor; "
        "+https://github.com/StrikerLUL/spar_bit)"
    )
    http_timeout: float = 25.0
    per_host_delay: float = 1.0

    # Circuit Breaker
    breaker_threshold: int = 5          # Fehler in Folge
    breaker_cooldown: int = 1800        # Sekunden Sperre

    # Aufbewahrung
    deal_retention_days: int = 60
    log_retention_days: int = 14
    max_log_lines: int = 5000

    # Claimer-Log (vom claimer-Container gemountet bzw. lokal daneben)
    claimer_log_dir: Path = _default_claimer_dir()

    # Zusaetzliche Quellen-Module, die nicht im Repository stehen. Jede
    # .py-Datei in diesem Ordner wird beim Start geladen - so lassen sich
    # eigene Quellen betreiben, ohne SparBit zu forken.
    plugin_dir: Path | None = None

    # SparBit ruft von sich aus nichts im eigenen Netz ab (siehe
    # netzschutz.py). Wer bewusst einen Feed oder Shop aus dem Heimnetz
    # beobachten will, schaltet die Pruefung hiermit aus.
    erlaube_private_ziele: bool = False

    cors_origins: str = ""
    log_level: str = "INFO"
    # Lokal ist lesbarer Text angenehmer, im Container maschinenlesbares JSON.
    log_json: bool = in_docker()

    # Telegram-Bot: lauscht auf Knopfdruck ("gemerkt", "Quelle stumm") und
    # auf Befehle wie /neueste. Braucht keinen offenen Port - Long Polling.
    telegram_polling: bool = True

    # Ausgelieferte Web-Oberflaeche (von "npm run build"). Wird - wenn
    # vorhanden - direkt vom Backend serviert, dann reicht ein Prozess.
    frontend_dist: Path = PROJECT_ROOT / "frontend" / "dist"

    # Gemeinsames Geheimnis zwischen Web-UI und dem Update-Skript auf dem
    # Host. Nur wenn es gesetzt ist, gibt es den Update-Bereich im UI -
    # sonst koennte der Knopf ohnehin niemanden erreichen. install.sh legt
    # es an; von Hand:  openssl rand -hex 32
    update_token: str = ""

    # Laeuft der Scheduler in diesem Prozess?
    #   "auto" - ja (der Normalfall, ein Prozess fuer alles)
    #   "aus"  - nein; dann muss ein Worker laufen (python -m app.worker),
    #            sonst sammelt niemand Deals ein. Fuer grosse Anlagen, in
    #            denen das Einsammeln die Oberflaeche nicht bremsen soll.
    scheduler: str = "auto"

    @property
    def scheduler_hier(self) -> bool:
        return str(self.scheduler).strip().lower() not in {"aus", "off", "0", "false"}

    # Wo der lokale Start lauscht.
    host: str = "127.0.0.1"
    port: int = 8000
    open_browser: bool = True

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_file

    @property
    def db_url(self) -> str:
        return self.db_url_override or f"sqlite:///{self.db_path}"

    @property
    def ist_sqlite(self) -> bool:
        return self.db_url.startswith("sqlite")


settings = Settings()
