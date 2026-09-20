"""Reddit ueber die oeffentlichen .rss-Endpunkte.

Subreddits sind im UI pflegbar. Kein API-Key noetig, aber Reddit ist bei
Cloud-/Rechenzentrums-IPs streng: erwarte 403/429, wenn der VPS in einem
bekannten Hosting-Netz steht. Der Circuit Breaker faengt das ab, und der
User-Agent ist bewusst sprechend (das verlangt Reddit ausdruecklich).

Drei Zeilen aus einem Betriebsbericht haben diese Datei umgebaut:

    r/SexToyDeals: HTTPStatusError: Client error '404 Not Found'
    r/NSFWdeals: RateLimited: HTTP 429, retry after 58s
    r/AdultDeals: RateLimited: HTTP 429, retry after 58s

Das sind zwei verschiedene Probleme, die frueher gleich aussahen - beide
landeten als "Quelle kaputt" im Log.

**404 heisst: diesen Subreddit gibt es nicht.** Daran aendert kein
Wiederholen etwas, und jeder weitere Lauf verbrennt nur Anfragen an einem
Host, der ohnehin knausert. Solche Namen streicht die Quelle jetzt selbst
aus der Liste und legt sie unter "Automatisch entfernt" ab - sichtbar, mit
Grund, und jederzeit wieder eintragbar.

**429 heisst: Reddit drosselt diesen Server.** Der Subreddit ist in Ordnung,
nur zu schnell gefragt. Dann hat es keinen Sinn, die restlichen Subreddits
noch anzuklopfen (der Client sperrt den Host ohnehin fuer die genannte
Dauer) - die Quelle bricht ab, merkt sich, wo sie stand, und faengt beim
naechsten Lauf genau dort wieder an. So kommt auch bei dauerhafter Drosselung
jeder Subreddit regelmaessig dran, statt dass immer dieselben ersten zwei
das Kontingent aufbrauchen.

Verifizierungsstand: UNVERIFIED - in der Build-Session nicht live pruefbar.
"""
from __future__ import annotations

import re

from .. import feedfinder
from ..http import RateLimited
from ..priceparse import parse_price_text
from .base import (Category, DealItem, FetchContext, OptionSpec, Source,
                   Verification, register)
from .rssutil import (entry_body, entry_datetime, first_image, parse_feed,
                      strip_html)

# r/GameDeals-Konvention: "[Steam] Titel (75% off / 4,99€)"
_STORE_RE = re.compile(r"^\s*\[([^\]]{1,40})\]")

# Was Reddit als Subreddit-Namen akzeptiert. Alles andere fuehrt garantiert
# zu einem 404, den man sich sparen kann.
_NAME_RE = re.compile(r"^[A-Za-z0-9_]{2,21}$")


def _status(exc: Exception) -> int | None:
    """HTTP-Status aus einer Fehler-Ausnahme, falls sie einen traegt."""
    code = getattr(getattr(exc, "response", None), "status_code", None)
    return int(code) if isinstance(code, int) else None


def _saubere_namen(roh) -> list[str]:
    """Eingaben zu Subreddit-Namen machen - ohne Dubletten, ohne Unsinn.

    Erlaubt ist, was Leute tatsaechlich hineinkopieren: "r/GameDeals",
    "/r/GameDeals/", eine ganze URL. Was danach kein gueltiger Name ist,
    faellt raus, bevor es eine Anfrage kostet.
    """
    raus: list[str] = []
    gesehen: set[str] = set()
    for eintrag in roh or []:
        name = str(eintrag).strip()
        if not name:
            continue
        if "//" in name:                       # ganze URL hineinkopiert
            name = name.split("//", 1)[1].split("/r/", 1)[-1]
        name = name.strip("/").removeprefix("r/").removeprefix("R/").strip("/")
        name = name.split("/")[0].split("?")[0]
        if not _NAME_RE.match(name) or name.lower() in gesehen:
            continue
        gesehen.add(name.lower())
        raus.append(name)
    return raus


