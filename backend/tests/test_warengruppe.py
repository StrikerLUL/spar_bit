"""Warengruppen: was ist das Ding, nicht woher kommt es.

Der Unterschied zum Feld `kategorie` ist der Kern: das sagt, aus
welcher Art Quelle ein Fund kam. Hier geht es um die Ware. Wer beides
verwechselt, baut eine Regel „nur Elektronik" und bekommt alles aus
Deal-Communities.

Auch hier gilt: keine Gruppe ist ein gueltiges Ergebnis. Eine erfundene
waere schlimmer, weil eine Regel darauf dann falsch greift.
"""
import pytest

from app.warengruppe import GRUPPEN, bestimme, label


@pytest.mark.parametrize("titel,gruppe", [
    ("LEGO Technic 42143 Ferrari Daytona", "spielzeug"),
    ("Sony WH-1000XM5 Kopfhörer", "elektronik"),
    ("Samsung 990 PRO 2TB NVMe SSD", "computer"),
    ("Bosch Professional Akkuschrauber GSR 18V", "werkzeug"),
    ("Nike Air Max Sneaker Gr. 44", "kleidung"),
    ("PlayStation 5 Slim Konsole", "gaming"),
    ("Tchibo Kaffeebohnen 1 kg", "lebensmittel"),
    ("Philips Sonicare Zahnbürste", "drogerie"),
    ("Siemens EQ.6 Kaffeevollautomat", "haushalt"),
    ("Dune Teil 2 Blu-ray Steelbook", "medien"),
    ("Microsoft 365 Family Lizenz 1 Jahr", "software"),
    ("Deutschlandticket für 49 €", "reise"),
])
def test_typische_titel_landen_richtig(titel, gruppe):
    ist, _ = bestimme(titel)
    assert ist == gruppe, f"{titel} -> {ist}"


@pytest.mark.parametrize("titel", [
    "Sammeldeal: 20 Artikel reduziert",
    "20 % auf alles bei einem Händler",
    "Newsletter-Gutschein über 5 €",
])
def test_ohne_hinweis_wird_nichts_erfunden(titel):
    gruppe, wort = bestimme(titel)
    assert gruppe is None
    assert wort is None


def test_das_ausloesende_wort_kommt_mit():
    """Ohne Begruendung waere die Einteilung im UI nicht nachvollziehbar."""
    gruppe, wort = bestimme("Neuer Monitor von Dell, 27 Zoll")
    assert gruppe == "computer"
    assert wort == "monitor"


def test_der_titel_wiegt_schwerer_als_die_beschreibung():
    """In der Beschreibung steht oft Zubehoer, das in die falsche Gruppe zieht."""
    gruppe, _ = bestimme("LEGO Technic Bagger",
                         "Inklusive USB-Kabel und Ladegerät")
    assert gruppe == "spielzeug"


def test_die_beschreibung_hilft_wenn_der_titel_schweigt():
    gruppe, _ = bestimme("Angebot der Woche",
                         "Ein Akkuschrauber von Bosch, stark reduziert")
    assert gruppe == "werkzeug"


def test_mitten_im_wort_zaehlt_nicht():
    """Sonst faende 'tv ' jedes 'Advent' und 'ssd' jedes 'Fassdauben'."""
    gruppe, _ = bestimme("Adventskalender mit Süßigkeiten")
    assert gruppe != "elektronik"


def test_jede_gruppe_hat_einen_anzeigenamen():
    for gruppe in GRUPPEN:
        assert label(gruppe)
    assert label(None) is None
    assert label("gibtsnicht") is None


def test_leere_eingabe_faellt_nicht_um():
    assert bestimme(None) == (None, None)
    assert bestimme("", "", []) == (None, None)


# --- Die Faelle, die die Wortmuster erst noetig gemacht haben -------------

def test_deutsche_komposita_werden_gefunden():
    """„Kaffeevollautomat" setzt das Hauptwort hinten an - wie jedes zweite
    deutsche Produktwort."""
    assert bestimme("Siemens Kaffeevollautomat")[0] == "haushalt"
    assert bestimme("Akkustaubsauger von Dyson")[0] == "haushalt"
    assert bestimme("Bluetooth-Kopfhörer")[0] == "elektronik"


def test_kurze_stichworte_haengen_sich_nicht_hinten_an():
    """„roller" darf keinen „Controller" einsammeln - sonst waere jedes
    Gamepad eine Reise."""
    assert bestimme("Xbox Wireless Controller")[0] == "gaming"


def test_ganze_woerter_bleiben_ganze_woerter():
    """„reis" ist Lebensmittel, „Reise" nicht."""
    assert bestimme("Basmati Reis 5 kg")[0] == "lebensmittel"
    assert bestimme("Reise nach Mallorca, 7 Nächte")[0] != "lebensmittel"
