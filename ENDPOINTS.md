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
| Slickdeals (US) | RSS | `feeds.slickdeals.net/slickdeals/frontpage` | nein | 20 Min. | Preise in **USD** |
| OzBargain (AU) | RSS | `ozbargain.com.au/deals/feed` | nein | 20 Min. | Preise in **AUD** |
| Eigene Feeds | RSS | frei eintragbar | nein | 15 Min. | für Geizhals-Wunschlisten u. Ä. |

### Die beiden internationalen Quellen

Warum überhaupt: SparBit rechnet ohnehin in EUR um, und die
Preisfehler-Erkennung braucht Gegenmeinungen aus mehreren Quellen. Beides
wird besser, je mehr Märkte dieselbe Ware melden — gerade bei Elektronik,
wo ein Preisfehler oft zuerst anderswo auffällt. OzBargain ist wegen der
Zeitzone oft die erste Quelle, die einen weltweiten Preisfehler meldet.

Die Währung wird dabei **nicht geraten**: steht im Titel ein
Währungszeichen, gewinnt das, sonst gilt die Vorgabe der Quelle (USD bzw.
AUD). Ohne diese Festlegung liefe ein „$ 199" als EUR durch jede
Preisregel. Beide Adressen sind im UI änderbar — viele dieser Seiten
bieten auch Feeds je Kategorie an.

### Ein Endpunkt, der nicht zu den Deals gehört

| Zweck | Endpoint | Key | Intervall |
|---|---|---|---|
| Wechselkurse | `www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml` | nein | 1× täglich |

Das ist der einzige ausgehende Abruf, den SparBit **von sich aus** macht —
alles andere sind Quellen, die du eingeschaltet hast, und Kanäle, die du
eingerichtet hast. Rund 3 KB, kein Schlüssel, kein Konto, keine Cookies.

Der Grund: ein fester Kurs im Code altert still. Niemand bekommt eine
Fehlermeldung, wenn „max. 20 €" seit einem Jahr bei 21,40 € zuschlägt —
die Regel greift einfach ein bisschen daneben. Abschalten lässt sich der
Abruf unter *Benachrichtigungen → Währung & Pause*; dann gilt, was du dort
einträgst, und das UI sagt weiterhin, wie alt es ist.

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
* **Reddit ist streng gegen Cloud-IPs.** 429 oder 403 sind möglich — im
  Betrieb bestätigt (`HTTP 429, retry after 58s`). Der User-Agent ist bewusst
  sprechend gesetzt (das verlangt Reddit), das Intervall ist mit 10 Minuten
  defensiv, und zwischen zwei Reddit-Anfragen liegen mindestens 3 Sekunden
  statt der üblichen 1. Kommt trotzdem 429: die Quelle pausiert so lange, wie
  Reddit sagt, und arbeitet die Subreddits über mehrere Läufe ab, statt bei
  denselben ersten hängenzubleiben. Mit *Subreddits pro Lauf* lässt sich das
  zusätzlich begrenzen.
* **Steam drosselt `appdetails` hart** (grob ~200 Requests/5 Min. pro IP).
  Darum sind die Detailabfragen pro Lauf gedeckelt (Vorgabe 15) und mit einer
  Pause versehen.
* **Die Gruppen-Feed-Pfade von mydealz** (`/gruppe/preisfehler-rss` usw.) sind
  die gängige Konvention der Plattform, aber genau der Teil, den ich nicht
  prüfen konnte. Wenn ein Pfad 404 gibt: im UI unter *Quellen → mydealz →
  Einstellungen* korrigieren, kein Neustart nötig.

## SparBit sucht den Feed selbst

Nachgetragen, nachdem ein geratener Pfad im Betrieb danebenlag:

```
https://www.mydealz.de/gruppe/erotik-rss:
ValueError: Kein gueltiger Feed (SAXParseException).
Anfang der Antwort: '<!DOCTYPE html><html class="no-js …
```

Die Antwort war eine **echte Seite** — kein 404, keine Cloudflare-Wand. Der
Server war erreichbar und wusste, wo sein Feed liegt; nur SparBit wusste es
nicht. Praktisch jede Seite schreibt das in ihren Kopf:

```html
<link rel="alternate" type="application/rss+xml" href="/rss/gruppe/erotik">
```

