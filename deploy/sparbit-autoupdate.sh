#!/usr/bin/env bash
#
# Haelt SparBit auf dem Stand seines Git-Zweigs.
#
# Laeuft auf dem Host, nicht im Container - dort gibt es weder git noch
# Docker. Ein systemd-Timer startet das Skript minuetlich; ausgeloest wird
# ein Update von zweierlei:
#
#   - Knopf im Web-UI            (jedes Mal geprueft, wirkt binnen einer Minute)
#   - neue Commits + Automatik   (Fernabfrage hoechstens alle
#                                 SPARBIT_UPDATE_INTERVALL Sekunden)
#
# Der Draht zum UI ist die API mit dem Token aus SPARBIT_UPDATE_TOKEN -
# kein gemeinsames Verzeichnis, damit es keinen Streit um Dateirechte gibt.
#
set -uo pipefail

WURZEL="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
cd "$WURZEL" || exit 1

ZUSTAND="${SPARBIT_UPDATE_STATE:-$WURZEL/.update}"
SPERRE="$ZUSTAND/sperre"
PROTOKOLL="$ZUSTAND/letztes-update.log"
INTERVALL="${SPARBIT_UPDATE_INTERVALL:-900}"
mkdir -p "$ZUSTAND"

# git als root in einem Verzeichnis, das jemand anderem gehoert, verweigert
# sonst den Dienst ("dubious ownership"). Ueber die Umgebung gesetzt, damit
# nichts in eine globale Konfiguration geschrieben wird.
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0=safe.directory
export GIT_CONFIG_VALUE_0="$WURZEL"

jetzt_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }
meldung()   { printf '%s %s\n' "$(jetzt_iso)" "$*"; }

# --- Zugang zur API --------------------------------------------------------

wert_aus_env() {
  grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'"'"'\r'
}

TOKEN="${SPARBIT_UPDATE_TOKEN:-$(wert_aus_env SPARBIT_UPDATE_TOKEN)}"
PORT="$(wert_aus_env SPARBIT_WEB_PORT)"; PORT="${PORT:-8080}"
API="http://127.0.0.1:$PORT/api/system/update"

if [ -z "$TOKEN" ]; then
  meldung "SPARBIT_UPDATE_TOKEN fehlt in der .env - Auto-Update ist aus."
  exit 0
fi

api() {
  local methode="$1" pfad="$2" daten="${3:-}"
  if [ -n "$daten" ]; then
    curl -fsS --max-time 20 -X "$methode" "$API$pfad" \
      -H "X-SparBit-Update: $TOKEN" -H "Content-Type: application/json" \
      --data-binary "$daten"
  else
    curl -fsS --max-time 20 -X "$methode" "$API$pfad" \
      -H "X-SparBit-Update: $TOKEN"
  fi
}

# melde <json>  - schickt einen Teilbericht; was fehlt, bleibt im UI stehen.
melde() { api POST /bericht "$1" >/dev/null 2>&1 || true; }

# --- Nur ein Lauf gleichzeitig ---------------------------------------------

if ! mkdir "$SPERRE" 2>/dev/null; then
  # Verwaiste Sperre nach einem Absturz nach 30 Minuten freigeben.
  if [ -n "$(find "$SPERRE" -maxdepth 0 -mmin +30 2>/dev/null)" ]; then
    rmdir "$SPERRE" 2>/dev/null && mkdir "$SPERRE" 2>/dev/null || exit 0
  else
    exit 0
  fi
fi
trap 'rmdir "$SPERRE" 2>/dev/null' EXIT

# --- Auftrag holen ---------------------------------------------------------

# -w schreibt den Status hinter die Antwort; -f wuerde bei 403 gar nichts
# liefern und "falsches Token" saehe aus wie "Server ist aus".
antwort="$(curl -sS --max-time 20 -w '\n%{http_code}' "$API/auftrag" \
           -H "X-SparBit-Update: $TOKEN" 2>/dev/null)"
code="$(printf '%s' "$antwort" | tail -n1)"
auftrag="$(printf '%s' "$antwort" | sed '$d')"

