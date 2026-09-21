"""Anmeldebremse - ohne sie kann man Passwoerter unbegrenzt durchprobieren."""
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.loginguard import (
    SANFT_AB,
    SPERRE_AB,
    LoginGesperrt,
    aufraeumen,
    fehlversuch,
    pruefen,
    wartezeit,
    zuruecksetzen,
)
from app.models import Base, LoginAttempt, utcnow


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_erste_versuche_werden_nicht_gebremst(db):
    for _ in range(SANFT_AB - 1):
        fehlversuch(db, "1.2.3.4", "cillian")
    pruefen(db, "1.2.3.4")          # darf nicht werfen


def test_ab_fuenf_fehlversuchen_wird_gewartet(db):
    for _ in range(SANFT_AB):
        fehlversuch(db, "1.2.3.4", "cillian")
    with pytest.raises(LoginGesperrt) as info:
        pruefen(db, "1.2.3.4")
    assert info.value.sekunden > 0


def test_wartezeit_waechst_und_ist_gedeckelt():
    assert wartezeit(SANFT_AB - 1) == 0
    assert wartezeit(SANFT_AB) < wartezeit(SANFT_AB + 1)
    assert wartezeit(SANFT_AB + 2) <= 60.0


def test_ab_zehn_fehlversuchen_viertelstunde_gesperrt(db):
    for _ in range(SPERRE_AB):
        fehlversuch(db, "1.2.3.4", "cillian")
    with pytest.raises(LoginGesperrt) as info:
        pruefen(db, "1.2.3.4")
    assert info.value.sekunden > 60 * 10


def test_andere_ip_ist_nicht_betroffen(db):
    for _ in range(SPERRE_AB):
        fehlversuch(db, "1.2.3.4", "cillian")
    pruefen(db, "9.9.9.9")          # darf nicht werfen


def test_erfolgreiche_anmeldung_setzt_zurueck(db):
    for _ in range(SPERRE_AB):
        fehlversuch(db, "1.2.3.4", "cillian")
    zuruecksetzen(db, "1.2.3.4")
    pruefen(db, "1.2.3.4")


def test_sperre_laeuft_nach_wartezeit_ab(db):
    for _ in range(SANFT_AB):
        fehlversuch(db, "1.2.3.4", "cillian")
    # Alle Versuche kuenstlich altern lassen: die Wartezeit ist verstrichen.
    for eintrag in db.scalars(select(LoginAttempt)):
        eintrag.ts = utcnow() - timedelta(seconds=120)
    db.commit()
    pruefen(db, "1.2.3.4")


def test_alte_versuche_fallen_aus_dem_fenster(db):
    for _ in range(SPERRE_AB):
        fehlversuch(db, "1.2.3.4", "cillian")
    for eintrag in db.scalars(select(LoginAttempt)):
        eintrag.ts = utcnow() - timedelta(hours=1)
    db.commit()
    pruefen(db, "1.2.3.4")          # ausserhalb des 15-Minuten-Fensters


def test_aufraeumen_entfernt_alte_eintraege(db):
    fehlversuch(db, "1.2.3.4", "cillian")
    for eintrag in db.scalars(select(LoginAttempt)):
        eintrag.ts = utcnow() - timedelta(days=2)
    db.commit()
    assert aufraeumen(db) == 1
    db.commit()
    assert db.scalar(select(LoginAttempt)) is None