Darum gilt jetzt für **alle** Feed-Quellen: kommt HTML statt eines Feeds,
liest SparBit die ausgezeichneten Feed-Adressen aus der Seite, probiert sie
der Reihe nach (höchstens drei) und **schreibt die funktionierende in die
Quellen-Einstellungen zurück**. Beim nächsten Lauf steht dort die richtige
Adresse. Ein falsch geratener Pfad heilt sich damit von selbst — und du
siehst im UI, was daraus geworden ist.

Deshalb dürfen in den Feed-Feldern auch **Seiten-Adressen** stehen, nicht nur
Feed-Adressen. Die Gruppen-Pfade von mydealz sind aus diesem Grund auf die
Seiten umgestellt (`/gruppe/gratis` statt `/gruppe/gratis-rss`).

### Und wenn die Seite ihren Feed nicht auszeichnet

Genau das kam als nächste Meldung aus dem Betrieb — mydealz und Preisjäger
nennen auf ihren Gruppen- und Suchseiten keinen Feed:

```
https://www.mydealz.de/gruppe/erotik-rss: KeinFeed: HTML-Seite, kein Feed
https://www.preisjaeger.at/search?q=satisfyer&rss=1: KeinFeed: HTML-Seite
```

Unbekannt ist die Adresse deshalb nicht. Jede Software legt ihre Feeds an
derselben Handvoll Stellen ab, und die probiert SparBit nun durch:

| Software | Eingetragen | Probierte Muster |
|---|---|---|
| Pepper-Gruppe/-Tag | `/gruppe/erotik` | `/rss/gruppe/erotik`, `/gruppe/erotik-rss`, `/gruppe/erotik?rss=1`, `/rss/erotik` |
| Pepper-Suche | `/search?q=X&rss=1` | `/rss/search?q=X`, `/search/rss?q=X`, `/search.rss?q=X` |
| Shopify-Kollektion | `/collections/sale` | `/collections/sale.atom` |
| Shopify-Startseite | `https://shop.de/` | `/collections/all.atom`, `/feed`, `/rss` |
| WordPress/WooCommerce | `https://shop.de/angebote/` | `…/feed`, `…/rss`, `…/feed.xml`, `…/rss.xml` |

Regeln dabei:

* **Übernommen wird nur, was wirklich einen Feed liefert.** Ein Muster, das
  HTML oder 404 zurückgibt, wird verworfen — nichts wird „optimistisch"
  eingetragen.
* **Höchstens vier Muster je Adresse**, und eine Adresse, bei der alle
  durchfielen, wird eine Stunde lang nicht erneut durchprobiert. *Jetzt
  testen* hebt die Sperrfrist sofort auf.
* **Auch ein 404 löst die Suche aus** — bei einem geratenen Pfad heißt er
  „hier nicht", nicht „nirgends". Nur bei Reddit ist das abgeschaltet: dort
  stimmt die Adresse, und 404 heißt „diesen Subreddit gibt es nicht".
* **Bei Suchbegriffen wandert die Vorlage zurück**, nicht nur die eine
  Adresse: aus einem geheilten `…/rss/search?q=satisfyer` wird
  `search_path = /rss/search?q={term}` für alle Begriffe.

Die Vorbelegungen der Pepper-Quellen stehen deshalb jetzt auf der
Feed-Variante (`/rss/gruppe/…`, `/rss/search?q={term}`) — liegt sie anders,
findet die Muster-Suche die richtige und trägt sie ein.

### „Feed suchen"

Wenn du es vorher wissen willst: *Quellen → Feed suchen* (oder
`sparbit feed-suche <adresse>`) holt eine beliebige Seite und listet, welche
Feeds sie angibt — mit Vermerk, ob die Adresse **ausgezeichnet** ist oder aus
einem Link **geraten**. Das Ergebnis lässt sich direkt in ein Feed-Feld
kopieren.

```
$ sparbit feed-suche https://pypi.org/
  2 Feed-Adresse(n) gefunden auf 'PyPI · Der Python Package Index'.

  Feed-Adresse                       Titel                        Herkunft
  https://pypi.org/rss/updates.xml   RSS: Letzte 40 Aktualisier…  ausgezeichnet
  https://pypi.org/rss/packages.xml  RSS: 40 neueste Pakete       ausgezeichnet
```

