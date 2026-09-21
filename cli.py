#!/usr/bin/env python3
"""SparBit von der Kommandozeile steuern.

    python cli.py status
    python cli.py kanaele liste
    python cli.py kanaele hinzufuegen discord "Mein Server" --set url=https://…
    python cli.py kanaele testen 1
    python cli.py quellen an mydealz
    python cli.py regeln hinzufuegen "Alles Gratis" --gratis --sofort --kanal 1
    python cli.py wunschliste hinzufuegen https://shop.de/artikel --ziel 199
    python cli.py preisfehler liste
    python cli.py preisfehler waechter --an --schwelle 65

Arbeitet direkt auf der Datenbank in ./data - laeuft also auch, wenn der
Server gerade aus ist. Wer die Datei lesen kann, hat ohnehin alles; ein
zusaetzliches Passwort waere hier nur Theater.

Aenderungen an Quellen greifen im laufenden Server binnen einer Minute; der
Scheduler gleicht seine Jobs regelmaessig mit der Datenbank ab.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _in_die_venv() -> None:
    """In die von run.py angelegte Umgebung wechseln.

    Dort liegen die Abhaengigkeiten. Ohne diesen Sprung scheitert
    'python cli.py' auf einem frischen Rechner an einem ImportError, obwohl
    alles laengst installiert ist.
    """
    if os.environ.get("SPARBIT_CLI_REEXEC"):
        return
    venv = ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin")
    python = venv / ("python.exe" if os.name == "nt" else "python")
    if not python.exists():
        return                                  # ohne .venv: einfach so laufen
    try:
        if Path(sys.executable).resolve() == python.resolve():
            return                              # schon drin
    except OSError:
        return
    os.environ["SPARBIT_CLI_REEXEC"] = "1"
    try:
        os.execv(str(python), [str(python), str(Path(__file__).resolve()),
                               *sys.argv[1:]])
    except OSError:
        pass                                    # dann eben mit dem aktuellen


def _utf8_ausgabe() -> None:
    """Die Konsole auf UTF-8 stellen.

    Die Windows-Konsole benutzt per Voreinstellung cp1252. Ein Pfeil oder ein
    Umlaut in der Ausgabe beendet die CLI dann mit einem UnicodeEncodeError -
    das Programm bricht also an seiner eigenen Tabellenzeichnung ab. Umlaute
    kommen in dieser CLI in jeder zweiten Ausgabe vor, insofern ist das kein
    Randfall.
    """
    for strom in (sys.stdout, sys.stderr):
        umstellen = getattr(strom, "reconfigure", None)
        if umstellen is not None:
            try:
                umstellen(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


_utf8_ausgabe()
_in_die_venv()
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("SPARBIT_DATA_DIR", str(ROOT / "data"))
os.environ.setdefault("SPARBIT_LOG_LEVEL", "WARNING")

# Farbe nur, wenn das Terminal sie darstellt.
_FARBE = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _FARBE else text


gruen = lambda t: _c(t, "32")     # noqa: E731
rot = lambda t: _c(t, "31")       # noqa: E731
gelb = lambda t: _c(t, "33")      # noqa: E731
grau = lambda t: _c(t, "90")      # noqa: E731
fett = lambda t: _c(t, "1")       # noqa: E731


def tabelle(kopf: list[str], zeilen: list[list[str]]) -> None:
    """Schlichte Tabelle, an der laengsten Zelle je Spalte ausgerichtet."""
    if not zeilen:
        print(grau("  (nichts vorhanden)"))
        return
    breiten = [max(len(str(kopf[i])), *(len(str(z[i])) for z in zeilen))
               for i in range(len(kopf))]
    print("  " + fett("  ".join(str(k).ljust(b) for k, b in zip(kopf, breiten, strict=True))))
    for zeile in zeilen:
        print("  " + "  ".join(str(z).ljust(b) for z, b in zip(zeile, breiten, strict=True)))


def beschnitten(text: str, laenge: int) -> str:
    """Kuerzen, aber sichtbar - sonst liest man eine halbe Bedingung als ganze."""
    return text if len(text) <= laenge else text[:laenge - 1] + "…"


def kuerze(werte: list, trenner: str, zeige: int = 3) -> str:
    sichtbar = trenner.join(str(w) for w in werte[:zeige])
    rest = len(werte) - zeige
    return f"{sichtbar} +{rest}" if rest > 0 else sichtbar


def ja_nein(wert: bool) -> str:
    return gruen("ja") if wert else grau("nein")


def fehler(text: str, code: int = 1) -> int:
    print(rot(f"  Fehler: {text}"))
    return code


def paare(werte: list[str] | None) -> dict:
    """--set schluessel=wert  ->  {"schluessel": wert} mit Typerkennung."""
    raus: dict = {}
    for eintrag in werte or []:
        if "=" not in eintrag:
            raise SystemExit(fehler(f"'{eintrag}' braucht die Form schluessel=wert"))
        schluessel, _, wert = eintrag.partition("=")
        schluessel, wert = schluessel.strip(), wert.strip()
        if wert.lower() in ("true", "ja", "an"):
            raus[schluessel] = True
        elif wert.lower() in ("false", "nein", "aus"):
            raus[schluessel] = False
        else:
            try:
                raus[schluessel] = int(wert)
            except ValueError:
                raus[schluessel] = wert
    return raus


def unbekannte_quelle(quellen_id: str) -> int:
    """Fehlermeldung mit Vorschlag - 'epic_free' statt 'epic' passiert schnell."""
    import difflib

    from app.sources import all_sources

    namen = sorted(q.id for q in all_sources())
    nahe = difflib.get_close_matches(quellen_id, namen, n=3, cutoff=0.6)
    text = f"Quelle '{quellen_id}' gibt es nicht."
    if nahe:
        text += f" Meintest du {', '.join(nahe)}?"
    else:
        text += " 'python cli.py quellen liste' zeigt alle."
    return fehler(text)


# --- status ----------------------------------------------------------------

def befehl_status(args) -> int:
    from datetime import timedelta

    from sqlalchemy import func, select

    from app.db import SessionLocal
    from app.models import Channel, Deal, Match, Rule, SourceConfig, WatchItem, utcnow

    with SessionLocal() as db:
        heute = utcnow() - timedelta(hours=24)
        quellen = list(db.scalars(select(SourceConfig)))
        aktiv = [q for q in quellen if q.enabled]
        gesperrt = [q for q in aktiv
                    if q.circuit_open_until and q.circuit_open_until > utcnow()]

        print(fett("\n  SparBit\n"))
        tabelle(["", ""], [
            ["Deals gesamt", str(db.scalar(select(func.count()).select_from(Deal)) or 0)],
            ["Neu (24 h)", str(db.scalar(select(func.count()).select_from(Deal)
                                         .where(Deal.first_seen >= heute)) or 0)],
            ["Treffer (24 h)", str(db.scalar(select(func.count()).select_from(Match)
                                             .where(Match.created_at >= heute)) or 0)],
            ["Quellen aktiv", f"{len(aktiv)} von {len(quellen)}"
                              + (rot(f"  ({len(gesperrt)} gesperrt)") if gesperrt else "")],
            ["Preisfehler (3 T)", _preisfehler_zaehler(db)],
            ["Regeln aktiv", str(db.scalar(select(func.count()).select_from(Rule)
                                           .where(Rule.enabled.is_(True))) or 0)],
            ["Kanäle", str(db.scalar(select(func.count()).select_from(Channel)) or 0)],
            ["Wunschliste", str(db.scalar(select(func.count()).select_from(WatchItem)) or 0)],
        ])
        print()
    return 0


def _preisfehler_zaehler(db) -> str:
    """Belegte Preisfehler der letzten drei Tage, rot wenn es welche gibt."""
    from datetime import timedelta

    from sqlalchemy import func, select

    from app.models import Deal, utcnow
    from app.pricefehler import HEISS

    anzahl = db.scalar(
        select(func.count()).select_from(Deal)
        .where(Deal.fehler_stufe == HEISS,
               Deal.first_seen >= utcnow() - timedelta(days=3))) or 0
    return rot(str(anzahl)) if anzahl else "0"


# --- preisfehler -----------------------------------------------------------

def befehl_preisfehler(args) -> int:
    """Die Funde auflisten, mit Begruendung."""
    from datetime import timedelta

    from sqlalchemy import desc, select

    from app.db import SessionLocal
    from app.models import Deal, utcnow
    from app.money import betrag
    from app.pricefehler import HEISS, VERDACHT

    stufen = [HEISS] if args.nur_belegt else [HEISS, VERDACHT]
    with SessionLocal() as db:
        funde = list(db.scalars(
            select(Deal)
            .where(Deal.fehler_stufe.in_(stufen),
                   Deal.last_seen >= utcnow() - timedelta(days=args.tage))
            .order_by(desc(Deal.fehler_score)).limit(args.anzahl)))

        if not funde:
            print(grau(f"\n  Keine Preisfehler in den letzten {args.tage} Tagen.\n"))
            return 0

        print(fett(f"\n  {len(funde)} Preisfehler\n"))
        for d in funde:
            marke = rot("BELEGT ") if d.fehler_stufe == HEISS else gelb("Verdacht")
            preis = betrag(d.preis, d.waehrung)
            erwartet = (f"  statt ~{betrag(d.fehler_erwartet_eur)}"
                        if d.fehler_erwartet_eur else "")
            print(f"  {marke} {str(d.fehler_score).rjust(3)}/100  "
                  f"{fett(preis)}{erwartet}")
            print(f"           {d.titel[:88]}")
            for grund in (d.fehler_gruende or [])[:3]:
                print(grau(f"           - {grund}"))
            print(grau(f"           {d.url}"))
            print()
    return 0


def befehl_preisfehler_pruefen(args) -> int:
    """Alle jungen Deals neu bewerten - nach einem Kurs- oder Schwellenwechsel."""
    from datetime import timedelta

    from sqlalchemy import desc, select

    from app import pricefehler
    from app.db import SessionLocal
    from app.models import Deal, utcnow

    with SessionLocal() as db:
        kandidaten = list(db.scalars(
            select(Deal)
            .where(Deal.first_seen >= utcnow() - timedelta(days=args.tage),
                   Deal.ist_gratis.is_(False), Deal.preis_eur.isnot(None))
            .order_by(desc(Deal.last_seen)).limit(2000)))
        print(f"  {len(kandidaten)} Deals werden geprüft ...")
        neu = pricefehler.aktualisiere(db, kandidaten)
        heiss = [d for d in kandidaten if d.fehler_stufe == pricefehler.HEISS]
        verdacht = [d for d in kandidaten if d.fehler_stufe == pricefehler.VERDACHT]
    print(gruen(f"  {len(heiss)} belegt, {len(verdacht)} Verdacht, "
                f"{len(neu)} davon neu"))
    print(grau("  Ansehen mit:  sparbit preisfehler liste\n"))
    return 0


def befehl_preisfehler_waechter(args) -> int:
    """Den Waechter ein- oder ausschalten und die Schwelle setzen."""
    from app.db import SessionLocal, get_setting, set_setting
    from app.pricefehler import SCHWELLE_HEISS

    with SessionLocal() as db:
        if args.an:
            set_setting(db, "preisfehler_waechter", True)
        elif args.aus:
            set_setting(db, "preisfehler_waechter", False)
        if args.schwelle is not None:
            set_setting(db, "preisfehler_schwelle",
                        max(30, min(100, args.schwelle)))
        db.commit()

        aktiv = bool(get_setting(db, "preisfehler_waechter", True))
        schwelle = int(get_setting(db, "preisfehler_schwelle", SCHWELLE_HEISS))

    print()
    print(f"  Wächter:  {gruen('an') if aktiv else grau('aus')}")
    print(f"  Schwelle: {schwelle} von 100 Punkten")
    if aktiv:
        print(grau("  Meldet an Regeln und Ruhezeiten vorbei über alle "
                   "aktiven Kanäle."))
    print()
    return 0


def befehl_feed_suche(args) -> int:
    """Welche Feeds zeichnet diese Adresse aus?

    Der Ausweg aus dem Pfad-Raten. Statt zu wissen, wie ein Shop seinen
    Feed nennt, fragt man ihn - und zwar von dem Rechner aus, der auch
    Netz hat.
    """
    import asyncio

    from app import feedfinder
    from app.http import PoliteClient

    url = args.url.strip()
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url

    async def lauf():
        client = PoliteClient()
        try:
            return await feedfinder.suche(client, url)
        finally:
            await client.aclose()

    ergebnis = asyncio.run(lauf())

    print()
    print(f"  {url}")
    print(f"  {ergebnis['detail']}")
    if not ergebnis["feeds"]:
        print(grau("\n  Tipp: eine Uebersichts- oder Kategorieseite probieren,"))
        print(grau("  nicht die Startseite - Feeds haengen meist an Rubriken.\n"))
        return 1
    print()
    tabelle(["Feed-Adresse", "Titel", "Herkunft"],
            [[f["url"], (f["titel"] or "-")[:34],
              "ausgezeichnet" if f["herkunft"] == "link" else "geraten"]
             for f in ergebnis["feeds"]])
    print(grau("\n  Eintragen mit: sparbit quellen … bzw. im UI unter "
               "Quellen → Einstellungen.\n"))
    return 0


# --- 18plus ----------------------------------------------------------------

def befehl_erwachsen(args) -> int:
    """Den 18+-Bereich schalten - mit derselben Huerde wie im Web."""
    from sqlalchemy import func, select

    from app import erwachsen as erw
    from app.db import SessionLocal, set_setting
    from app.models import Deal

    with SessionLocal() as db:
        if args.an:
            if not args.ich_bin_volljaehrig:
                return fehler(
                    "Zum Einschalten fehlt die Altersbestätigung. "
                    "Nochmal mit --ich-bin-volljaehrig.")
            erw.schalte(db, True, bestaetigt=True)
        elif args.aus:
            erw.schalte(db, False)
        if args.melden is not None:
            set_setting(db, erw.MELDEN, args.melden == "an")
            db.commit()

        zustand = erw.zustand(db)
        funde = db.scalar(select(func.count()).select_from(Deal)
                          .where(Deal.erwachsen.is_(True))) or 0

    from app.sources import all_sources
    quellen = [s for s in all_sources() if s.category.value == "erwachsen"]

    print()
    print(f"  18+-Bereich: {gruen('frei') if zustand['an'] else grau('aus')}")
    if zustand["an"]:
        print(f"  Zustellung:  "
              f"{gruen('an') if zustand['melden'] else grau('aus - nur auf der Seite')}")
        print(f"  Funde:       {funde}")
        print()
        print(fett("  Eigene Quellen"))
        for q in quellen:
            print(f"    {q.id:18} {q.display_name}")
        print(grau("\n  Keine davon ist geprüft. Erst 'sparbit quellen testen <id>',"))
        print(grau("  dann 'sparbit quellen an <id>'. Kandidaten stehen in ENDPOINTS.md."))
    else:
        print(grau("  Die Quellen laufen nicht, die Funde sind unsichtbar."))
        print(grau("  Einschalten: sparbit 18plus --an --ich-bin-volljaehrig"))
    print()
    return 0


# --- gratischeck -----------------------------------------------------------

def befehl_gratischeck(args) -> int:
    """Die Gegenprobe auf der Zielseite schalten und auswerten."""
    from datetime import timedelta

    from sqlalchemy import func, select

    from app import gratischeck as gc
    from app.db import SessionLocal, get_setting, set_setting
    from app.models import Deal, utcnow

    with SessionLocal() as db:
        if args.an:
            set_setting(db, gc.SETTING_AN, True)
        elif args.aus:
            set_setting(db, gc.SETTING_AN, False)
        if args.max_pro_lauf is not None:
            set_setting(db, gc.SETTING_MAX, max(0, min(60, args.max_pro_lauf)))
        db.commit()

        aktiv = bool(get_setting(db, gc.SETTING_AN, True))
        deckel = int(get_setting(db, gc.SETTING_MAX, gc.MAX_PRO_LAUF))
        zeilen = db.execute(
            select(Deal.check_status, func.count(Deal.id))
            .where(Deal.check_am >= utcnow() - timedelta(days=7))
            .group_by(Deal.check_status)).all()

    print()
    print(f"  Gegenprobe:  {gruen('an') if aktiv else grau('aus')}")
    print(f"  Höchstens:   {deckel} Seitenaufrufe je Lauf")
    if zeilen:
        print()
        print(fett("  Letzte sieben Tage"))
        for status, anzahl in sorted(zeilen, key=lambda z: -z[1]):
            if not status:
                continue
            name = gc.LABEL.get(status, status)
            farbe = (rot if status == gc.WIDERLEGT
                     else gelb if status == gc.ABGELAUFEN
                     else gruen if status == gc.BESTAETIGT else grau)
            print(f"    {anzahl:>4}×  {farbe(name)}")
    print(grau("\n  Ruft bei jedem Gratis-Fund die Zielseite auf. Findet sich dort"))
    print(grau("  keine ausgezeichnete Preisangabe, bleibt alles wie gemeldet."))
    print()
    return 0


# --- kanaele ---------------------------------------------------------------

def befehl_kanal_typen(args) -> int:
    from app.notify import all_channels

    print(fett("\n  Verfügbare Kanaltypen\n"))
    for kanal in all_channels():
        print(f"  {gruen(kanal.type.ljust(10))} {kanal.display_name}")
        print(f"  {grau('           ' + kanal.beschreibung)}")
        for feld in kanal.options_schema:
            marke = gelb(" (nötig)") if feld.pflicht else ""
            vorgabe = ""
            if not feld.pflicht and feld.default not in ("", None):
                vorgabe = grau(f"  [{feld.default}]")
            print(f"             {feld.key:<14} {feld.label}{marke}{vorgabe}")
        noetig = [f.key for f in kanal.options_schema if f.pflicht]
        beispiel = " ".join(f"--set {k}=…" for k in noetig)
        print(grau(f'             python cli.py kanaele hinzufuegen {kanal.type} '
                   f'"{kanal.display_name}" {beispiel}'))
        print()
    return 0


def befehl_kanal_liste(args) -> int:
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Channel

    with SessionLocal() as db:
        zeilen = [[str(k.id), k.type, k.name, ja_nein(k.enabled),
                   str(k.error_count) if k.error_count else grau("0")]
                  for k in db.scalars(select(Channel).order_by(Channel.id))]
    print()
    tabelle(["ID", "Typ", "Name", "Aktiv", "Fehler"], zeilen)
    print()
    return 0


def befehl_kanal_hinzufuegen(args) -> int:
    from app.db import SessionLocal
    from app.models import Channel
    from app.notify import get_channel

    impl = get_channel(args.typ)
    if impl is None:
        return fehler(f"Unbekannter Typ '{args.typ}'. "
                      f"'python cli.py kanaele typen' zeigt alle.")

    gesetzt = paare(args.set)
    unbekannt = set(gesetzt) - {f.key for f in impl.options_schema}
    if unbekannt:
        return fehler(f"Unbekannte Felder für {args.typ}: {', '.join(sorted(unbekannt))}. "
                      f"'python cli.py kanaele typen' zeigt die richtigen.")

    config = {feld.key: feld.default for feld in impl.options_schema}
    config.update(gesetzt)

    # Lieber hier meckern als spaeter still nicht zustellen.
    fehlend = [f for f in impl.options_schema
               if f.pflicht and config.get(f.key) in ("", None)]
    if fehlend:
        namen = ", ".join(f"{f.key} ({f.label})" for f in fehlend)
        return fehler(f"Für {args.typ} fehlt: {namen}")

    with SessionLocal() as db:
        kanal = Channel(type=args.typ, name=args.name, enabled=True, config=config)
        db.add(kanal)
        db.commit()
        db.refresh(kanal)
        print(gruen(f"\n  Kanal {kanal.id} „{kanal.name}“ ({kanal.type}) angelegt."))
        print(grau(f"  Prüfen mit: python cli.py kanaele testen {kanal.id}\n"))
    return 0


def befehl_kanal_aendern(args) -> int:
    from app.db import SessionLocal
    from app.models import Channel

    with SessionLocal() as db:
        kanal = db.get(Channel, args.id)
        if kanal is None:
            return fehler(f"Kanal {args.id} gibt es nicht.")
        if args.name:
            kanal.name = args.name
        if args.an:
            kanal.enabled = True
        if args.aus:
            kanal.enabled = False
        neu = paare(args.set)
        if neu:
            from app.notify import get_channel
            impl = get_channel(kanal.type)
            if impl is not None:
                unbekannt = set(neu) - {f.key for f in impl.options_schema}
                if unbekannt:
                    return fehler(f"Unbekannte Felder für {kanal.type}: "
                                  f"{', '.join(sorted(unbekannt))}")
            kanal.config = {**(kanal.config or {}), **neu}
        db.commit()
        print(gruen(f"\n  Kanal {kanal.id} aktualisiert.\n"))
    return 0


def befehl_kanal_loeschen(args) -> int:
    from app.db import SessionLocal
    from app.models import Channel

    with SessionLocal() as db:
        kanal = db.get(Channel, args.id)
        if kanal is None:
            return fehler(f"Kanal {args.id} gibt es nicht.")
        name = kanal.name
        db.delete(kanal)
        db.commit()
    print(gruen(f"\n  Kanal „{name}“ gelöscht.\n"))
    return 0


def befehl_kanal_testen(args) -> int:
    from app.db import SessionLocal
    from app.http import PoliteClient
    from app.models import Channel
    from app.notify import get_channel

    async def lauf() -> int:
        with SessionLocal() as db:
            ziele = ([db.get(Channel, args.id)] if args.id
                     else list(db.scalars(__import__("sqlalchemy").select(Channel))))
            ziele = [z for z in ziele if z is not None]
            if not ziele:
                return fehler("Kein Kanal gefunden.")

            http = PoliteClient()
            fehlgeschlagen = 0
            try:
                print()
                for kanal in ziele:
                    impl = get_channel(kanal.type)
                    if impl is None:
                        print(f"  {rot('?')} {kanal.name}: Typ '{kanal.type}' unbekannt")
                        fehlgeschlagen += 1
                        continue
                    try:
                        await impl.send_test(kanal.config or {}, http)
                        print(f"  {gruen('OK')}   {kanal.name} ({kanal.type})")
                    except Exception as exc:
                        print(f"  {rot('FEHL')} {kanal.name} ({kanal.type})")
                        print(f"       {grau(f'{type(exc).__name__}: {exc}'[:160])}")
                        fehlgeschlagen += 1
                print()
            finally:
                await http.aclose()
            return 1 if fehlgeschlagen else 0

    return asyncio.run(lauf())


# --- quellen ---------------------------------------------------------------

def befehl_quellen_liste(args) -> int:
    from sqlalchemy import select

    from app import erwachsen as erw
    from app.db import SessionLocal
    from app.models import SourceConfig, utcnow
    from app.sources import all_sources

    with SessionLocal() as db:
        cfgs = {c.id: c for c in db.scalars(select(SourceConfig))}
        # Genau wie im Web: solange der 18+-Bereich zu ist, gibt es diese
        # Quellen hier nicht. Sonst waere die CLI die Hintertuer.
        frei = erw.ist_aktiv(db)
        zeilen = []
        for quelle in all_sources():
            cfg = cfgs.get(quelle.id)
            if cfg is None:
                continue
            if quelle.category.value == "erwachsen" and not frei:
                continue
            if not cfg.enabled:
                zustand = grau("aus")
            elif cfg.circuit_open_until and cfg.circuit_open_until > utcnow():
                zustand = rot("gesperrt")
            elif cfg.consecutive_failures:
                zustand = gelb(f"{cfg.consecutive_failures} Fehler")
            else:
                zustand = gruen("an")
            pruefung = {"verified": gruen("geprüft"), "broken": rot("defekt")}.get(
                cfg.verification, grau("ungeprüft"))
            zeilen.append([quelle.id, zustand, pruefung,
                           f"{cfg.interval_seconds // 60} Min.",
                           str(cfg.total_items),
                           gruen("ja") if cfg.api_key else
                           (gelb("nötig") if quelle.requires_api_key else grau("–"))])
    print()
    tabelle(["Quelle", "Zustand", "Prüfung", "Intervall", "Gefunden", "Key"], zeilen)
    print()
    return 0


def _quelle_schalten(quellen_id: str, an: bool) -> int:
    from app import erwachsen as erw
    from app.db import SessionLocal
    from app.models import SourceConfig

    with SessionLocal() as db:
        cfg = db.get(SourceConfig, quellen_id)
        if cfg is None:
            return unbekannte_quelle(quellen_id)
        if erw.quelle_ist_18(quellen_id) and not erw.ist_aktiv(db):
            return fehler("Der 18+-Bereich ist nicht freigeschaltet. "
                          "Erst: sparbit 18plus --an --ich-bin-volljaehrig")
        cfg.enabled = an
        if an:
            cfg.consecutive_failures = 0
            cfg.circuit_open_until = None
        db.commit()
    print(gruen(f"\n  {quellen_id} {'eingeschaltet' if an else 'ausgeschaltet'}."))
    print(grau("  Der laufende Server übernimmt das binnen einer Minute.\n"))
    return 0


def befehl_quelle_an(args) -> int:
    return _quelle_schalten(args.quelle, True)


def befehl_quelle_aus(args) -> int:
    return _quelle_schalten(args.quelle, False)


def befehl_quelle_intervall(args) -> int:
    from app.db import SessionLocal
    from app.models import SourceConfig
    from app.sources import get_source

    quelle = get_source(args.quelle)
    if quelle is None:
        return unbekannte_quelle(args.quelle)
    sekunden = args.minuten * 60
    if sekunden < quelle.min_interval:
        print(gelb(f"  {args.minuten} Min. unterschreitet das Mindestintervall — "
                   f"setze {quelle.min_interval // 60} Min."))
        sekunden = quelle.min_interval

    with SessionLocal() as db:
        cfg = db.get(SourceConfig, args.quelle)
        if cfg is None:
            return fehler(f"Quelle '{args.quelle}' ist nicht eingerichtet.")
        cfg.interval_seconds = sekunden
        db.commit()
    print(gruen(f"\n  {args.quelle}: alle {sekunden // 60} Minuten.\n"))
    return 0


def befehl_quelle_testen(args) -> int:
    from app.db import SessionLocal
    from app.models import SourceConfig
    from app.scheduler import build_context
    from app.sources import all_sources, get_source

    async def lauf() -> int:
        ziele = ([get_source(args.quelle)] if args.quelle else all_sources())
        ziele = [z for z in ziele if z is not None]
        if not ziele:
            return unbekannte_quelle(args.quelle)

        schlecht = 0
        print()
        for quelle in ziele:
            with SessionLocal() as db:
                cfg = db.get(SourceConfig, quelle.id)
                if cfg is None:
                    continue
                if quelle.requires_api_key and not cfg.api_key:
                    print(f"  {gelb('----')} {quelle.id:<18} API-Key fehlt")
                    continue
                ctx = build_context(cfg)
            ergebnis = await quelle.health_check(ctx)
            # Was der Test gelernt hat, gilt auch fuer den echten Lauf -
            # sonst zeigt "testen" etwas anderes, als die Quelle danach tut.
            gelernt = {k: v for k, v in ctx.notizen.items()
                       if not k.startswith("_")}
            if ctx.notizen:
                with SessionLocal() as db:
                    cfg = db.get(SourceConfig, quelle.id)
                    if cfg is not None:
                        cfg.options = {**(cfg.options or {}), **ctx.notizen}
                        db.commit()
            if ergebnis.ok:
                print(f"  {gruen('OK')}   {quelle.id:<18} {ergebnis.items_found:>3} "
                      f"Einträge  {ergebnis.latency_ms:>5} ms")
            else:
                schlecht += 1
                print(f"  {rot('FEHL')} {quelle.id:<18} {ergebnis.detail[:70]}")
            for schluessel, wert in gelernt.items():
                print(f"       {gelb('korrigiert')} {schluessel} = {wert}")
        print()
        return 1 if schlecht else 0

    return asyncio.run(lauf())


def befehl_quelle_jetzt(args) -> int:
    from app.scheduler import run_source, shutdown
    from app.sources import get_source

    if get_source(args.quelle) is None:
        return unbekannte_quelle(args.quelle)

    async def lauf() -> int:
        ergebnis = await run_source(args.quelle, manual=True)
        if ergebnis.get("error"):
            print(rot(f"\n  Fehler: {ergebnis['error']}\n"))
            await shutdown()
            return 1
        print(gruen(f"\n  {ergebnis.get('items', 0)} Einträge, "
                    f"{ergebnis.get('new_items', 0)} davon neu "
                    f"({ergebnis.get('duration_ms', 0)} ms).\n"))
        await shutdown()
        return 0

    return asyncio.run(lauf())


# --- regeln ----------------------------------------------------------------

def befehl_regeln_liste(args) -> int:
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Rule

    with SessionLocal() as db:
        zeilen = []
        for regel in db.scalars(select(Rule).order_by(Rule.id)):
            bedingungen = []
            if regel.nur_gratis:
                bedingungen.append("gratis")
            # Stichworte sind ODER, Pflichtworte UND, Blacklist schliesst aus -
            # das Zeichen dazwischen sagt genau das.
            if regel.keywords:
                bedingungen.append(kuerze(regel.keywords, " oder "))
            if regel.required_keywords:
                bedingungen.append(kuerze(regel.required_keywords, " und "))
            if regel.blacklist:
                bedingungen.append("ohne " + kuerze(regel.blacklist, "/"))
            if regel.max_preis is not None:
                bedingungen.append(f"≤{regel.max_preis:g}€")
            if regel.min_rabatt_prozent is not None:
                bedingungen.append(f"≥{regel.min_rabatt_prozent:g}%")
            if regel.min_urteil:
                bedingungen.append(f"Urteil≥{regel.min_urteil}")
            if regel.min_fehler_score:
                bedingungen.append(f"Preisfehler≥{regel.min_fehler_score}")
            if regel.sources:
                bedingungen.append("Quelle " + kuerze(regel.sources, "/"))
            if regel.haendler:
                bedingungen.append("bei " + kuerze(regel.haendler, "/"))
            zeilen.append([
                str(regel.id), regel.name[:28], ja_nein(regel.enabled),
                gelb("SOFORT") if regel.priority == "SOFORT" else "normal",
                beschnitten(", ".join(bedingungen), 44) or grau("–"),
                ",".join(map(str, regel.channels or [])) or rot("kein Kanal"),
                str(regel.match_count),
            ])
    print()
    tabelle(["ID", "Name", "Aktiv", "Prio", "Bedingungen", "Kanäle", "Treffer"], zeilen)
    print()
    return 0


def befehl_regel_hinzufuegen(args) -> int:
    from app.db import SessionLocal
    from app.models import Rule

    regel = Rule(
        name=args.name,
        enabled=True,
        priority="SOFORT" if args.sofort else "NORMAL",
        keywords=args.keyword or [],
        required_keywords=args.pflicht or [],
        blacklist=args.blacklist or [],
        max_preis=args.max_preis,
        min_rabatt_prozent=args.min_rabatt,
        nur_gratis=args.gratis,
        min_urteil=args.urteil,
        min_fehler_score=args.preisfehler,
        sources=args.quelle or [],
        kategorien=[], haendler=args.haendler or [],
        channels=args.kanal or [],
    )
    if not any([regel.keywords, regel.required_keywords, regel.nur_gratis,
                regel.max_preis is not None, regel.min_rabatt_prozent is not None,
                regel.min_urteil, regel.min_fehler_score, regel.sources,
                regel.haendler]):
        return fehler("Die Regel hat keine Bedingung — sie würde nichts treffen. "
                      "Mindestens eine Option angeben (--gratis, --keyword, …).")
    doppelt = ({w.lower() for w in regel.keywords + regel.required_keywords}
               & {w.lower() for w in regel.blacklist})
    if doppelt:
        return fehler(f"{', '.join(sorted(doppelt))} steht zugleich in der "
                      f"Blacklist — so trifft die Regel nie.")
    if not regel.channels:
        print(gelb("  Hinweis: ohne --kanal wird nichts zugestellt."))

    with SessionLocal() as db:
        db.add(regel)
        db.commit()
        db.refresh(regel)
        print(gruen(f"\n  Regel {regel.id} „{regel.name}“ angelegt.\n"))
    return 0


def _regel_schalten(regel_id: int, an: bool) -> int:
    from app.db import SessionLocal
    from app.models import Rule

    with SessionLocal() as db:
        regel = db.get(Rule, regel_id)
        if regel is None:
            return fehler(f"Regel {regel_id} gibt es nicht.")
        regel.enabled = an
        db.commit()
        name = regel.name
    print(gruen(f"\n  Regel „{name}“ {'aktiv' if an else 'pausiert'}.\n"))
    return 0


def befehl_regel_an(args) -> int:
    return _regel_schalten(args.id, True)


def befehl_regel_aus(args) -> int:
    return _regel_schalten(args.id, False)


def befehl_regel_loeschen(args) -> int:
    from app.db import SessionLocal
    from app.models import Rule

    with SessionLocal() as db:
        regel = db.get(Rule, args.id)
        if regel is None:
            return fehler(f"Regel {args.id} gibt es nicht.")
        name = regel.name
        db.delete(regel)
        db.commit()
    print(gruen(f"\n  Regel „{name}“ gelöscht.\n"))
    return 0


def befehl_regel_testen(args) -> int:
    """Zeigt, wie viele der letzten Deals eine Regel getroffen haette."""
    from sqlalchemy import desc, select

    from app.db import SessionLocal
    from app.filters import RuleSpec, preview
    from app.models import Deal, Rule

    with SessionLocal() as db:
        regel = db.get(Rule, args.id)
        if regel is None:
            return fehler(f"Regel {args.id} gibt es nicht.")
        deals = list(db.scalars(select(Deal).order_by(desc(Deal.first_seen))
                                .limit(args.anzahl)))
        ergebnis = preview(RuleSpec.from_model(regel), deals)

    print(fett(f"\n  {regel.name}\n"))
    print(f"  {gruen(str(ergebnis['treffer']))} von {ergebnis['geprueft']} Deals "
          f"({ergebnis['trefferquote']} %)\n")
    for beispiel in ergebnis["beispiele"][:8]:
        preis = "gratis" if beispiel["ist_gratis"] else (
            f"{beispiel['preis']:.2f} €" if beispiel["preis"] is not None else "—")
        print(f"  {gruen('+')} {beispiel['titel'][:58]:<60} {preis}")
    if ergebnis["knapp_verfehlt"]:
        print(grau("\n  Knapp verfehlt:"))
        for beispiel in ergebnis["knapp_verfehlt"][:4]:
            print(grau(f"  - {beispiel['titel'][:58]:<60} "
                       f"{beispiel['verfehlt'][0][:34]}"))
    print()
    return 0


# --- wunschliste -----------------------------------------------------------

def befehl_watch_liste(args) -> int:
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import WatchItem

    with SessionLocal() as db:
        zeilen = []
        for eintrag in db.scalars(select(WatchItem).order_by(WatchItem.id)):
            preis = (f"{eintrag.letzter_preis:.2f} {eintrag.waehrung}"
                     if eintrag.letzter_preis is not None else grau("—"))
            ziel = (f"{eintrag.ziel_preis:.2f}" if eintrag.ziel_preis is not None
                    else grau("—"))
            if eintrag.letzter_fehler:
                zustand = rot("Fehler")
            elif not eintrag.aktiv:
                zustand = grau("aus")
            elif (eintrag.ziel_preis is not None and eintrag.letzter_preis is not None
                  and eintrag.letzter_preis <= eintrag.ziel_preis):
                zustand = gruen("Ziel erreicht")
            else:
                zustand = "beobachtet"
            zeilen.append([str(eintrag.id), eintrag.name[:34], preis, ziel, zustand])
    print()
    tabelle(["ID", "Name", "Preis", "Ziel", "Zustand"], zeilen)
    print()
    return 0


def befehl_watch_hinzufuegen(args) -> int:
    from app.db import SessionLocal
    from app.http import PoliteClient
    from app.models import WatchItem
    from app.pricewatch import pruefe

    async def lauf() -> int:
        with SessionLocal() as db:
            eintrag = WatchItem(name=args.name or args.url, url=args.url,
                                ziel_preis=args.ziel,
                                intervall_minuten=args.intervall)
            db.add(eintrag)
            db.commit()
            db.refresh(eintrag)

            http = PoliteClient()
            try:
                fund = await pruefe(db, eintrag, http)
            finally:
                await http.aclose()
            db.refresh(eintrag)

            if fund is None:
                print(rot(f"\n  Aufgenommen als {eintrag.id}, aber der Preis war "
                          f"nicht lesbar:"))
                print(grau(f"  {eintrag.letzter_fehler}\n"))
                return 1
            if not args.name:
                eintrag.name = fund.name or args.url
                db.commit()
            print(gruen(f"\n  {eintrag.name}"))
            print(f"  {fund.preis:.2f} {fund.waehrung} — gelesen aus {fund.quelle}")
            if args.ziel:
                print(grau(f"  Meldung ab {args.ziel:.2f} €"))
            print()
        return 0

    return asyncio.run(lauf())


def befehl_watch_entfernen(args) -> int:
    from app.db import SessionLocal
    from app.models import WatchItem

    with SessionLocal() as db:
        eintrag = db.get(WatchItem, args.id)
        if eintrag is None:
            return fehler(f"Eintrag {args.id} gibt es nicht.")
        name = eintrag.name
        db.delete(eintrag)
        db.commit()
    print(gruen(f"\n  „{name}“ entfernt.\n"))
    return 0


def befehl_watch_pruefen(args) -> int:
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.http import PoliteClient
    from app.models import WatchItem
    from app.pricewatch import pruefe

    async def lauf() -> int:
        with SessionLocal() as db:
            ziele = ([db.get(WatchItem, args.id)] if args.id
                     else list(db.scalars(select(WatchItem))))
            ziele = [z for z in ziele if z is not None]
            if not ziele:
                return fehler("Kein Eintrag gefunden.")

            http = PoliteClient()
            schlecht = 0
            try:
                print()
                for eintrag in ziele:
                    fund = await pruefe(db, eintrag, http)
                    if fund is None:
                        schlecht += 1
                        print(f"  {rot('FEHL')} {eintrag.name[:40]:<42} "
                              f"{grau((eintrag.letzter_fehler or '')[:50])}")
                    else:
                        print(f"  {gruen('OK')}   {eintrag.name[:40]:<42} "
                              f"{fund.preis:.2f} {fund.waehrung}")
                print()
            finally:
                await http.aclose()
            return 1 if schlecht else 0

    return asyncio.run(lauf())


# --- deals -----------------------------------------------------------------

def befehl_deals(args) -> int:
    from sqlalchemy import desc, or_, select

    from app.db import SessionLocal
    from app.models import Deal
    from app.search import fts_verfuegbar, match_bedingung

    with SessionLocal() as db:
        stmt = select(Deal)
        if args.suche:
            treffer = (match_bedingung(args.suche)
                       if fts_verfuegbar(db.get_bind()) else None)
            if treffer is not None:
                stmt = stmt.where(Deal.id.in_(treffer))
            else:
                like = f"%{args.suche}%"
                stmt = stmt.where(or_(Deal.titel.ilike(like),
                                      Deal.beschreibung.ilike(like)))
        if args.gratis:
            stmt = stmt.where(Deal.ist_gratis.is_(True))
        if args.urteil:
            from app.verdict import mindestens
            stmt = stmt.where(Deal.urteil.in_(mindestens(args.urteil)))

        zeilen = []
        for deal in db.scalars(stmt.order_by(desc(Deal.first_seen)).limit(args.anzahl)):
            preis = (gruen("gratis") if deal.ist_gratis else
                     f"{deal.preis:.2f} {deal.waehrung}" if deal.preis is not None
                     else grau("—"))
            urteil = {"bestpreis": gruen("Bestpreis"),
                      "sehr_gut": gruen("sehr gut"),
                      "gut": "gut",
                      "teurer": gelb("war günstiger"),
                      "uvp_fragwuerdig": rot("UVP fragwürdig")}.get(
                          deal.urteil or "", grau("—"))
            zeilen.append([deal.titel[:46], preis, urteil, deal.quelle])
    print()
    tabelle(["Titel", "Preis", "Urteil", "Quelle"], zeilen)
    print()
    return 0


# --- Argumente -------------------------------------------------------------

def baue_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python cli.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    bereiche = p.add_subparsers(dest="bereich", required=True)

    bereiche.add_parser("status", help="Überblick").set_defaults(fn=befehl_status)

    # kanaele
    k = bereiche.add_parser("kanaele", help="Benachrichtigungskanäle")
    kb = k.add_subparsers(dest="befehl", required=True)
    kb.add_parser("typen", help="verfügbare Kanaltypen").set_defaults(fn=befehl_kanal_typen)
    kb.add_parser("liste", help="eingerichtete Kanäle").set_defaults(fn=befehl_kanal_liste)

    kh = kb.add_parser("hinzufuegen", help="neuen Kanal anlegen")
    kh.add_argument("typ", help="discord, telegram, slack, …")
    kh.add_argument("name")
    kh.add_argument("--set", action="append", metavar="SCHLUESSEL=WERT")
    kh.set_defaults(fn=befehl_kanal_hinzufuegen)

    ka = kb.add_parser("aendern", help="Kanal ändern")
    ka.add_argument("id", type=int)
    ka.add_argument("--name")
    ka.add_argument("--an", action="store_true")
    ka.add_argument("--aus", action="store_true")
    ka.add_argument("--set", action="append", metavar="SCHLUESSEL=WERT")
    ka.set_defaults(fn=befehl_kanal_aendern)

    kl = kb.add_parser("loeschen", help="Kanal entfernen")
    kl.add_argument("id", type=int)
    kl.set_defaults(fn=befehl_kanal_loeschen)

    kt = kb.add_parser("testen", help="Testnachricht senden")
    kt.add_argument("id", type=int, nargs="?", help="leer = alle Kanäle")
    kt.set_defaults(fn=befehl_kanal_testen)

    # quellen
    q = bereiche.add_parser("quellen", help="Deal-Quellen")
    qb = q.add_subparsers(dest="befehl", required=True)
    qb.add_parser("liste", help="alle Quellen").set_defaults(fn=befehl_quellen_liste)

    qa = qb.add_parser("an", help="Quelle einschalten")
    qa.add_argument("quelle")
    qa.set_defaults(fn=befehl_quelle_an)

    qx = qb.add_parser("aus", help="Quelle ausschalten")
    qx.add_argument("quelle")
    qx.set_defaults(fn=befehl_quelle_aus)

    qi = qb.add_parser("intervall", help="Abstand zwischen Läufen setzen")
    qi.add_argument("quelle")
    qi.add_argument("minuten", type=int)
    qi.set_defaults(fn=befehl_quelle_intervall)

    qt = qb.add_parser("testen", help="Erreichbarkeit prüfen")
    qt.add_argument("quelle", nargs="?", help="leer = alle Quellen")
    qt.set_defaults(fn=befehl_quelle_testen)

    qj = qb.add_parser("jetzt", help="sofort einen Lauf starten")
    qj.add_argument("quelle")
    qj.set_defaults(fn=befehl_quelle_jetzt)

    # regeln
    r = bereiche.add_parser("regeln", help="Filterregeln")
    rb = r.add_subparsers(dest="befehl", required=True)
    rb.add_parser("liste", help="alle Regeln").set_defaults(fn=befehl_regeln_liste)

    rh = rb.add_parser("hinzufuegen", help="neue Regel anlegen")
    rh.add_argument("name")
    rh.add_argument("--keyword", action="append", help="ODER-Stichwort (mehrfach)")
    rh.add_argument("--pflicht", action="append", help="muss vorkommen (mehrfach)")
    rh.add_argument("--blacklist", action="append", help="schließt aus (mehrfach)")
    rh.add_argument("--gratis", action="store_true", help="nur 0-€-Funde")
    rh.add_argument("--max-preis", type=float, dest="max_preis")
    rh.add_argument("--min-rabatt", type=float, dest="min_rabatt")
    rh.add_argument("--preisfehler", type=int, metavar="PUNKTE",
                    help="nur Deals ab so vielen Preisfehler-Punkten (z. B. 70)")
    rh.add_argument("--urteil", choices=["bestpreis", "sehr_gut", "gut", "normal"],
                    help="Mindest-Preisurteil")
    rh.add_argument("--quelle", action="append", help="nur diese Quellen")
    rh.add_argument("--haendler", action="append")
    rh.add_argument("--kanal", action="append", type=int, help="Kanal-ID (mehrfach)")
    rh.add_argument("--sofort", action="store_true", help="Priorität SOFORT")
    rh.set_defaults(fn=befehl_regel_hinzufuegen)

    ra = rb.add_parser("an", help="Regel aktivieren")
    ra.add_argument("id", type=int)
    ra.set_defaults(fn=befehl_regel_an)

    rx = rb.add_parser("aus", help="Regel pausieren")
    rx.add_argument("id", type=int)
    rx.set_defaults(fn=befehl_regel_aus)

    rl = rb.add_parser("loeschen", help="Regel entfernen")
    rl.add_argument("id", type=int)
    rl.set_defaults(fn=befehl_regel_loeschen)

    rt = rb.add_parser("testen", help="gegen die letzten Deals durchrechnen")
    rt.add_argument("id", type=int)
    rt.add_argument("--anzahl", type=int, default=500)
    rt.set_defaults(fn=befehl_regel_testen)

    # wunschliste
    w = bereiche.add_parser("wunschliste", help="selbst beobachtete Artikel")
    wb = w.add_subparsers(dest="befehl", required=True)
    wb.add_parser("liste", help="alle Einträge").set_defaults(fn=befehl_watch_liste)

    wh = wb.add_parser("hinzufuegen", help="Artikel beobachten")
    wh.add_argument("url")
    wh.add_argument("--name", help="leer = aus der Seite lesen")
    wh.add_argument("--ziel", type=float, help="Zielpreis in Euro")
    wh.add_argument("--intervall", type=int, default=180, help="Minuten")
    wh.set_defaults(fn=befehl_watch_hinzufuegen)

    we = wb.add_parser("entfernen", help="nicht mehr beobachten")
    we.add_argument("id", type=int)
    we.set_defaults(fn=befehl_watch_entfernen)

    wp = wb.add_parser("pruefen", help="Preis jetzt abfragen")
    wp.add_argument("id", type=int, nargs="?", help="leer = alle")
    wp.set_defaults(fn=befehl_watch_pruefen)

    # deals
    # --- preisfehler ---
    f = bereiche.add_parser("preisfehler", help="Preisfehler-Funde und Wächter")
    fb = f.add_subparsers(dest="unterbefehl", required=True)
    fl = fb.add_parser("liste", help="gefundene Preisfehler")
    fl.add_argument("--tage", type=int, default=7)
    fl.add_argument("--anzahl", type=int, default=20)
    fl.add_argument("--nur-belegt", action="store_true", dest="nur_belegt",
                    help="Verdachtsfälle ausblenden")
    fl.set_defaults(fn=befehl_preisfehler)

    fp = fb.add_parser("pruefen", help="alle jungen Deals neu bewerten")
    fp.add_argument("--tage", type=int, default=7)
    fp.set_defaults(fn=befehl_preisfehler_pruefen)

    fw = fb.add_parser("waechter", help="Sofortmeldung ein-/ausschalten")
    fw.add_argument("--an", action="store_true")
    fw.add_argument("--aus", action="store_true")
    fw.add_argument("--schwelle", type=int,
                    help="ab wie vielen Punkten gemeldet wird (30-100)")
    fw.set_defaults(fn=befehl_preisfehler_waechter)

    fs = bereiche.add_parser("feed-suche",
                             help="welchen Feed bietet eine Adresse an?")
    fs.add_argument("url", help="Shop- oder Übersichtsseite")
    fs.set_defaults(fn=befehl_feed_suche)

    e = bereiche.add_parser("18plus", help="18+-Bereich (standardmäßig aus)")
    e.add_argument("--an", action="store_true", help="freischalten")
    e.add_argument("--aus", action="store_true", help="wieder abschalten")
    e.add_argument("--ich-bin-volljaehrig", action="store_true",
                   dest="ich_bin_volljaehrig",
                   help="Altersbestätigung, ohne die --an nicht greift")
    e.add_argument("--melden", choices=["an", "aus"],
                   help="18+-Funde auch über die Kanäle zustellen")
    e.set_defaults(fn=befehl_erwachsen)

    g = bereiche.add_parser("gratischeck",
                            help="Gegenprobe auf der Zielseite")
    g.add_argument("--an", action="store_true")
    g.add_argument("--aus", action="store_true")
    g.add_argument("--max-pro-lauf", type=int, dest="max_pro_lauf",
                   help="Deckel für Seitenaufrufe je Quellenlauf (0-60)")
    g.set_defaults(fn=befehl_gratischeck)

    d = bereiche.add_parser("deals", help="gesammelte Deals ansehen")
    d.add_argument("suche", nargs="?", help='z. B. lego oder "nintendo switch"')
    d.add_argument("--gratis", action="store_true")
    d.add_argument("--urteil", choices=["bestpreis", "sehr_gut", "gut", "normal"])
    d.add_argument("--anzahl", type=int, default=20)
    d.set_defaults(fn=befehl_deals)

    return p


def main() -> int:
    args = baue_parser().parse_args()
    try:
        from app.db import init_db
        from app.scheduler import ensure_source_rows
        init_db()
        # Damit 'quellen an …' auch auf einer frischen Datenbank geht, ohne
        # dass der Server vorher einmal gelaufen sein muss.
        ensure_source_rows()
    except Exception as exc:
        return fehler(f"Datenbank nicht nutzbar: {exc}")
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        print()
        return 130


if __name__ == "__main__":
    sys.exit(main())