class Reddit(Source):
    id = "reddit"
    display_name = "Reddit"
    category = Category.REDDIT
    default_interval = 600
    min_interval = 300
    verification = Verification.UNVERIFIED
    docs_url = "https://www.reddit.com/wiki/api"
    beschreibung = ("Oeffentliche .rss-Feeds mehrerer Subreddits. "
                    "Subreddits hier pflegbar.")

    options_schema = [
        OptionSpec("subreddits", "Subreddits", "list",
                   ["GameDeals", "FreeGameFindings", "freebies",
                    "googleplaydeals", "AppHookup", "Schnaeppchen"],
                   help="Ohne 'r/'. Einer pro Zeile. Was Reddit mit 404 "
                        "beantwortet, streicht SparBit selbst."),
        OptionSpec("listing", "Sortierung", "select", "new",
                   choices=["new", "hot", "top"],
                   help="new = alles sofort, hot = nur was Zulauf hat."),
        OptionSpec("base", "Basis-Host", "string", "https://www.reddit.com",
                   help="Alternative: https://old.reddit.com"),
        OptionSpec("max_pro_lauf", "Subreddits pro Lauf", "int", 0,
                   help="0 = alle. Kleiner setzen, wenn Reddit diesen Server "
                        "drosselt (429): die Quelle arbeitet die Liste dann "
                        "ueber mehrere Laeufe ab, statt bei denselben ersten "
                        "beiden haengenzubleiben."),
        OptionSpec("entfernt", "Automatisch entfernt (404)", "list", [],
                   help="Subreddits, die es laut Reddit nicht gibt. Nur zur "
                        "Ansicht - wer meint, es war ein Irrtum, traegt den "
                        "Namen oben wieder ein."),
    ]

    async def fetch(self, ctx: FetchContext) -> list[DealItem]:
        subs = _saubere_namen(ctx.opt("subreddits"))
        if not subs:
            raise ValueError(
                "Keine Subreddits konfiguriert. Trag mindestens einen Namen "
                "ein (ohne 'r/'), z.B. GameDeals.")
        listing = ctx.opt("listing", "new")
        base = str(ctx.opt("base", "https://www.reddit.com")).rstrip("/")

        # Wo der letzte Lauf abgebrochen ist. Nicht im UI - der Wert ist
        # Buchhaltung, keine Einstellung.
        start = int(ctx.options.get("_offset", 0) or 0) % len(subs)
        reihe = subs[start:] + subs[:start]
        grenze = int(ctx.opt("max_pro_lauf", 0) or 0)
        if grenze > 0:
            reihe = reihe[:grenze]

        items: list[DealItem] = []
        errors: list[str] = []
        tot: list[str] = []
        gedrosselt: RateLimited | None = None
        erledigt = 0

        for sub in reihe:
            url = f"{base}/r/{sub}/{listing}/.rss"
            try:
                # mit_mustern=False: /r/<name>/new/.rss ist die richtige
                # Adresse. Ein 404 heisst hier "Subreddit gibt es nicht" -
                # da ist nichts zu suchen, nur etwas zu streichen.
                fund = await feedfinder.hole(
                    ctx.http, url, cache_key=f"{self.id}:{sub}:{listing}",
                    mit_mustern=False)
                items.extend(self.parse(fund.text, sub))
                erledigt += 1
            except RateLimited as exc:
                # Der Client sperrt den Host jetzt ohnehin fuer die genannte
                # Dauer - weitermachen hiesse, in eine geschlossene Tuer zu
                # rennen. Beim naechsten Lauf geht es hier weiter.
                gedrosselt = exc
                break
            except Exception as exc:
                erledigt += 1
                code = _status(exc)
                if code == 404:
                    tot.append(sub)
                    errors.append(f"r/{sub}: gibt es nicht (404) - entfernt")
                elif code == 403:
                    errors.append(f"r/{sub}: kein Zugang (403) - privat, "
                                  f"gesperrt oder nur mit Anmeldung")
                else:
                    errors.append(f"r/{sub}: {type(exc).__name__}: {exc}"[:260])

        self._lernen(ctx, subs, tot, start, erledigt)

        if items:
            if errors and ctx.log:
                ctx.log.warning("%s: %d von %d Subreddits fehlerhaft: %s",
                                self.id, len(errors), len(reihe), errors[0])
            return items

        if gedrosselt is not None:
            # Als RateLimited weiterreichen, nicht als RuntimeError: der
            # Scheduler legt die Quelle dann schlafen, statt sie nach drei
            # Laeufen als defekt abzuschalten. Gedrosselt ist nicht kaputt.
            raise gedrosselt
        if errors:
            raise RuntimeError(self._fehlertext(errors))
        return items

    def _lernen(self, ctx: FetchContext, subs: list[str], tot: list[str],
                start: int, erledigt: int) -> None:
        """Tote Namen streichen und merken, wo der naechste Lauf anfaengt."""
        if tot:
            rest = [s for s in subs if s not in tot]
            ctx.merke("subreddits", rest)
            bekannt = [str(x) for x in (ctx.options.get("entfernt") or [])]
            ctx.merke("entfernt", bekannt + [s for s in tot if s not in bekannt])
            if ctx.log:
                ctx.log.warning("%s: %s gibt es nicht - aus der Liste entfernt",
                                self.id, ", ".join("r/" + s for s in tot))
            subs = [s for s in subs if s not in tot]
            start = 0
        if subs:
            ctx.merke("_offset", (start + erledigt) % len(subs))

    @staticmethod
    def _fehlertext(errors: list[str]) -> str:
        """Kurz halten: drei Zeilen erklaeren die Lage, dreissig nicht."""
        text = " | ".join(errors[:3])
        if len(errors) > 3:
            text += f" | (+{len(errors) - 3} weitere)"
        return text

    def parse(self, text: str, sub: str = "") -> list[DealItem]:
        feed = parse_feed(text)
        out: list[DealItem] = []
        for entry in feed.entries:
            title = strip_html(entry.get("title"), 400)
            link = entry.get("link")
            if not title or not link:
                continue
            body_html = entry_body(entry)
            body = strip_html(body_html, 800)
            price = parse_price_text(title)     # Reddit-Titel tragen den Preis
            if price.preis is None:
                price = parse_price_text(f"{title} {body}")

            store = None
            m = _STORE_RE.match(title)
            if m:
                store = m.group(1).strip()

            out.append(DealItem(
                titel=title,
                url=link,
                quelle=self.id,
                beschreibung=body or None,
                preis=price.preis,
                originalpreis=price.originalpreis,
                rabatt_prozent=price.rabatt_prozent,
                waehrung=price.waehrung or "EUR",
                haendler=store,
                bild=first_image(entry, body_html),
                veroeffentlicht_am=entry_datetime(entry),
                tags=[f"r/{sub}"] if sub else [],
                ist_gratis=price.ist_gratis,
                kategorie="reddit",
                roh={"subreddit": sub, "author": entry.get("author")},
            ))
        return out


register(Reddit())