Und die Fehlermeldungen sagen jetzt, was zu tun ist. Statt
`SAXParseException` steht dort entweder *„Der Server hat eine HTML-Seite
geliefert (Seitentitel: …). Auf der Seite ist auch kein Feed ausgezeichnet"*
oder *„Bot-Abwehr statt Inhalt — ein anderer Pfad hilft dagegen nicht."*
Das sind zwei verschiedene Probleme, und man sucht sonst am falschen Ende.

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

---

# 18+-Bereich

Standardmäßig aus. Freischalten unter *Logs & System → 18+-Bereich* (mit
Altersbestätigung) oder per `sparbit 18plus --an --ich-bin-volljaehrig`.
Solange er aus ist, existieren die folgenden Quellen nicht — sie sind weder
sichtbar noch über die API oder die CLI einschaltbar.

**Auch hier gilt der Verifizierungsstand des ganzen Projekts: nichts davon
konnte live geprüft werden.** Die Build-Umgebung erreicht keinen einzigen
Deal-Host; 44 von 44 Endpoints scheitern am Proxy. Alles unten sind darum
*Kandidaten*, keine Zusagen. `Jetzt testen` hat das letzte Wort.

## Was gebaut ist

| Quelle | Typ | Vorbelegung | Anmerkung |
|---|---|---|---|
| `mydealz_erotik` | RSS | `/rss/gruppe/erotik` | liegt der Feed anders, sucht SparBit ihn |
| `preisjaeger_erotik` | RSS | `/rss/gruppe/erotik` | Österreich, gleiche Plattform |
| `dealabs_erotik` | RSS | `/rss/groupe/erotique` | Frankreich, Slug geraten |
| `hotukdeals_erwachsen` | RSS | `/rss/tag/adult` | UK, GBP → EUR, Slug geraten |
| `reddit_erwachsen` | RSS | `NSFWdeals`, `AdultDeals` | **Namen geraten** — was 404 gibt, streicht SparBit selbst |
| `erotik_feed` | RSS/Atom | leer | Shop-Seite *oder* Feed, siehe unten |

`SexToyDeals` stand hier bis zum Betriebsbericht mit in der Vorbelegung und
ist mit `404 Not Found` widerlegt — deshalb draußen. Die beiden verbliebenen
Namen kamen in deinen Läufen nie bis zu einer Antwort, weil vorher das
Rate-Limit griff; sie bleiben damit ungeprüft.

Die Gruppen-Pfade sind weiterhin geraten — aber sie sind jetzt die der
**Seite**, nicht des Feeds. Gibt es die Gruppe unter dem Namen, findet
SparBit den Feed darauf selbst. Gibt es sie nicht, sagt die Fehlermeldung
das im Klartext statt eines Parser-Fehlers. Zusätzlich hat jede dieser
Quellen **Suchbegriff-Feeds** — die greifen auch dann, wenn es die Gruppe
gar nicht gibt.

Kriterium für die Aufnahme ist dasselbe wie überall im Projekt: **es muss
einen Feed oder eine dokumentierte API geben.** Erotik-Shops sind fast
durchweg reine HTML-Seiten mit aktivem Bot-Schutz — ein Scraper dafür wäre
genau das, was du nicht wolltest.

## Auch ohne eigene Quelle ist der Bereich nicht leer

