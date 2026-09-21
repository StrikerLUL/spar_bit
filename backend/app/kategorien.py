"""Wovon handelt dieser Deal - Elektronik, SSD, Abo, Dessous?

Bis hierher kannte SparBit nur die Kategorie der *Quelle*: "community",
"reddit", "gaming", "erwachsen". Das beantwortet die Frage, wo etwas
herkommt, nicht die Frage, worum es geht - und die stellt man beim Suchen:
"zeig mir Speicher", "zeig mir Abos".

Die Einstufung ist bewusst regelbasiert und nicht gelernt. Ein Modell
muesste trainiert, gepflegt und mitgeliefert werden, und wenn es
danebenliegt, kann man nichts dagegen tun. Eine Wortliste dagegen ist zu
lesen, zu pruefen und in einer Zeile zu korrigieren - und sie erklaert
jeden Treffer von selbst.

Drei Entscheidungen, die den Unterschied machen:

**Zusammensetzungen.** Deutsch klebt Woerter aneinander: "SSD-Festplatte",
"Gaming-Headset", "Monatsabo". Ein Begriff passt darum ab Wortanfang und
darf hinten weiterlaufen ("Kopfhoerer" trifft "Kopfhoerern"). Kurze
Begriffe (bis vier Zeichen) bekommen zusaetzlich eine Bremse nach hinten,
sonst findet "abo" das englische "above" und "tv" das Wort "tvoed".

**Mehrere Kategorien.** Ein "Gaming-Notebook mit 1 TB SSD" ist Computer,
Gaming und Speicher zugleich. Genau deshalb sind es Mehrfach-Marken und
keine Schublade - wer nach Speicher filtert, will dieses Notebook sehen.
Gedeckelt auf drei, damit eine Karte nicht zur Wortwolke wird.

**18+ bleibt getrennt.** Die Kategorien mit `erwachsen=True` werden nur an
18+-Funde vergeben und nur im 18+-Bereich zur Auswahl gestellt. Umgekehrt
gilt dasselbe: ein normaler Deal bekommt sie nie, auch wenn ein Wort passt.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Wie viele Marken ein Deal hoechstens bekommt.
MAX_PRO_DEAL = 3

# Stand der Wortliste. **Diese Zahl hochzaehlen, sobald sich unten etwas
# aendert** - dann stuft SparBit den Bestand beim naechsten Start neu ein.
#
# Ohne das waere jede Verbesserung an der Liste wirkungslos fuer alles, was
# schon in der Datenbank liegt: ein neu aufgenommener Begriff wuerde nur
# noch kuenftige Funde treffen, und der Filter bliebe fuer den halben
# Bestand leer. Genau das ist beim ersten Umbau passiert.
VERSION = 2

# Wo der Neu-Durchlauf steht: {"version": int, "cursor": letzte Deal-ID}.
SCHLUESSEL_STAND = "kategorien_stand"

# Bis zu dieser Laenge braucht ein Begriff eine Bremse nach hinten.
KURZ_BIS = 4


@dataclass(frozen=True)
class Kategorie:
    key: str
    label: str
    begriffe: tuple[str, ...]
    # Nur fuer 18+-Funde vergeben und nur dort zur Auswahl gestellt.
    erwachsen: bool = False
    # Kurzbeschreibung fuer den Hilfetext im UI.
    hinweis: str = ""


KATEGORIEN: tuple[Kategorie, ...] = (
    Kategorie("speicher", "Speicher & SSD", (
        "ssd", "nvme", "m.2", "festplatte", "hdd", "sata", "speicherkarte",
        "microsd", "sd-karte", "sdxc", "usb-stick", "usb stick", "nas",
        "arbeitsspeicher", "ram-kit", "ddr4", "ddr5", "externe festplatte",
        "ssd-festplatte", "flash", "cf-express",
        "crucial", "sandisk", "kingston", "seagate", "wd blue", "wd black",
        "wd red", "samsung 990", "samsung 980", "synology",
    ), hinweis="SSDs, Festplatten, Speicherkarten, RAM"),
    Kategorie("computer", "Computer & Zubehör", (
        "notebook", "laptop", "ultrabook", "macbook", "desktop-pc", "gaming-pc",
        "monitor", "bildschirm", "tastatur", "keyboard", "computermaus",
        "grafikkarte", "geforce", "radeon", "prozessor", "ryzen", "intel core",
        "mainboard", "netzteil", "gehäuse-lüfter", "drucker", "scanner",
        "router", "fritz!box", "fritzbox", "repeater", "switch-hub", "docking",
        "webcam", "usb-hub", "thunderbolt",
        "thinkpad", "ideapad", "zenbook", "vivobook", "surface laptop",
        "surface pro", "imac", "mac mini", "rtx", "intel arc",
    ), hinweis="Notebooks, PCs, Monitore, Peripherie"),
    Kategorie("handy", "Handy & Tablet", (
        "smartphone", "iphone", "galaxy s", "pixel ", "handy", "tablet",
        "ipad", "smartwatch", "fitness-tracker", "powerbank", "ladegerät",
        "ladekabel", "handyhülle", "displayschutz", "xiaomi", "oneplus",
        "fairphone", "nothing phone", "redmi", "poco ", "garmin",
        "fitbit", "apple watch",
    ), hinweis="Smartphones, Tablets, Wearables, Zubehör"),
    Kategorie("audio", "Audio & Kopfhörer", (
        "kopfhörer", "headset", "earbuds", "in-ear", "over-ear", "airpods",
        "lautsprecher", "soundbar", "bluetooth-box", "hifi", "verstärker",
        "plattenspieler", "subwoofer", "mikrofon", "sonos", "bose", "jbl",
        "sennheiser", "beyerdynamic", "marshall", "teufel", "soundcore",
        "nothing ear", "bluetooth-kopfhörer",
    ), hinweis="Kopfhörer, Boxen, HiFi"),
    Kategorie("tv_foto", "TV, Foto & Video", (
        "fernseher", "oled-tv", "oled tv", "oled fernseher", "oled evo",
        "lg oled", "qled", "led-tv", "smart-tv", "beamer",
        "projektor", "kamera", "spiegelreflex", "systemkamera", "objektiv",
        "gopro", "action-cam", "drohne", "stativ", "blitzgerät",
        "bravia", "canon eos", "nikon z", "sony alpha", "fujifilm", "dji ",
    ), hinweis="Fernseher, Kameras, Beamer"),
    Kategorie("gaming", "Gaming", (
        "playstation", "ps5", "ps4", "xbox", "nintendo", "switch-spiel",
        "konsole", "controller", "gamepad", "steam", "epic games", "gog",
        "gaming", "videospiel", "spiele-key", "game-key", "season pass",
        "battle pass", "dlc", "vr-brille", "quest 3",
        "steam deck", "rog ally", "legion go", "switch oled", "switch lite",
    ), hinweis="Konsolen, Spiele, Zubehör"),
    Kategorie("software", "Software & Lizenzen", (
        "software", "lizenz", "windows 1", "office 2", "microsoft 365",
        "antivirus", "virenschutz", "betriebssystem", "adobe", "cad-",
        "lizenzschlüssel", "produktkey", "product key",
    ), hinweis="Programme, Lizenzen, Keys"),
    Kategorie("abo", "Abo & Mitgliedschaft", (
        "abo", "abonnement", "monatsabo", "jahresabo", "mitgliedschaft",
        "membership", "subscription", "flatrate", "flat rate", "premium-zugang",
        "premium zugang", "monatlich kündbar", "pro monat", "pro jahr",
        "im monat", "mtl.", "monatlich", "streaming-dienst", "netflix",
        "spotify", "disney+", "dazn", "prime video", "youtube premium",
        "cloud-speicher", "vpn-dienst", "nordvpn", "surfshark", "zugang für",
        "laufzeit", "vertragslaufzeit", "testmonat", "probeabo",
    ), hinweis="Laufende Dienste: Streaming, VPN, Mitgliedschaften"),
    Kategorie("mobilfunk", "Mobilfunk & Internet", (
        "allnet", "allnet-flat", "datenvolumen", "prepaid", "sim-karte",
        "mobilfunk", "handyvertrag", "telekom", "vodafone", "o2 ", "congstar",
        "winsim", "dsl", "glasfaser", "kabel-internet", "lte-tarif",
        "5g-tarif", "gb lte", "gb 5g",
    ), hinweis="Tarife, DSL, Glasfaser"),
    Kategorie("haushalt", "Haushalt", (
        "staubsauger", "saugroboter", "waschmaschine", "trockner",
        "geschirrspüler", "kühlschrank", "gefrierschrank", "mikrowelle",
        "luftreiniger", "luftentfeuchter", "ventilator", "heizlüfter",
        "bügeleisen", "nähmaschine", "wäschetrockner",
        "roborock", "ecovacs", "dreame", "dyson", "vorwerk", "akkusauger",
        "wischroboter", "fenstersauger",
    ), hinweis="Grossgeräte, Reinigung, Klima"),
    Kategorie("kueche", "Küche", (
        "kaffeemaschine", "kaffeevollautomat", "espressomaschine", "siebträger",
        "airfryer", "heißluftfritteuse", "pfanne", "kochtopf", "topfset",
        "messerset", "küchenmaschine", "standmixer", "thermomix", "wasserkocher",
        "toaster", "backofen", "geschirrset", "kapseln",
        "delonghi", "de'longhi", "jura ", "nespresso", "dolce gusto",
        "kitchenaid", "ninja foodi", "tefal",
    ), hinweis="Kochen, Kaffee, Geschirr"),
    Kategorie("moebel", "Möbel & Wohnen", (
        "sofa", "couch", "matratze", "bettgestell", "schreibtisch",
        "bürostuhl", "gamingstuhl", "regal", "kommode", "kleiderschrank",
        "teppich", "lampe", "leuchte", "vorhang", "bettwäsche",
        "philips hue", "hue bridge", "hue white", "nanoleaf", "govee",
        "tradfri", "stehleuchte", "deckenleuchte",
    ), hinweis="Möbel, Licht, Textilien"),
    Kategorie("werkzeug", "Werkzeug & Baumarkt", (
        "akkuschrauber", "bohrmaschine", "schlagbohrer", "stichsäge",
        "kreissäge", "winkelschleifer", "werkzeugkoffer", "werkzeugset",
        "schraubendreher", "multitool", "leiter", "kompressor", "bosch professional",
    ), hinweis="Werkzeug, Maschinen, Baumarkt"),
    Kategorie("garten", "Garten & Grill", (
        "rasenmäher", "vertikutierer", "heckenschere", "hochdruckreiniger",
        "gartenmöbel", "grill", "gasgrill", "kugelgrill", "pizzaofen",
        "hochbeet", "pflanzkübel", "sonnenschirm", "pool",
        "kärcher", "gardena", "laubbläser", "rasentrimmer",
    ), hinweis="Garten, Grill, Aussenbereich"),
    Kategorie("drogerie", "Drogerie & Pflege", (
        "shampoo", "duschgel", "zahnpasta", "zahnbürste", "rasierer",
        "rasierklingen", "windeln", "waschmittel", "spülmittel", "parfum",
        "eau de toilette", "gesichtscreme", "bodylotion", "sonnencreme",
        "nahrungsergänzung", "vitamin", "body lotion",
        "oral-b", "gillette", "nivea", "l'oréal", "braun series", "philips series",
        "elektrische zahnbürste",
    ), hinweis="Pflege, Hygiene, Reinigung"),
    Kategorie("lebensmittel", "Lebensmittel & Getränke", (
        "kaffeebohnen", "schokolade", "süßigkeiten", "nudeln", "lebensmittel",
        "getränke", "mineralwasser", "bier", "wein", "whisky", "gin ",
        "energydrink", "proteinpulver", "müsli", "tiefkühl",
        "lindt", "haribo", "ritter sport", "milka", "kelloggs",
    ), hinweis="Essen und Trinken"),
    Kategorie("mode", "Mode & Schuhe", (
        "sneaker", "laufschuh", "turnschuh", "stiefel", "jacke", "mantel",
        "hoodie", "pullover", "t-shirt", "jeans", "hose", "kleid", "rucksack",
        "handtasche", "gürtel", "sonnenbrille", "armbanduhr",
    ), hinweis="Kleidung, Schuhe, Accessoires"),
    Kategorie("kinder", "Kinder & Spielzeug", (
        "lego", "playmobil", "spielzeug", "puppe", "kuscheltier", "puzzle",
        "brettspiel", "gesellschaftsspiel", "kinderwagen", "kindersitz",
        "babyphone", "bobby car", "schulranzen",
    ), hinweis="Spielzeug, Baby, Schule"),
    Kategorie("sport", "Sport & Outdoor", (
        "hantel", "kurzhantel", "laufband", "heimtrainer", "ergometer",
        "fitness", "yogamatte", "fahrrad", "e-bike", "pedelec", "fahrradhelm",
        "zelt", "schlafsack", "wanderschuh", "skier", "snowboard",
        "wahoo", "hometrainer", "rudergerät", "klimmzugstange",
    ), hinweis="Fitness, Rad, Outdoor"),
    Kategorie("reise", "Reise & Hotel", (
        "hotel", "hotelgutschein", "übernachtung", "ferienwohnung", "flug",
        "flüge", "pauschalreise", "kurzurlaub", "mietwagen", "bahnticket",
        "deutschlandticket", "koffer", "trolley",
    ), hinweis="Hotels, Flüge, Gepäck"),
    Kategorie("auto", "Auto & Zweirad", (
        "reifen", "winterreifen", "sommerreifen", "motoröl", "autobatterie",
        "dashcam", "dachbox", "anhängerkupplung", "scheibenwischer",
        "kindersitz auto", "motorrad", "roller", "e-scooter",
        "michelin", "goodyear", "bridgestone", "hankook", "aerotwin",
    ), hinweis="Auto, Motorrad, Zubehör"),
    Kategorie("medien", "Bücher, Filme & Musik", (
        "buch", "bücher", "ebook", "e-book", "hörbuch", "hörspiel", "roman",
        "blu-ray", "4k uhd", "dvd-box", "comic", "manga", "zeitschrift",
        "abonnement zeitung", "vinyl", "schallplatte",
    ), hinweis="Bücher, Filme, Musik"),
    Kategorie("finanzen", "Finanzen & Versicherung", (
        "girokonto", "kreditkarte", "depot", "tagesgeld", "festgeld",
        "versicherung", "haftpflicht", "kredit", "bausparen", "broker",
        "neukundenbonus", "prämie für",
    ), hinweis="Konten, Depots, Versicherungen"),
    Kategorie("gutschein", "Gutschein & Rabattcode", (
        "gutschein", "gutscheincode", "rabattcode", "coupon", "voucher",
        "aktionscode", "promo-code", "gutscheinkarte", "geschenkkarte",
    ), hinweis="Codes, Gutscheinkarten"),

    # --- Nur im 18+-Bereich ------------------------------------------------
    Kategorie("toys18", "Toys", (
        "vibrator", "dildo", "buttplug", "analplug", "penisring", "masturbator",
        "sextoy", "sexspielzeug", "satisfyer", "womanizer", "lovense",
        "auflege", "klitoris", "we-vibe", "fleshlight", "liebeskugeln",
    ), erwachsen=True, hinweis="Spielzeug"),
    Kategorie("waesche18", "Dessous & Wäsche", (
        "dessous", "reizwäsche", "straps", "korsett", "negligé",
        "negligee", "strapse", "ouvert", "bodystocking", "latex-",
    ), erwachsen=True, hinweis="Wäsche und Kleidung"),
    Kategorie("pflege18", "Gleitgel & Pflege", (
        "gleitgel", "gleitmittel", "kondom", "kondome", "massageöl",
        "stimulationsgel", "toycleaner", "toy-cleaner", "desinfektion",
    ), erwachsen=True, hinweis="Gleitgel, Kondome, Pflege"),
    Kategorie("seiten18", "Seiten-Abo & Zugang", (
        "premium-account", "premium account", "vod", "video on demand",
        "cam-", "camseite", "livecam", "webcam-portal", "onlyfans",
        "mitgliedschaft", "premium-mitgliedschaft", "portal-zugang",
        "streaming-abo", "monatsabo", "jahresabo", "abo", "abonnement",
        "flatrate", "zugang", "premium", "membership", "subscription",
    ), erwachsen=True,
       hinweis="Abos und Zugänge für Internetseiten"),
)

_NACH_KEY = {k.key: k for k in KATEGORIEN}


def _muster(begriff: str) -> str:
    """Ein Begriff als Regex - vorn am Wortanfang, hinten je nach Laenge.

    Lang genug ist eindeutig genug: "kopfhörer" darf hinten weiterlaufen
    und trifft damit auch "Kopfhörern" und "Kopfhörer-Set". Kurze Begriffe
    brauchen eine Bremse, sonst findet "abo" das Wort "above" und "vod"
    das Wort "vodafone".
    """
    kern = re.escape(begriff.strip()).replace(r"\ ", r"\s+")
    if len(begriff.strip()) <= KURZ_BIS:
        return kern + r"(?:s|n|e|en|er)?(?![a-z0-9äöüß])"
    return kern


def _regex_fuer(kategorie: Kategorie) -> re.Pattern[str]:
    alternativen = "|".join(_muster(b) for b in
                            sorted(kategorie.begriffe, key=len, reverse=True))
    return re.compile(r"(?<![a-z0-9äöüß])(?:" + alternativen + ")",
                      re.IGNORECASE)


_REGEX = {k.key: _regex_fuer(k) for k in KATEGORIEN}


def _normalisiere(text: str) -> str:
    """Kleinschreibung, Umlaute erhalten, Bindestriche zu Wortgrenzen.

    NFKC macht aus typografischen Varianten die gewoehnlichen Zeichen -
    sonst geht ein Begriff an einem Halbgeviertstrich vorbei.
    """
    text = unicodedata.normalize("NFKC", text or "").lower()
    return re.sub(r"\s+", " ", text.replace("–", "-").replace("—", "-"))


@dataclass
class Befund:
    """Welche Kategorien passen - und woran es lag."""
    keys: list[str] = field(default_factory=list)
    treffer: dict[str, list[str]] = field(default_factory=dict)

    @property
    def text(self) -> str:
        """Speicherform in der Datenbank: '|speicher|computer|'.

        Ein Trennzeichen aussen herum, damit `LIKE '%|ssd|%'` nicht
        versehentlich in einem laengeren Schluessel landet.
        """
        return als_text(self.keys)


def als_text(keys: list[str] | tuple[str, ...]) -> str:
    sauber = [k for k in keys if k in _NACH_KEY]
    return "|" + "|".join(sauber) + "|" if sauber else ""


def aus_text(text: str | None) -> list[str]:
    return [k for k in (text or "").split("|") if k and k in _NACH_KEY]


def bestimme(titel: str, beschreibung: str | None = None,
             tags: list[str] | None = None, *,
             erwachsen: bool = False) -> Befund:
    """Kategorien fuer einen Deal.

    Der Titel zaehlt doppelt: in der Beschreibung stehen Fussnoten,
    Versandhinweise und Querverweise auf andere Angebote - wer die gleich
    gewichtet, macht aus jedem Deal eine Wortwolke.
    """
    titel_norm = _normalisiere(titel)
    rest = _normalisiere(" ".join(filter(None, [
        beschreibung or "", " ".join(tags or [])])))

    punkte: dict[str, int] = {}
    treffer: dict[str, list[str]] = {}

    for kategorie in KATEGORIEN:
        # 18+-Marken nur an 18+-Funde, und normale Marken bleiben beiden
        # erhalten - ein Toy ist auch ein Geschenk, aber kein Werkzeug.
        if kategorie.erwachsen and not erwachsen:
            continue
        regex = _REGEX[kategorie.key]
        im_titel = {m.group(0).strip() for m in regex.finditer(titel_norm)}
        im_rest = {m.group(0).strip() for m in regex.finditer(rest)}
        if not im_titel and not im_rest:
            continue
        punkte[kategorie.key] = 2 * len(im_titel) + len(im_rest)
        treffer[kategorie.key] = sorted(im_titel | im_rest)[:4]

    if not punkte:
        return Befund()

    reihenfolge = {k.key: i for i, k in enumerate(KATEGORIEN)}
    keys = sorted(punkte, key=lambda k: (-punkte[k], reihenfolge[k]))[:MAX_PRO_DEAL]
    return Befund(keys, {k: treffer[k] for k in keys})


def label(key: str) -> str:
    kategorie = _NACH_KEY.get(key)
    return kategorie.label if kategorie else key


def alle(*, erwachsen: bool = False) -> list[Kategorie]:
    """Die Kategorien, die in diesem Bereich zur Auswahl stehen."""
    return [k for k in KATEGORIEN if k.erwachsen == erwachsen] if erwachsen \
        else [k for k in KATEGORIEN if not k.erwachsen]


def als_dict(kategorie: Kategorie) -> dict:
    return {"key": kategorie.key, "label": kategorie.label,
            "hinweis": kategorie.hinweis, "erwachsen": kategorie.erwachsen}


# --- Bestand nachtragen ----------------------------------------------------

def fuer_deal(deal) -> Befund:
    """Kategorien fuer einen Deal-Datensatz (oder ein DealItem)."""
    return bestimme(getattr(deal, "titel", "") or "",
                    getattr(deal, "beschreibung", None),
                    list(getattr(deal, "tags", None) or []),
                    erwachsen=bool(getattr(deal, "erwachsen", False)))


def nachtragen(db, grenze: int = 2000) -> int:
    """Kategorien nachtragen - fuer neue Deals und nach einer Listenaenderung.

    Zwei Betriebsarten, und die zweite ist der eigentliche Grund:

    1. **Luecken fuellen.** Deals ohne Marken bekommen welche. Das betrifft
       den Bestand von vor dieser Funktion und alles, was auf anderem Weg
       in die Tabelle kam.
    2. **Neu einstufen.** Steht in `VERSION` eine andere Zahl als in der
       Datenbank, hat sich die Wortliste geaendert - dann wird der ganze
       Bestand noch einmal durchgesehen. Ohne diesen Durchlauf waere jede
       Korrektur an der Liste fuer alles Alte wirkungslos.

    Beides laeuft in Haeppchen (beim Start und im Aufraeum-Job) und merkt
    sich, wo es stand: ein Neustart mitten im Durchlauf verliert nichts.
    """
    from sqlalchemy import select

    from .db import get_setting, set_setting
    from .models import Deal

    stand = get_setting(db, SCHLUESSEL_STAND) or {}
    if not isinstance(stand, dict):
        stand = {}
    grenze = max(1, grenze)

    if stand.get("version") != VERSION:
        cursor = int(stand.get("cursor") or 0)
        offen = list(db.scalars(
            select(Deal).where(Deal.id > cursor).order_by(Deal.id).limit(grenze)))
        for deal in offen:
            deal.kategorien = fuer_deal(deal).text or ""
        if len(offen) < grenze:
            # Durch - ab jetzt wieder der guenstige Luecken-Modus.
            set_setting(db, SCHLUESSEL_STAND, {"version": VERSION, "cursor": 0})
        else:
            set_setting(db, SCHLUESSEL_STAND,
                        {"version": stand.get("version"), "cursor": offen[-1].id})
        db.commit()
        return len(offen)

    offen = list(db.scalars(
        select(Deal).where(Deal.kategorien.is_(None)).limit(grenze)))
    if not offen:
        return 0
    for deal in offen:
        # Leerstring statt None: sonst faende der naechste Lauf denselben
        # Deal wieder und liefe endlos im Kreis.
        deal.kategorien = fuer_deal(deal).text or ""
    db.commit()
    return len(offen)
