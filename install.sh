#!/usr/bin/env bash
#
# SparBit auf einem VPS einrichten.
#
#   curl -fsSL https://raw.githubusercontent.com/StrikerLUL/spar_bit/refs/heads/claude/deal-freebie-zentrale-gpi8dr/install.sh | bash
#
# Oder, wenn das Repo schon da ist:  ./install.sh
#
# Das Skript ist absichtlich einzeln lauffaehig und ohne Argumente benutzbar.
# Alles, was es nicht sicher wissen kann, fragt es einmal - und merkt sich die
# Antwort in der .env, damit ein zweiter Lauf nichts erneut fragt.
#
set -euo pipefail

REPO="${SPARBIT_REPO:-https://github.com/StrikerLUL/spar_bit.git}"
ZIEL="${SPARBIT_DIR:-/opt/sparbit}"
# Leer = der Standard-Branch des Repos. Den fest zu verdrahten geht
# schief, sobald er anders heisst als erwartet.
BRANCH="${SPARBIT_BRANCH:-}"

# Farbe nur, wenn wirklich ein Terminal dranhaengt. Beim Pipen in eine Datei
# waeren die Steuerzeichen nur Muell.
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; C=$'\033[36m'; N=$'\033[0m'
else
  B=""; G=""; Y=""; R=""; C=""; N=""
fi

schritt() { printf '\n%s▸ %s%s\n' "$C$B" "$1" "$N"; }
ok()      { printf '  %s✓%s %s\n' "$G" "$N" "$1"; }
warn()    { printf '  %s!%s %s\n' "$Y" "$N" "$1"; }
fehler()  { printf '  %s✗%s %s\n' "$R" "$N" "$1" >&2; }
abbruch() { fehler "$1"; [ $# -gt 1 ] && printf '\n    %s\n\n' "$2"; exit 1; }

# Ein interaktives Skript, das per "curl | bash" laeuft, hat kein stdin mehr -
# das haengt dann still. Darum wird /dev/tty benutzt, wenn es eines gibt, und
# sonst gar nicht gefragt.
frage() {
  local text="$1" standard="${2:-}" antwort=""
  if [ -e /dev/tty ]; then
    printf '  %s' "$text" > /dev/tty
    read -r antwort < /dev/tty || antwort=""
  fi
  printf '%s' "${antwort:-$standard}"
}

ja_nein() {
  local antwort
  antwort="$(frage "$1 [j/N] " "n")"
  case "$antwort" in [jJyY]*) return 0 ;; *) return 1 ;; esac
}


# --- 1. Voraussetzungen ----------------------------------------------------

als_root() { if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi; }

pruefe_system() {
  schritt "System prüfen"

  if [ "$(uname -s)" != "Linux" ]; then
    warn "Nicht Linux — das Skript ist für einen VPS gedacht."
    warn "Auf dem eigenen Rechner reicht:  python run.py"
  fi

  if ! command -v git >/dev/null 2>&1; then
    warn "git fehlt, wird nachinstalliert ..."
    if command -v apt-get >/dev/null 2>&1; then
      als_root apt-get update -qq && als_root apt-get install -y -qq git
    elif command -v dnf >/dev/null 2>&1; then
      als_root dnf install -y -q git
    else
      abbruch "git fehlt und ich kenne deinen Paketmanager nicht." \
              "Bitte git von Hand installieren und noch einmal starten."
    fi
  fi
  ok "git vorhanden"

  if ! command -v docker >/dev/null 2>&1; then
    warn "Docker fehlt."
    if ja_nein "Docker jetzt über get.docker.com installieren?"; then
      curl -fsSL https://get.docker.com | als_root sh
      als_root systemctl enable --now docker 2>/dev/null || true
    else
      abbruch "Ohne Docker geht es hier nicht weiter." \
              "Anleitung: https://docs.docker.com/engine/install/"
    fi
  fi

  if ! docker compose version >/dev/null 2>&1; then
    abbruch "Docker ist da, aber 'docker compose' fehlt." \
            "Das Plugin docker-compose-plugin nachinstallieren."
  fi

  if ! docker info >/dev/null 2>&1; then
    abbruch "Docker läuft nicht oder dein Benutzer darf ihn nicht bedienen." \
            "Starten:  sudo systemctl start docker
    Rechte:   sudo usermod -aG docker \$USER   (danach neu anmelden)"
  fi
  ok "Docker läuft"

  # 768 MB Backend + Build. Unter 1 GB RAM wird der Frontend-Build vom
  # OOM-Killer abgeraeumt, und zwar wortlos - lieber vorher warnen.
  local mb
  mb="$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo 2>/dev/null || echo 9999)"
  if [ "$mb" -lt 1024 ]; then
    warn "Nur ${mb} MB RAM. Der Frontend-Build braucht ca. 1 GB."
    warn "Notfalls vorher Swap anlegen, sonst bricht der Build wortlos ab."
  fi
}