SparBit stuft **jeden** Fund ein, egal woher er kommt. Ein Erotik-Deal aus
`mydealz /rss/alle` landet automatisch im 18+-Bereich und *nicht* im
normalen Feed. Die Einstufung ist zweistufig (`backend/app/erwachsen.py`):
ein eindeutiges Wort genügt („Vibrator", „Satisfyer", „FSK 18"), ein
mehrdeutiges nicht („adult", „sexy", „Dessous") — davon braucht es zwei.
Sonst wandert die halbe Modeabteilung dorthin und ist nicht wiederzufinden.

## Feed-Adressen, die sich lohnen zu probieren

Das ist der nützlichste Teil: viele Shops liefern einen Feed, ohne damit zu
werben. Welche Adresse, hängt an der Shop-Software — die erkennst du im
Seitenquelltext oder an typischen Pfaden.

| Shop-System | Feed-Adresse | Woran man es erkennt |
|---|---|---|
| **Shopify** | `…/collections/all.atom`, `…/collections/sale.atom`, `…/collections/<name>.atom` | `cdn.shopify.com` im Quelltext |
| **WooCommerce / WordPress** | `…/feed`, `…/shop/feed`, `…/product-category/<name>/feed` | `wp-content/` im Quelltext |
| **Magento 2** | `…/rss/catalog/special/store_id/1/cid/<id>` (Sonderangebote), `…/rss/catalog/category/cid/<id>` | `static/version…/Magento_` |
| **PrestaShop** | `…/modules/feeder/rss.php` | `/themes/` + `id_product=` |
| **Shopware 6** | kein Standard-RSS; manche Shops bieten einen Google-Shopping-Export als XML an | `/widgets/` |

Vorgehen, kurz: **Adresse der Angebotsseite** unter *Quellen → Eigene
18+-Quellen* eintragen und *Jetzt testen* drücken. Den Feed sucht SparBit
selbst und trägt ihn ein. Willst du es vorher sehen: *Feed suchen* oben auf
der Quellen-Seite, oder `sparbit feed-suche <adresse>`.

Die Tabelle oben brauchst du nur, wenn die Seite ihren Feed **nicht**
auszeichnet — dann musst du die Adresse von Hand raten, und dort steht,
welche Schreibweise bei welcher Shop-Software üblich ist.

Die Shopify-Variante ist am ergiebigsten: `.atom` ist dort fest eingebaut
und lässt sich nicht abschalten, und auffällig viele Erotik-Shops laufen
auf Shopify.

## Kandidaten, die du selbst prüfen musst

Diese Anbieter sind im DACH-Raum verbreitet und verkaufen legale
Erwachsenenartikel. **Ich konnte keinen einzigen aufrufen** — die Liste
sagt nur, wo sich das Ausprobieren der Adressen oben lohnt, nicht, dass es
funktioniert.

* **Shops:** EIS.de, Amorelie, Orion, Beate Uhse, Lovehoney, Satisfyer
  (Herstellershop), Pabo, Christine le Duc, Dildoking, Erotikmarkt
* **Deal-Communities:** mydealz-Gruppe *Erotik* (gebaut), Preisjäger.at
  (gleiche Plattform — als absolute URL in `mydealz_erotik` eintragbar),
  Dealabs *Érotique*
* **Suchbegriff-Feeds statt Gruppen:** oft ergiebiger als die Gruppe. Unter
  *mydealz — Erotik → Suchbegriff-Feeds* z. B. `satisfyer`, `gleitgel`,
  `womanizer`, `dessous`, `kondome` eintragen.

## Was bewusst NICHT gebaut ist

| Quelle | Warum nicht | Was stattdessen |
|---|---|---|
| **itch.io (NSFW-Spiele)** | Browse-Seiten liefern HTML; `format=json` gibt HTML in JSON verpackt — weiterhin Scraping. | Ein Subreddit in `reddit_erwachsen` |
| **Steam (Mature)** | Adult-Titel liegen hinter der Altersabfrage; `featuredcategories` liefert sie nicht. Es gibt keinen dokumentierten Endpoint dafür. | — |
| **DLsite / Fanza / Nutaku** | Kein dokumentierter öffentlicher Feed. Japanische Seiten mit Regionssperre und Bot-Schutz. | Suchbegriff-Feeds auf mydealz |
| **Pornhub / OnlyFans u. Ä. (Abo-Rabatte)** | Keine öffentliche API für Preise; Angebote laufen über personalisierte Aktionen. | — |
| **Reddit-Subreddits allgemein** | Existieren vermutlich, ich konnte aber keinen einzigen Namen prüfen. Die drei vorbelegten sind geraten. | Prüfen, korrigieren, ergänzen |

## Zustellung

Zwei Schalter, beide standardmäßig aus:

1. **Je Regel:** ohne das Häkchen *18+-Funde einbeziehen* sieht eine Regel
   diese Deals gar nicht — auch dann nicht, wenn sonst alles passt.
2. **Global:** *Logs & System → 18+-Bereich → Auch über Telegram, Discord &
   Co. melden*. Aus heißt: nur auf der Seite.

Der Preisfehler-Wächter ignoriert 18+-Funde vollständig. Er meldet an Regeln
und Ruhezeiten vorbei in Sekunden — genau das soll dieser Bereich nicht tun.
