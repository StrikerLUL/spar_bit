from app.claimer import parse_events


def test_parst_claim_ereignisse(load_text):
    events = parse_events(load_text("claimer.log"), "claimer.log")
    by_title = {e["titel"]: e for e in events}

    assert by_title["Control"]["status"] == "claimed"
    assert by_title["Control"]["platform"] == "epic"
    assert by_title["Alan Wake 2"]["status"] == "already"
    assert by_title["Fallout 76"]["status"] == "claimed"
    assert by_title["Fallout 76"]["platform"] == "prime"
    assert by_title["Baldurs Gate 3"]["status"] == "failed"
    assert "button not found" in by_title["Baldurs Gate 3"]["detail"]


def test_ignoriert_rauschen(load_text):
    events = parse_events(load_text("claimer.log"), "claimer.log")
    titles = {e["titel"] for e in events}
    assert "Starting free-games-claimer" not in titles
    assert not any("Signed in" in t for t in titles)


def test_leeres_log():
    assert parse_events("", "x.log") == []


def test_ansi_codes_stoeren_nicht():
    raw = "\x1b[32m2025-01-01 [epic-games] claimed: Control\x1b[0m"
    events = parse_events(raw, "x.log")
    assert events and events[0]["titel"] == "Control"
