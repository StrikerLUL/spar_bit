# Endpoint-Recherche und Machbarkeitstabelle

## Zusammenfassung vorweg

**Es konnte in dieser Build-Session keine einzige Quelle live verifiziert
werden.** Die Umgebung, in der SparBit gebaut wurde, hat eine Egress-Policy,
die den Zugriff auf alle Deal-Hosts blockiert. Geprüft wurden 44 Endpoints —
alle 44 scheiterten am Proxy, nicht an den Zielservern:

```
gateway answered 403 to CONNECT (policy denial or upstream failure)
```

Kontrollmessung zur Abgrenzung: `api.github.com` → 200, `pypi.org` → 200,
`example.com` → blockiert. Es ist also eine schmale Allowlist für
Entwicklungsinfrastruktur, kein Cloudflare-Problem und kein 404.

Da du ausdrücklich keine erfundenen Endpunkte und keine
„sollte-funktionieren"-Platzhalter wolltest, steht hier **keine erfundene
Ja/Nein-Spalte**. Stattdessen:

1. Jede Quelle startet mit dem Status `ungeprüft`.
2. Alle URLs sind im Web-UI editierbar — du brauchst keinen Code anzufassen,
   wenn eine Seite ihre Pfade geändert hat.
3. `tools/verify_endpoints.py` holt die Verifikation auf deinem VPS nach und
   erzeugt genau die Tabelle, die hier fehlt.

## Die Tabelle selbst erzeugen

Auf dem VPS, nach `docker compose up -d`:

```bash
docker compose exec backend python -m tools.verify_endpoints --markdown /data/endpoints.md
docker cp sparbit-backend:/data/endpoints.md ./ENDPOINTS-live.md
```

Oder ohne Docker, direkt im `backend/`-Verzeichnis:

```bash
export SPARBIT_KEY_ITAD=dein_key        # optional
export SPARBIT_KEY_GGDEALS=dein_key     # optional
python -m tools.verify_endpoints --markdown ../ENDPOINTS-live.md
```

Das Skript ruft jeden Endpoint wirklich auf und lässt **den echten Parser der
jeweiligen Quelle** darüberlaufen — es prüft also nicht nur „antwortet der
Server", sondern „kommen sinnvolle Deals heraus". Ausgabe: Quelle, Endpoint,
funktioniert ja/nein, Key nötig, Anzahl Einträge, Latenz, Fehlerdetail.

Im Web-UI macht der Knopf **„Jetzt testen"** pro Quelle dasselbe und setzt den
Status auf `geprüft` oder `defekt`.

## Was implementiert ist

Kriterium für die Aufnahme war: **es gibt einen dokumentierten Feed oder eine
JSON-API.** Quellen, die nur per HTML-Scraping erreichbar wären, sind bewusst
*nicht* gebaut — du wolltest keine fragilen Scraper, und ein Scraper, den ich
nicht einmal gegen die echte Seite laufen lassen konnte, wäre besonders
fragil.

| Quelle | Typ | Endpoint(s) mit Vorbelegung | Key | Intervall | Anmerkung |
|---|---|---|---|---|---|
| mydealz.de | RSS | `/rss/alle`, `/rss/hot`, `/gruppe/preisfehler-rss`, `/gruppe/gratis-rss`, `/gruppe/gaming-rss` + eigene Suchbegriffe | nein | 10 Min. | Pepper-Plattform, hinter Cloudflare |
| Preisjaeger.at | RSS | `/rss/alle`, `/rss/hot` | nein | 10 Min. | dito |
| HotUKDeals | RSS | `/rss/all`, `/rss/hot` | nein | 10 Min. | dito, GBP |
| Dealabs (FR) | RSS | `/rss/alle`, `/rss/hot` | nein | 10 Min. | dito |
| Sparhamster.at | RSS | `https://www.sparhamster.at/feed/` | nein | 15 Min. | WordPress |
| Schnaeppchenfuchs | RSS | `https://www.schnaeppchenfuchs.com/feed` | nein | 15 Min. | WordPress |
| Reddit | RSS | `/r/{sub}/new/.rss` für 6 Subreddits | nein | 10 Min. | Subreddits im UI pflegbar |
| Epic Games Store | JSON | `store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions` | nein | 1 Std. | `locale=de-DE&country=DE` |
| GOG.com | JSON | `catalog.gog.com/v1/catalog` (0-€-Filter) + `gog.com/giveaway/api/status` | nein | 1 Std. | Giveaway-Endpoint darf fehlen |
| Steam | JSON | `store.steampowered.com/api/featuredcategories` + `/api/appdetails` | nein | 1 Std. | appdetails gedeckelt (Rate-Limit) |
| CheapShark | JSON | `cheapshark.com/api/1.0/deals` + `/stores` | nein | 30 Min. | Preise in **USD** |
| IsThereAnyDeal | JSON | `api.isthereanydeal.com/deals/v2` | **ja** | 30 Min. | Doku: docs.isthereanydeal.com |
| GG.deals | JSON | `api.gg.deals/v1/deals/list/` | **ja** | 1 Std. | Zugang wird einzeln freigeschaltet |
| Eigene Feeds | RSS | frei eintragbar | nein | 15 Min. | für Geizhals-Wunschlisten u. Ä. |

### Zu den beiden Key-Quellen

* **IsThereAnyDeal** — Key unter <https://isthereanydeal.com/apps/my/> (App
  registrieren). Die v2-API ist öffentlich dokumentiert; der Pfad ist im UI
  änderbar, falls sich die Version verschiebt.
