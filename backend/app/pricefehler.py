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
                "gruende": list(self.gruende), "label": self.label,
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
    referenzen: list[float] = []

    # --- Indiz 1: die Community sagt es selbst --------------------------
    if explizit:
        punkte += 55
        gruende.append("Als Preisfehler ausgewiesen.")
    elif vage:
        punkte += 30
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
                gruende.append(
                    f"Kostet sonst um {money.betrag(mittel)} — das sind "
                    f"{round((1 - anteil) * 100)} % weniger als üblich.")
            # Auch der bisherige Tiefstpreis wird weit unterboten: der
            # Artikel war noch nie auch nur in der Naehe.
            if tiefst > 0 and preis_eur <= tiefst * 0.5:
                punkte += 15
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
                gruende.append(
                    f"Andere Quellen verlangen mindestens "
                    f"{money.betrag(guenstigster_fremd)} für denselben Artikel.")
            elif anteil <= 0.5:
                punkte += 18
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
        gruende.append(
            f"{round(rabatt_prozent)} % unter dem Listenpreis von "
            f"{money.betrag(originalpreis_eur)}.")

    # --- Indiz 6: die Community dreht durch ------------------------------
    # Unterstuetzend, nie allein tragend: Hitze entsteht auch bei ganz
    # normalen guten Deals.
    if temperatur is not None and temperatur >= 600 and punkte > 0:
        punkte += 10
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
        deal.fehler_erwartet_eur = urteil.erwartet_eur
        deal.fehler_am = utcnow()
        if urteil.stufe == HEISS and vorher != HEISS:
            frisch_heiss.append(deal)
            log.warning("Preisfehler erkannt (%d Punkte): %s — %s",
                        urteil.punkte, deal.titel[:70], urteil.kurz(),
                        extra={"deal_id": deal.id})
    db.commit()
    return frisch_heiss
