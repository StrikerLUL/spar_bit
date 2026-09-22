"""Die Sammelmeldung als Mail, die man auch lesen mag.

Bisher ging jede Mail als reiner Text raus: Titel, Preis, Link,
untereinander. Bei einem einzelnen Fund geht das in Ordnung. Bei einer
Sammelmeldung mit zwanzig Deals ist es eine Wand, in der das
Interessante - der Bestpreis, der Preisfehler - genauso aussieht wie
der Rest.

Darum HTML mit Tabelle und Bild, und der Text bleibt als Alternative
darunter: Mail-Programme, die kein HTML anzeigen (oder es nicht sollen),
bekommen weiter die Fassung, die sie bisher bekamen. Verloren geht so
nichts.

Alles inline formatiert und ohne externe Stile - Mail-Programme werfen
<style>-Bloecke gern weg, und Gmail tut es zuverlaessig.
"""
from __future__ import annotations

import html

from . import money

RAHMEN = "#e5e7eb"
GEDAEMPFT = "#6b7280"
AKZENT = "#2563eb"
GRATIS = "#059669"
FEHLER = "#dc2626"


def _e(text) -> str:
    return html.escape(str(text or ""), quote=True)


def _preiszeile(note) -> str:
    if note.ist_gratis or (note.preis is not None and note.preis <= 0.009):
        return f'<span style="color:{GRATIS};font-weight:700">GRATIS</span>'
    teile = [f'<strong>{_e(money.preiszeile(note.preis, note.waehrung, eur=note.preis_eur))}</strong>']
    if note.originalpreis and note.preis is not None and note.originalpreis > note.preis:
        teile.append(f'<span style="color:{GEDAEMPFT};text-decoration:line-through">'
                     f'{_e(money.betrag(note.originalpreis, note.waehrung))}</span>')
    if note.rabatt_prozent:
        teile.append(f'<span style="color:{GRATIS}">-{int(note.rabatt_prozent)}%</span>')
    return " ".join(teile)


def _marke(note) -> str:
    if note.fehler_stufe:
        return (f'<span style="color:{FEHLER};font-weight:700">'
                f'Preisfehler-Verdacht</span> ')
    if note.urteil == "bestpreis":
        return f'<span style="color:{GRATIS};font-weight:700">Bestpreis</span> '
    return ""


def _eintrag(note) -> str:
    bild = ""
    if note.bild:
        bild = (f'<td width="72" style="padding:0 12px 0 0;vertical-align:top">'
                f'<img src="{_e(note.bild)}" width="64" height="64" alt="" '
                f'style="border-radius:8px;object-fit:cover;display:block"></td>')

    unten = []
    if note.haendler:
        unten.append(_e(note.haendler))
    if note.urteil_text:
        unten.append(_e(note.urteil_text))
    if note.regel:
        unten.append(f"Regel: {_e(note.regel)}")

    return f"""
      <tr>
        <td style="padding:14px 0;border-bottom:1px solid {RAHMEN}">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
            {bild}
            <td style="vertical-align:top">
              <a href="{_e(note.url)}" style="color:{AKZENT};font-size:15px;
                 font-weight:600;text-decoration:none">{_marke(note)}{_e(note.titel)}</a>
              <div style="margin-top:6px;font-size:14px">{_preiszeile(note)}</div>
              <div style="margin-top:4px;font-size:12px;color:{GEDAEMPFT}">
                {" · ".join(unten)}</div>
            </td>
          </tr></table>
        </td>
      </tr>"""


def _huelle(titel: str, vorspann: str, inhalt: str) -> str:
    return f"""<!doctype html>
<html lang="de"><body style="margin:0;padding:0;background:#f9fafb">
  <div style="display:none;max-height:0;overflow:hidden">{_e(vorspann)}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
         style="background:#f9fafb;padding:24px 12px">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
             style="max-width:600px;background:#ffffff;border:1px solid {RAHMEN};
                    border-radius:12px;padding:24px;
                    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',
                                Roboto,Helvetica,Arial,sans-serif;color:#111827">
        <tr><td>
          <div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;
                      color:{GEDAEMPFT}">SparBit</div>
          <h1 style="margin:6px 0 16px;font-size:19px;font-weight:700">{_e(titel)}</h1>
        </td></tr>
        {inhalt}
        <tr><td style="padding-top:18px;font-size:11px;color:{GEDAEMPFT}">
          Gesendet von deiner eigenen SparBit-Installation.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def einzeln(note) -> str:
    return _huelle(
        ("Gratis: " if note.ist_gratis else "") + (note.titel or ""),
        note.preis_text(),
        f'<tr><td><table role="presentation" width="100%" cellpadding="0" '
        f'cellspacing="0">{_eintrag(note)}</table></td></tr>'
        + (f'<tr><td style="padding-top:14px;font-size:13px;color:{GEDAEMPFT}">'
           f'{_e(note.beschreibung)[:400]}</td></tr>' if note.beschreibung else ""))


def sammel(meldung) -> str:
    zeilen = "".join(_eintrag(n) for n in meldung.beste[:20])
    rest = meldung.anzahl - min(meldung.anzahl, 20)
    if rest:
        zeilen += (f'<tr><td style="padding:12px 0;font-size:13px;color:{GEDAEMPFT}">'
                   f'… und {rest} weitere</td></tr>')
    return _huelle(
        meldung.titel,
        f"{meldung.anzahl} Funde {meldung.zeitraum}".strip(),
        f'<tr><td><table role="presentation" width="100%" cellpadding="0" '
        f'cellspacing="0">{zeilen}</table></td></tr>')