* **GG.deals** — Zugang unter <https://gg.deals/de/api/> beantragen, für
  private Nutzung kostenlos. Hier ist die Unsicherheit am größten: sowohl der
  genaue Pfad als auch die Antwortstruktur hängen von deiner Freischaltung ab.
  Der Parser ist tolerant gegenüber mehreren gängigen Feldnamen und meldet
  eine unbrauchbare Antwort als klaren Fehler, statt still nichts zu liefern.
  **Bitte hier unbedingt zuerst „Jetzt testen" drücken.**

## Was bewusst NICHT implementiert ist

Diese Quellen aus deiner Liste hätten HTML-Scraping erfordert. Du hast
gesagt: lieber melden als fragil bauen — also melde ich sie.

| Quelle | Warum nicht | Was du stattdessen tun kannst |
|---|---|---|
| **itch.io** | Browse-Seiten liefern HTML; das kursierende `format=json` gibt HTML in JSON verpackt zurück — also weiterhin Scraping. | r/FreeGameFindings meldet itch.io-Freebies zuverlässig. |
| **Indiegala Freebies** | Reine HTML-Seite, kein stabiler JSON-Endpoint bekannt. | r/FreeGameFindings |
| **Fanatical Free** | Store-API ist intern und undokumentiert, Struktur ändert sich mit dem Frontend. | r/FreeGameFindings, zusätzlich CheapShark |
| **Humble Store Free** | Cloudflare-geschützt, interne Such-API. | r/FreeGameFindings, CheapShark |
| **Unreal Engine Gratis-Assets** | Der Marketplace wurde 2024 durch **FAB** ersetzt; die alte `/marketplace/api/assets` ist Geschichte, FAB hat keine dokumentierte öffentliche API. | Falls FAB einen Feed anbietet: als „Eigene Feeds"-URL eintragen. |
| **Kleinanzeigen „Zu verschenken"** | Kein Feed, aktiver Bot-Schutz. Ein Scraper wäre hier nicht nur fragil, sondern würde auch schnell gesperrt. | — (ehrlich: hier habe ich nichts Gutes) |
| **Geizhals-Wunschliste** | Der Wunschlisten-Feed ist an *deinen* Account gebunden, eine generische URL kann ich nicht vorgeben. | **„Eigene Feeds"** — trag deine persönliche Wunschlisten-RSS-URL ein. Genau dafür ist die Quelle da. |

Der praktische Trost: **r/FreeGameFindings** aggregiert itch.io, Indiegala,
Fanatical, Humble und Epic ohnehin, meist binnen Minuten. Die Reddit-Quelle
deckt diese Lücke weitgehend ab — deshalb ist sie vorbelegt.

## Erwartbare Stolpersteine auf deinem VPS

Das sind Vermutungen aus der Bauweise der jeweiligen Dienste, keine
Messungen — der Test auf deinem Server hat das letzte Wort.

* **Pepper-Seiten (mydealz & Co.) stehen hinter Cloudflare.** Von einer
  Rechenzentrums-IP kann es 403 geben, wo es vom Heimanschluss klappt. Wenn
  eine Quelle konstant 403 liefert: der Circuit Breaker pausiert sie
  automatisch, und im UI steht der Grund.
* **Reddit ist streng gegen Cloud-IPs.** 429 oder 403 sind möglich. Der
  User-Agent ist bewusst sprechend gesetzt (das verlangt Reddit), und das
  Intervall ist mit 10 Minuten defensiv.
* **Steam drosselt `appdetails` hart** (grob ~200 Requests/5 Min. pro IP).
  Darum sind die Detailabfragen pro Lauf gedeckelt (Vorgabe 15) und mit einer
  Pause versehen.
* **Die Gruppen-Feed-Pfade von mydealz** (`/gruppe/preisfehler-rss` usw.) sind
  die gängige Konvention der Plattform, aber genau der Teil, den ich nicht
  prüfen konnte. Wenn ein Pfad 404 gibt: im UI unter *Quellen → mydealz →
  Einstellungen* korrigieren, kein Neustart nötig.

## Wenn eine Quelle nicht funktioniert

1. **„Jetzt testen"** drücken — die Fehlermeldung ist konkret (404, HTML statt
   JSON, Cloudflare, Timeout).
2. Bei falschem Pfad: unter *Einstellungen* korrigieren, erneut testen.
3. Bei dauerhaftem Block: Quelle ausschalten. Alle anderen laufen weiter —
   Quellen sind vollständig voneinander isoliert.
4. Nach 5 Fehlern in Folge greift der Circuit Breaker und pausiert die Quelle
   30 Minuten. Im UI lässt sich das mit dem Zurücksetzen-Knopf sofort aufheben.

## Echte Fixtures aufzeichnen

Die mitgelieferten Test-Fixtures sind formattreu, aber synthetisch — sie
testen die Parser-Logik, nicht die Realität der Endpoints. Sobald du Netz
hast, kannst du echte aufzeichnen und die Tests dagegen laufen lassen:

```bash
cd backend
python -m tools.verify_endpoints --save-fixtures tests/fixtures/live
pytest tests/ --live-fixtures tests/fixtures/live
```

Weicht das echte Format von meinen Annahmen ab, schlagen die Tests fehl —
genau so ist es gedacht. Dann weißt du präzise, welcher Parser nachgezogen
werden muss.
