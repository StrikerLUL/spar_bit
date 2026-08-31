from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPARBIT_", env_file=".env",
                                      env_file_encoding="utf-8", extra="ignore")

    data_dir: Path = Path("/data")
    db_file: str = "sparbit.db"

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

    # Claimer-Log (vom claimer-Container gemountet)
    claimer_log_dir: Path = Path("/claimer-data")

    cors_origins: str = ""
    log_level: str = "INFO"
    log_json: bool = True

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_file

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"


settings = Settings()