case "$code" in
  200) ;;
  403) meldung "Token abgelehnt. SPARBIT_UPDATE_TOKEN in der .env stimmt nicht"
       meldung "mit dem ueberein, mit dem der Container laeuft -"
       meldung "nach einer Aenderung: ./sparbit neustart backend"
       exit 1 ;;
  404) meldung "Dieser SparBit-Stand kennt die Update-API noch nicht."
       meldung "Einmal von Hand aktualisieren: ./sparbit update"
       exit 1 ;;
  000|"")
       # curl schreibt 000, wenn die Verbindung gar nicht zustande kam.
       meldung "SparBit antwortet nicht auf Port $PORT - Lauf uebersprungen."
       exit 0 ;;
  *)   meldung "Unerwartete Antwort $code von der Update-API."
       exit 1 ;;
esac

lies_flag() {
  printf '%s' "$auftrag" | python3 -c "
import json, sys
try: print('1' if json.load(sys.stdin).get(sys.argv[1]) else '0')
except Exception: print('0')" "$1" 2>/dev/null || printf '0'
}

knopf="$(lies_flag jetzt)"
automatik="$(lies_flag auto)"
claimer_auftrag="$(lies_flag claimer)"

# --- Claimer auf Zuruf -----------------------------------------------------
#
# Derselbe Weg wie beim Update: der Container darf den Host nicht anfassen,
# also legt das UI einen Auftrag ab und hier wird er ausgefuehrt.

if [ "$claimer_auftrag" = "1" ]; then
  claimer_log="$ZUSTAND/claimer.log"
  api POST /claimer-bericht '{"laeuft": true}' >/dev/null 2>&1 || true
  meldung "Claimer wird gestartet"
  : > "$claimer_log"
  docker compose run --rm claimer >> "$claimer_log" 2>&1
  claimer_rc=$?

  ZEIT="$(jetzt_iso)" RC="$claimer_rc" LOG="$claimer_log" python3 - \
      > "$ZUSTAND/claimer-bericht.json" <<'PYEND'
import json, os
try:
    ausgabe = open(os.environ["LOG"], encoding="utf-8", errors="replace").read()
except OSError:
    ausgabe = ""
print(json.dumps({"laeuft": False, "zuletzt": os.environ["ZEIT"],
                  "ok": os.environ["RC"] == "0",
                  "ausgabe": ausgabe[-20000:]}, ensure_ascii=False))
PYEND
  api POST /claimer-bericht "$(cat "$ZUSTAND/claimer-bericht.json")" >/dev/null 2>&1 || true
  meldung "Claimer beendet (rc=$claimer_rc)"
fi

# --- Stand des Zweigs ------------------------------------------------------

zweig="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
[ -n "$zweig" ] && [ "$zweig" != "HEAD" ] || { meldung "Kein Git-Zweig."; exit 1; }

# Die Fernabfrage kostet eine Netzverbindung - nicht jede Minute.
marke="$ZUSTAND/zuletzt-geprueft"
faellig=1
if [ -f "$marke" ] && [ -z "$(find "$marke" -maxdepth 0 -mmin "+$((INTERVALL / 60))" 2>/dev/null)" ]; then
  faellig=0
fi

neue=""
geprueft=""
if [ "$faellig" = "1" ] || [ "$knopf" = "1" ]; then
  if git fetch --quiet origin "$zweig" 2>/dev/null; then
    neue="$(git rev-list --count "HEAD..origin/$zweig" 2>/dev/null || echo 0)"
    geprueft="$(jetzt_iso)"
    touch "$marke"
  fi
fi

