"""Preisfehler erkennen.

Ein Preisfehler ist kein Rabatt. Es ist ein Versehen des Haendlers: eine
verrutschte Kommastelle, eine vergessene Null, ein falsch verknuepftes
Variantenbild. Der Fernseher fuer 899 € steht ploetzlich fuer 89,90 € drin.

Solche Funde haben zwei Eigenschaften, die sie vom normalen Deal-Rauschen
abheben:

  * Sie sind kurzlebig. Ein Preisfehler ist nach zwanzig Minuten korrigiert.
    Eine Meldung, die erst im Stunden-Digest kommt, ist wertlos.
  * Sie sind selten. Genau deshalb darf hier nicht grosszuegig geschaetzt
    werden - wer bei jedem 80-Prozent-Rabatt Alarm schlaegt, hat nach einer
    Woche einen stumm geschalteten Kanal.

Darum sammelt dieses Modul Indizien und addiert sie zu einer Punktzahl, statt
eine einzelne Schwelle zu pruefen. Jedes Indiz bringt seine Begruendung mit:
in der Meldung steht nicht "Preisfehler (87 Punkte)", sondern warum.

Die eigentliche Erkennung steckt in `bewerte()` - einer reinen Funktion ohne
Datenbank. Alles, was sie wissen muss, wird ihr uebergeben; damit ist sie
gegen echte Beispiele testbar, ohne eine Deal-Historie aufbauen zu muessen.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import money
from .currency import to_eur
from .db import get_setting
from .models import Deal, DealOffer, PriceHistory, utcnow

log = logging.getLogger(__name__)

# --- Stufen ---------------------------------------------------------------

HEISS = "heiss"          # sehr wahrscheinlich ein Fehler - sofort melden
VERDACHT = "verdacht"    # auffaellig, aber erklaerbar - im Feed hervorheben
KEIN = "kein"

LABEL = {
    HEISS: "Preisfehler",
    VERDACHT: "Preisfehler-Verdacht",
    KEIN: "unauffällig",
}

# Ab welcher Punktzahl welche Stufe gilt.
SCHWELLE_HEISS = 70
SCHWELLE_VERDACHT = 45
# Unter so vielen Rueckmeldungen wird keine Schwelle vorgeschlagen - eine
# aus drei Beobachtungen waere schlechter als die begruendete Vorgabe.
MIN_RUECKMELDUNGEN = 10


# --- Wortlisten -----------------------------------------------------------

# Die Community benennt Preisfehler selbst - das ist das verlaesslichste
# Signal, das es gibt, und es kostet nichts, danach zu suchen.
_FEHLER_WORTE = re.compile(
    r"\b(preisfehler|preis-fehler|preisirrtum|preis-irrtum|"
    r"price\s?error|pricing\s?error|mispric\w*|"
    r"fehlerhafte\s+preisaus(zeichnung|weisung)|"
    r"falsch\s+ausgezeichnet|preisglitch|glitch\s?price)\b",
    re.IGNORECASE)

# "vermutlich Preisfehler" ist schwaecher als eine Feststellung, aber immer
# noch ein Hinweis von jemandem, der den Artikel gesehen hat.
_FEHLER_VAGE = re.compile(
    r"\b(vermutlich|moeglicherweise|möglicherweise|evtl\.?|eventuell|wohl|"
    r"vielleicht|maybe|possible|likely)\s+(ein\s+)?preisfehler\b",
    re.IGNORECASE)

# Konstrukte, bei denen ein niedriger Preis kein Fehler ist, sondern die
# Bauart des Angebots. Ohne diese Liste meldet der Waechter jeden
# Sammeldeal und jeden Gutschein-Stapel.
_KEIN_FEHLER = re.compile(
    r"\b(gutschein|coupon|rabattcode|gutscheincode|voucher|cashback|"
    r"sammeldeal|sammelbestellung|gewinnspiel|verlosung|"
    r"abo|abonnement|vertrag|tarif|monatlich|pro\s+monat|mtl\.?|"
    r"leasing|finanzierung|miete|mietkauf|"
    r"gebraucht|refurbished|b-?ware|defekt|bastler|ersatzteil|"
    r"demo|vorfuehr|vorführ|ausstellungsst)\b",
    re.IGNORECASE)

# Quellen, bei denen 90 Prozent Rabatt der Normalfall sind. Ein Steam-Sale
# ist kein Preisfehler, auch wenn die Zahlen gleich aussehen.
_RABATT_QUELLEN = {"steam", "cheapshark", "itad", "ggdeals", "gog", "epic",
                   "humble", "fanatical"}

# Ab welcher Ersparnis sich ein Preisfehler ueberhaupt lohnt. Ein Kugelschreiber
# fuer 3 statt 30 Cent ist rechnerisch ein Zehntel - aber niemand steht dafuer
# nachts auf.
MIN_ERSPARNIS_EUR = 25.0

# Wie viele eigene Messpunkte noetig sind, bevor der Verlauf als Beleg zaehlt.
MIN_VERLAUF = 3
VERLAUF_TAGE = 180


# --- Ergebnis -------------------------------------------------------------

@dataclass
class Fehlerurteil:
    punkte: int = 0
    stufe: str = KEIN
    gruende: list[str] = field(default_factory=list)
    # Stabile Schluessel der Indizien, die zugeschlagen haben. Die Gruende
    # sind frei formulierter Text und taugen nicht zum Auswerten - fuer die
    # Frage "welches Indiz lag bei echten Funden wie oft richtig" braucht es
    # etwas, das sich nicht mit jeder Umformulierung aendert.
    indizien: list[str] = field(default_factory=list)
    # Der Preis, den der Artikel nach allem Wissen eigentlich kosten muesste.
    erwartet_eur: float | None = None
    ersparnis_eur: float | None = None

    @property
    def label(self) -> str:
        return LABEL.get(self.stufe, self.stufe)

    @property
    def melden(self) -> bool:
        return self.stufe == HEISS

    def as_dict(self) -> dict:
        return {"punkte": self.punkte, "stufe": self.stufe,
                "gruende": list(self.gruende), "indizien": list(self.indizien),
                "label": self.label,
                "erwartet_eur": self.erwartet_eur,
                "ersparnis_eur": self.ersparnis_eur}

    def kurz(self) -> str:
        """Ein Satz fuer Meldung und Deal-Karte."""
        if not self.gruende:
            return self.label
        kopf = self.gruende[0]
        if self.ersparnis_eur and self.ersparnis_eur >= MIN_ERSPARNIS_EUR:
            return f"{kopf} Ersparnis rund {money.betrag(self.ersparnis_eur)}."
        return kopf


def _median(werte: list[float]) -> float | None:
    if not werte:
        return None
    s = sorted(werte)
    mitte = len(s) // 2
    return s[mitte] if len(s) % 2 else (s[mitte - 1] + s[mitte]) / 2


def _dezimalverschiebung(preis: float, referenz: float) -> int | None:
    """Sieht die Differenz nach einer verrutschten Kommastelle aus?

    899,00 -> 89,90 ist Faktor 10, 1299 -> 12,99 ist Faktor 100. Das ist die
    Signatur eines Tippfehlers und nicht die eines Rabatts: Haendler setzen
    Rabatte auf krumme 71 oder 83 Prozent, nicht auf exakt 90,0 Prozent.
    """
    for stellen in (1, 2, 3):
        faktor = 10 ** stellen
        if abs(preis * faktor - referenz) <= referenz * 0.08:
            return stellen
    return None


def bewerte(
    titel: str,
    preis_eur: float | None,
    *,
    beschreibung: str | None = None,
    originalpreis_eur: float | None = None,
    rabatt_prozent: float | None = None,
    ist_gratis: bool = False,
    quelle: str = "",
    temperatur: float | None = None,
    verlauf_eur: list[float] | None = None,
    fremdpreise_eur: list[float] | None = None,
    uvp_fragwuerdig: bool = False,
) -> Fehlerurteil:
    """Indizien sammeln und zu einer Punktzahl verdichten.

    Reine Funktion: alles, was zaehlt, kommt als Argument rein. `verlauf_eur`
    sind die eigenen frueheren Beobachtungen dieses Artikels, `fremdpreise_eur`
    die aktuellen Preise anderer Quellen fuer denselben Artikel.
    """
    urteil = Fehlerurteil()
    text = f"{titel or ''} {beschreibung or ''}"

    # Gratis ist kein Fehler, sondern Absicht. Und ohne Preis gibt es nichts
    # zu beurteilen.
    if ist_gratis or preis_eur is None or preis_eur <= 0.009:
        return urteil

    # Reihenfolge zaehlt: "vermutlich Preisfehler" enthaelt das Wort
    # "Preisfehler" und wuerde sonst als Feststellung durchgehen. Deshalb
    # werden die vagen Wendungen erst herausgeschnitten und der Rest auf
    # eine klare Aussage geprueft.
    vage = bool(_FEHLER_VAGE.search(text))
    explizit = bool(_FEHLER_WORTE.search(_FEHLER_VAGE.sub(" ", text)))

    # Angebotsformen, bei denen ein niedriger Preis zur Bauart gehoert.
    # Eine ausdrueckliche Nennung sticht das aber: wenn im Titel
    # "Preisfehler" steht, ist das kein Sammeldeal-Artefakt.
    if _KEIN_FEHLER.search(text) and not explizit:
        return urteil

    verlauf = [w for w in (verlauf_eur or []) if w and w > 0]
    fremd = [w for w in (fremdpreise_eur or []) if w and w > 0]

    punkte = 0
    gruende: list[str] = []
    indizien: list[str] = []
    referenzen: list[float] = []

    # --- Indiz 1: die Community sagt es selbst --------------------------
    if explizit:
        punkte += 55
        indizien.append("ausgewiesen")
        gruende.append("Als Preisfehler ausgewiesen.")
    elif vage:
        punkte += 30
        indizien.append("vage_genannt")
        gruende.append("Wird als möglicher Preisfehler gehandelt.")

    # --- Indiz 2: der eigene beobachtete Verlauf ------------------------
    if len(verlauf) >= MIN_VERLAUF:
        mittel = _median(verlauf)
        tiefst = min(verlauf)
        if mittel:
            referenzen.append(mittel)
            anteil = preis_eur / mittel
            # Gestuft statt binaer: der Sprung von "auffaellig" zu "kaum
            # erklaerbar" ist fliessend, und eine harte Kante bei 25 Prozent
            # haette einen Artikel fuer 149 statt 549 Euro durchgewinkt.
            if anteil <= 0.20:
                punkte += 45
            elif anteil <= 0.30:
                punkte += 35
            elif anteil <= 0.45:
                punkte += 25
            if anteil <= 0.45:
                indizien.append("unter_eigenem_verlauf")
                gruende.append(
                    f"Kostet sonst um {money.betrag(mittel)} — das sind "
                    f"{round((1 - anteil) * 100)} % weniger als üblich.")
            # Auch der bisherige Tiefstpreis wird weit unterboten: der
            # Artikel war noch nie auch nur in der Naehe.
            if tiefst > 0 and preis_eur <= tiefst * 0.5:
                punkte += 15
                indizien.append("unter_tiefstpreis")
                gruende.append(
                    f"Günstigster bisher beobachteter Preis war "
                    f"{money.betrag(tiefst)}.")

    # --- Indiz 3: andere Quellen verlangen ein Vielfaches ---------------
    if fremd:
        guenstigster_fremd = min(fremd)
        referenzen.append(guenstigster_fremd)
        if guenstigster_fremd > 0:
            anteil = preis_eur / guenstigster_fremd
            if anteil <= 0.3:
                punkte += 35
                indizien.append("unter_fremdpreis")
                gruende.append(
                    f"Andere Quellen verlangen mindestens "
                    f"{money.betrag(guenstigster_fremd)} für denselben Artikel.")
            elif anteil <= 0.5:
                punkte += 18
                indizien.append("unter_fremdpreis")
                gruende.append(
                    f"Woanders kostet es {money.betrag(guenstigster_fremd)}.")

    # --- Indiz 4: verrutschte Kommastelle -------------------------------
    # Die aussagekraeftigste Form, weil sie eine konkrete Fehlermechanik
    # beschreibt und nicht nur "billig" heisst.
    kandidaten = list(referenzen)
    if originalpreis_eur and not uvp_fragwuerdig:
        kandidaten.append(originalpreis_eur)
    for referenz in kandidaten:
        stellen = _dezimalverschiebung(preis_eur, referenz)
        if stellen:
            punkte += 30
            indizien.append("kommastelle")
            gruende.append(
                f"Der Preis sieht aus wie {money.betrag(referenz)} mit "
                f"verrutschtem Komma ({'ein' if stellen == 1 else stellen} "
                f"{'e Stelle' if stellen == 1 else ' Stellen'}).")
            break

    # --- Indiz 5: extremer Rabatt auf einen glaubwuerdigen UVP ----------
    if (originalpreis_eur and not uvp_fragwuerdig
            and originalpreis_eur >= 80 and rabatt_prozent
            and rabatt_prozent >= 85):
        referenzen.append(originalpreis_eur)
        punkte += 20
        indizien.append("extremrabatt_auf_uvp")
        gruende.append(
            f"{round(rabatt_prozent)} % unter dem Listenpreis von "
            f"{money.betrag(originalpreis_eur)}.")

    # --- Indiz 6: die Community dreht durch ------------------------------
    # Unterstuetzend, nie allein tragend: Hitze entsteht auch bei ganz
    # normalen guten Deals.
    if temperatur is not None and temperatur >= 600 and punkte > 0:
        punkte += 10
        indizien.append("hohe_resonanz")
        gruende.append(f"Sehr hohe Resonanz ({round(temperatur)}°).")

    if not punkte:
        return urteil

    # --- Daempfer ---------------------------------------------------------
    quelle_low = (quelle or "").lower()
    if quelle_low in _RABATT_QUELLEN and not explizit:
        # Ein Spiel fuer 1,99 statt 59,99 ist ein Sale, kein Fehler.
        punkte = int(punkte * 0.45)
        if punkte >= SCHWELLE_VERDACHT:
            gruende.append("Hinweis: Bei Spiele-Shops sind solche Rabatte üblich.")

    erwartet = max(referenzen) if referenzen else None
    ersparnis = (erwartet - preis_eur) if erwartet else None

    # Kleinbetraege: rechnerisch auffaellig, praktisch egal. Ohne ausdrueckliche
    # Nennung reicht das nicht fuer eine Meldung mitten in der Nacht.
    if (ersparnis is not None and ersparnis < MIN_ERSPARNIS_EUR
            and not explizit):
        punkte = min(punkte, SCHWELLE_VERDACHT - 1)
        gruende.append(
            f"Nur {money.betrag(ersparnis)} Unterschied — als Fehler zu klein.")
    elif ersparnis is None and not explizit:
        # Keine einzige Referenz: wir wissen nicht, wovon der Preis abweicht.
        punkte = min(punkte, SCHWELLE_VERDACHT - 1)

    punkte = max(0, min(100, punkte))
    urteil.punkte = punkte
    urteil.gruende = gruende
    urteil.indizien = indizien
    urteil.erwartet_eur = round(erwartet, 2) if erwartet else None
    urteil.ersparnis_eur = round(ersparnis, 2) if ersparnis else None
    urteil.stufe = (HEISS if punkte >= SCHWELLE_HEISS
                    else VERDACHT if punkte >= SCHWELLE_VERDACHT else KEIN)
    return urteil


# --- Datenbank-Anbindung ---------------------------------------------------

def bewerte_deal(db: Session, deal: Deal) -> Fehlerurteil:
    """Urteil fuer einen gespeicherten Deal, inklusive Verlauf und Fremdpreisen."""
    seit = utcnow() - timedelta(days=VERLAUF_TAGE)
    verlauf = [
        to_eur(z.preis, z.waehrung)
        for z in db.scalars(
            select(PriceHistory)
            .where(PriceHistory.deal_id == deal.id, PriceHistory.ts >= seit)
            .order_by(PriceHistory.ts.asc()))
    ]

    # Preise anderer Quellen fuer denselben Artikel. Der eigene Eintrag der
    # guenstigsten Quelle faellt raus - sonst vergleicht sich der Deal mit
    # sich selbst und findet nie eine Abweichung.
    fremd = [
        a.preis_eur if a.preis_eur is not None else to_eur(a.preis, a.waehrung)
        for a in db.scalars(select(DealOffer).where(DealOffer.deal_id == deal.id))
        if not a.ist_gratis
    ]
    preis_eur = deal.preis_eur if deal.preis_eur is not None else to_eur(
        deal.preis, deal.waehrung)
    if preis_eur is not None:
        fremd = [p for p in fremd if p is not None and p > preis_eur * 1.02]

    return bewerte(
        deal.titel,
        preis_eur,
        beschreibung=deal.beschreibung,
        originalpreis_eur=to_eur(deal.originalpreis, deal.waehrung),
        rabatt_prozent=deal.rabatt_prozent,
        ist_gratis=deal.ist_gratis,
        quelle=deal.quelle,
        temperatur=deal.temperatur,
        verlauf_eur=[w for w in verlauf if w is not None],
        fremdpreise_eur=[p for p in fremd if p is not None],
        uvp_fragwuerdig=(deal.urteil == "uvp_fragwuerdig"),
    )


def aktualisiere(db: Session, deals: list[Deal]) -> list[Deal]:
    """Alle uebergebenen Deals bewerten und speichern.

    Gibt die zurueck, die neu auf `heiss` gesprungen sind - genau die, fuer
    die sich eine Sofortmeldung lohnt. Ein Deal, der schon gestern heiss war,
    ist nicht noch einmal eine Nachricht wert.
    """
    from .db import get_setting
    # Die Schwelle ist einstellbar: wer lieber zehn Fehlalarme als einen
    # verpassten Fund hat, zieht sie runter.
    schwelle = int(get_setting(db, "preisfehler_schwelle", SCHWELLE_HEISS) or
                   SCHWELLE_HEISS)

    frisch_heiss: list[Deal] = []
    for deal in deals:
        urteil = bewerte_deal(db, deal)
        if urteil.punkte >= schwelle:
            urteil.stufe = HEISS
        vorher = deal.fehler_stufe
        deal.fehler_score = urteil.punkte
        deal.fehler_stufe = urteil.stufe
        deal.fehler_gruende = urteil.gruende
        deal.fehler_indizien = urteil.indizien
        deal.fehler_erwartet_eur = urteil.erwartet_eur
        deal.fehler_am = utcnow()
        if urteil.stufe == HEISS and vorher != HEISS:
            frisch_heiss.append(deal)
            log.warning("Preisfehler erkannt (%d Punkte): %s — %s",
                        urteil.punkte, deal.titel[:70], urteil.kurz(),
                        extra={"deal_id": deal.id})
    db.commit()
    return frisch_heiss


# --- Rueckmeldung des Benutzers -------------------------------------------

ECHT = "echt"
FEHLALARM = "fehlalarm"

# Wie die Indizien im UI heissen. Absichtlich hier und nicht im Frontend:
# wer ein Indiz umbenennt, soll es an einer Stelle tun.
INDIZ_NAMEN = {
    "ausgewiesen": "Ausdrücklich als Preisfehler genannt",
    "vage_genannt": "Als möglicher Preisfehler gehandelt",
    "unter_eigenem_verlauf": "Weit unter dem eigenen Verlauf",
    "unter_tiefstpreis": "Unter dem bisherigen Tiefstpreis",
    "unter_fremdpreis": "Weit unter anderen Quellen",
    "kommastelle": "Verrutschte Kommastelle",
    "extremrabatt_auf_uvp": "Extremrabatt auf glaubwürdigen UVP",
    "hohe_resonanz": "Sehr hohe Resonanz",
}


def bewerte_rueckmeldungen(db: Session) -> dict:
    """Auswerten, welches Indiz wie oft richtig lag.

    Die Gewichte oben sind begruendet, aber am Schreibtisch gewaehlt. Erst
    die Rueckmeldungen sagen, welche Indizien auf diesem Rechner, mit
    diesen Quellen, tatsaechlich taugen. Ausgewertet wird nur, was der
    Benutzer beurteilt hat - alles andere waere geraten.
    """
    beurteilt = list(db.scalars(
        select(Deal).where(Deal.fehler_urteil_mensch.isnot(None))))

    echt = [d for d in beurteilt if d.fehler_urteil_mensch == ECHT]
    falsch = [d for d in beurteilt if d.fehler_urteil_mensch == FEHLALARM]

    indizien = []
    for schluessel, name in INDIZ_NAMEN.items():
        traf_echt = sum(1 for d in echt if schluessel in (d.fehler_indizien or []))
        traf_falsch = sum(1 for d in falsch if schluessel in (d.fehler_indizien or []))
        gesamt = traf_echt + traf_falsch
        if not gesamt:
            continue
        indizien.append({
            "schluessel": schluessel,
            "name": name,
            "echt": traf_echt,
            "fehlalarm": traf_falsch,
            "treffsicherheit": round(traf_echt / gesamt * 100),
        })
    indizien.sort(key=lambda i: (-i["treffsicherheit"], -i["echt"]))

    return {
        "beurteilt": len(beurteilt),
        "echt": len(echt),
        "fehlalarm": len(falsch),
        "indizien": indizien,
        **schwellen_vorschlag(db, echt, falsch),
    }


def schwellen_vorschlag(db: Session, echt: list[Deal],
                        falsch: list[Deal]) -> dict:
    """Eine Schwelle vorschlagen - aber nie selbst verstellen.

    Gesucht ist der niedrigste Wert, der noch alle Fehlalarme draussen
    laesst. Gibt es zu wenige Rueckmeldungen, wird gar nichts vorgeschlagen:
    eine Schwelle aus drei Beobachtungen waere schlechter als die begruendete
    Vorgabe.
    """
    aktuell = int(get_setting(db, "preisfehler_schwelle", SCHWELLE_HEISS)
                  or SCHWELLE_HEISS)
    if len(echt) + len(falsch) < MIN_RUECKMELDUNGEN:
        return {"vorschlag": None, "aktuelle_schwelle": aktuell,
                "vorschlag_grund": (
                    f"Noch zu wenig Rückmeldungen — ab "
                    f"{MIN_RUECKMELDUNGEN} lässt sich etwas sagen.")}

    hoechster_fehlalarm = max((d.fehler_score or 0 for d in falsch), default=0)
    if not falsch:
        # Keine Fehlalarme: die Schwelle koennte runter, damit weniger
        # durchrutscht. Nicht unter die Verdachtsschwelle.
        niedrigster_echter = min((d.fehler_score or 0 for d in echt), default=aktuell)
        vorschlag = max(SCHWELLE_VERDACHT, min(aktuell, niedrigster_echter))
        grund = ("Kein einziger Fehlalarm — die Schwelle darf niedriger "
                 "liegen, dann rutscht weniger durch.")
    else:
        vorschlag = min(100, hoechster_fehlalarm + 1)
        noch_dabei = sum(1 for d in echt if (d.fehler_score or 0) >= vorschlag)
        grund = (f"Über {hoechster_fehlalarm} Punkten war kein Fehlalarm mehr "
                 f"dabei; {noch_dabei} von {len(echt)} echten Funden bleiben.")

    if vorschlag == aktuell:
        return {"vorschlag": None, "aktuelle_schwelle": aktuell,
                "vorschlag_grund": "Die eingestellte Schwelle passt."}
    return {"vorschlag": vorschlag, "aktuelle_schwelle": aktuell,
            "vorschlag_grund": grund}


def notiere_rueckmeldung(db: Session, deal_id: int, urteil: str) -> Deal | None:
    """Rueckmeldung speichern. Nochmal druecken nimmt sie zurueck."""
    if urteil not in (ECHT, FEHLALARM):
        raise ValueError(f"Unbekanntes Urteil '{urteil}'")
    deal = db.get(Deal, deal_id)
    if deal is None:
        return None
    if deal.fehler_urteil_mensch == urteil:
        deal.fehler_urteil_mensch = None
        deal.fehler_urteil_am = None
    else:
        deal.fehler_urteil_mensch = urteil
        deal.fehler_urteil_am = utcnow()
    db.commit()
    return deal