# --- 2. Code holen ---------------------------------------------------------

hole_code() {
  schritt "SparBit nach $ZIEL holen"

  # Laeuft das Skript schon im Repo? Dann nicht woanders hin klonen.
  if [ -f "docker-compose.yml" ] && [ -d "backend/app" ]; then
    ZIEL="$(pwd)"
    ok "Repo liegt schon hier: $ZIEL"
    return
  fi

  if [ -d "$ZIEL/.git" ]; then
    ok "Vorhandene Installation gefunden — wird aktualisiert"
    git -C "$ZIEL" pull --ff-only
  else
    als_root mkdir -p "$(dirname "$ZIEL")"
    local zweig=()
    [ -n "$BRANCH" ] && zweig=(-b "$BRANCH")
    if [ ! -w "$(dirname "$ZIEL")" ]; then
      als_root git clone --depth 1 "${zweig[@]}" "$REPO" "$ZIEL"
      als_root chown -R "$(id -u):$(id -g)" "$ZIEL"
    else
      git clone --depth 1 "${zweig[@]}" "$REPO" "$ZIEL"
    fi
    ok "Nach $ZIEL geklont"
  fi
  cd "$ZIEL"
}


# --- 3. Konfiguration ------------------------------------------------------

setze() {
  # Einen Schluessel in der .env setzen, ohne vorhandene Werte zu ueberschreiben.
  local key="$1" wert="$2"
  if grep -qE "^${key}=" .env 2>/dev/null; then
    local vorhanden
    vorhanden="$(grep -E "^${key}=" .env | head -1 | cut -d= -f2-)"
    [ -n "$vorhanden" ] && return
    # Leerer Wert: ersetzen. -i mit Backup-Suffix, weil BSD-sed das verlangt.
    sed -i.bak "s|^${key}=.*|${key}=${wert}|" .env && rm -f .env.bak
  else
    printf '%s=%s\n' "$key" "$wert" >> .env
  fi
}

konfiguriere() {
  schritt "Konfiguration anlegen"

  if [ ! -f .env ]; then
    cp .env.example .env
    ok ".env aus der Vorlage erstellt"
  else
    ok "Vorhandene .env wird weiterverwendet"
  fi
  chmod 600 .env

  # Der Sitzungsschluessel darf nicht leer bleiben: sonst wird bei jedem
  # Neustart ein neuer erzeugt und alle Anmeldungen fliegen raus.
  local key
  key="$(openssl rand -base64 48 2>/dev/null | tr -d '\n' \
         || head -c 36 /dev/urandom | base64 | tr -d '\n')"
  setze SPARBIT_SECRET_KEY "$key"

  local tz
  tz="$(cat /etc/timezone 2>/dev/null || echo Europe/Berlin)"
  setze TZ "$tz"
  ok "Zeitzone: $tz  (wichtig für Ruhezeiten)"
}


# --- 4. Domain und HTTPS ---------------------------------------------------