# stand_json <laeuft> - der regelmaessige Kurzbericht ans UI.
stand_json() {
  WURZEL="$WURZEL" LAEUFT="$1" NEUE="$neue" GEPRUEFT="$geprueft" python3 - <<'PY'
import json, os, subprocess

def git(*args):
    try:
        lauf = subprocess.run(["git", "-C", os.environ["WURZEL"], *args],
                              capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    return lauf.stdout.strip() if lauf.returncode == 0 else None

raus = {
    "laeuft": os.environ["LAEUFT"] == "1",
    "zweig": git("rev-parse", "--abbrev-ref", "HEAD"),
    "commit": git("rev-parse", "HEAD"),
    "betreff": git("log", "-1", "--pretty=%s"),
    "commit_datum": git("log", "-1", "--pretty=%cI"),
}
if os.environ.get("NEUE"):
    raus["neue_commits"] = int(os.environ["NEUE"])
elif os.environ.get("NEUE") == "0":
    raus["neue_commits"] = 0
if os.environ.get("GEPRUEFT"):
    raus["geprueft_am"] = os.environ["GEPRUEFT"]
print(json.dumps(raus, ensure_ascii=False))
PY
}

# --- Soll aktualisiert werden? ---------------------------------------------

grund=""
if [ "$knopf" = "1" ]; then
  grund="knopf"
elif [ "$automatik" = "1" ] && [ "${neue:-0}" -gt 0 ] 2>/dev/null; then
  grund="automatisch"
fi

if [ -z "$grund" ]; then
  melde "$(stand_json 0)"
  exit 0
fi

# --- Aktualisieren ---------------------------------------------------------

melde "$(stand_json 1)"
vorher="$(git rev-parse HEAD)"
: > "$PROTOKOLL"

{
  meldung "Update wegen: $grund"
  # Vor jedem Update sichern. Kostet Sekunden und rettet im Zweifel alles.
  ./sparbit sichern "$ZUSTAND/vor-update.db" 2>&1 \
    || meldung "Sicherung fehlgeschlagen - Update trotzdem versucht"
  git fetch --quiet origin "$zweig" 2>&1
  git merge --ff-only "origin/$zweig" 2>&1
} >> "$PROTOKOLL" 2>&1
rc=$?

if [ $rc -eq 0 ]; then
  profil=""
  grep -qE '^SPARBIT_DOMAIN=.+' .env 2>/dev/null && profil="--profile https"

  # Fertiges Image statt Eigenbau, wenn es eines fuer genau diesen Commit
  # gibt. Das spart auf einem kleinen VPS mehrere Minuten und das halbe
  # RAM - und es kann nicht passieren, dass der Bau hier scheitert,
  # obwohl die CI gruen war.
  #
  # Genau *dieser* Commit: der Tag ist der Kurz-Hash. Wer eigene Commits
  # obendrauf hat oder in einem Fork arbeitet, findet keinen - dann wird
  # gebaut wie zuvor. Kein Ratespiel mit "latest", das zu einem anderen
  # Stand gehoert als der Quellbaum daneben.
  bezug="$(wert_aus_env SPARBIT_BEZUG)"; bezug="${bezug:-auto}"
  SPARBIT_TAG="sha-$(git rev-parse --short=7 HEAD)"
  export SPARBIT_TAG

  gezogen=0
  if [ "$bezug" != "build" ]; then
    meldung "Versuche fertige Images: $SPARBIT_TAG" >> "$PROTOKOLL"
    # shellcheck disable=SC2086
    if docker compose $profil pull --quiet backend frontend >> "$PROTOKOLL" 2>&1; then
      gezogen=1
    else
      meldung "Kein fertiges Image fuer $SPARBIT_TAG - es wird gebaut." >> "$PROTOKOLL"
    fi
  fi

  if [ "$gezogen" = "1" ]; then
    # shellcheck disable=SC2086
    docker compose $profil up -d >> "$PROTOKOLL" 2>&1
  else
    unset SPARBIT_TAG
    # shellcheck disable=SC2086
    docker compose $profil up -d --build >> "$PROTOKOLL" 2>&1
  fi
  rc=$?
  docker image prune -f >> "$PROTOKOLL" 2>&1 || true
fi

nachher="$(git rev-parse HEAD)"
neue=0
geprueft="$(jetzt_iso)"

# Der Abschlussbericht: Stand plus Ergebnis plus Protokoll fuer die
# Fehlersuche im UI.
ZEIT="$(jetzt_iso)" GRUND="$grund" RC="$rc" VON="$vorher" NACH="$nachher" \
STAND="$(stand_json 0)" LOG="$PROTOKOLL" python3 - > "$ZUSTAND/bericht.json" <<'PY'
import json, os

stand = json.loads(os.environ["STAND"])
try:
    protokoll = open(os.environ["LOG"], encoding="utf-8", errors="replace").read()
except OSError:
    protokoll = ""
ok = os.environ["RC"] == "0"
stand["protokoll"] = protokoll[-20000:]
stand["letztes_update"] = {
    "zeit": os.environ["ZEIT"],
    "grund": os.environ["GRUND"],
    "ok": ok,
    "von": os.environ["VON"][:7],
    "nach": os.environ["NACH"][:7],
    "fehler": None if ok else protokoll[-800:],
}
print(json.dumps(stand, ensure_ascii=False))
PY

# Nach einem Neubau braucht das Backend einen Moment, bis es wieder annimmt.
for _ in $(seq 1 30); do
  if melde "$(cat "$ZUSTAND/bericht.json")" && \
     api GET /auftrag >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

exit $rc