frage_domain() {
  schritt "Erreichbarkeit"

  if grep -qE '^SPARBIT_DOMAIN=.+' .env 2>/dev/null; then
    DOMAIN="$(grep -E '^SPARBIT_DOMAIN=' .env | head -1 | cut -d= -f2-)"
    ok "Domain aus .env: $DOMAIN"
    return
  fi

  printf '  Mit einer Domain richtet SparBit HTTPS automatisch ein\n'
  printf '  (Caddy holt das Zertifikat bei Let'"'"'s Encrypt).\n'
  printf '  Ohne Domain läuft es auf Port %s — dann bitte nur über\n' "${SPARBIT_WEB_PORT:-8080}"
  printf '  ein VPN oder einen SSH-Tunnel benutzen, nicht offen ins Netz.\n\n'

  DOMAIN="$(frage "Domain (leer lassen = ohne HTTPS): ")"
  if [ -n "$DOMAIN" ]; then
    setze SPARBIT_DOMAIN "$DOMAIN"
    local mail
    mail="$(frage "E-Mail für Let's Encrypt (optional): ")"
    [ -n "$mail" ] && setze SPARBIT_ACME_MAIL "$mail"
    ok "HTTPS für $DOMAIN"
    warn "Der A-Record von $DOMAIN muss auf diesen Server zeigen,"
    warn "sonst scheitert die Zertifikatsausstellung."
  else
    ok "Ohne Domain — nur über Port ${SPARBIT_WEB_PORT:-8080}"
  fi
}


# --- 5. Starten ------------------------------------------------------------

starten() {
  schritt "Container bauen und starten"
  printf '  Beim ersten Mal dauert das ein paar Minuten.\n\n'

  local profile=()
  [ -n "${DOMAIN:-}" ] && profile=(--profile https)

  docker compose "${profile[@]}" up -d --build

  schritt "Auf den ersten Start warten"
  local i
  for i in $(seq 1 60); do
    if docker compose ps --format json 2>/dev/null | grep -q '"Health":"healthy"' \
       || curl -fsS "http://127.0.0.1:${SPARBIT_WEB_PORT:-8080}/healthz" >/dev/null 2>&1; then
      ok "SparBit antwortet"
      return 0
    fi
    sleep 2
  done
  warn "SparBit antwortet noch nicht. Logs ansehen mit:  ./sparbit logs"
}


# --- 6. Abschluss ----------------------------------------------------------

abschluss() {
  local url
  if [ -n "${DOMAIN:-}" ]; then
    url="https://$DOMAIN"
  else
    local ip
    ip="$(curl -fsS --max-time 4 https://api.ipify.org 2>/dev/null \
          || hostname -I 2>/dev/null | awk '{print $1}' || echo localhost)"
    url="http://${ip}:${SPARBIT_WEB_PORT:-8080}"
  fi

  cat <<FERTIG

${G}${B}  SparBit läuft.${N}

  Oberfläche:   ${C}${url}${N}
  Verzeichnis:  ${ZIEL}

  ${B}Jetzt im Browser:${N}
    1. Benutzername und Passwort festlegen (erster Aufruf)
    2. Unter "Benachrichtigungen" einen Kanal anlegen — ohne den
       meldet sich SparBit nie, auch nicht bei einem Preisfehler
    3. Unter "Quellen" mydealz einschalten

  ${B}Bedienung:${N}
    ${ZIEL}/sparbit status     Was läuft gerade
    ${ZIEL}/sparbit logs       Logs mitlesen
    ${ZIEL}/sparbit update     Auf den neuesten Stand bringen
    ${ZIEL}/sparbit sichern    Datenbank sichern

FERTIG

  if [ -z "${DOMAIN:-}" ]; then
    printf '  %s!%s Ohne HTTPS: Port %s nicht offen ins Internet hängen.\n' \
           "$Y" "$N" "${SPARBIT_WEB_PORT:-8080}"
    printf '    SSH-Tunnel:  ssh -L 8080:127.0.0.1:8080 %s@<server>\n\n' "$(id -un)"
  fi
}


main() {
  printf '\n%s  SparBit — Deal- und Preisfehler-Wächter%s\n' "$B" "$N"
  pruefe_system
  hole_code
  cd "$ZIEL"
  konfiguriere
  frage_domain
  starten
  abschluss
}

main "$@"
