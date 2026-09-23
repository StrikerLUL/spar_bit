#!/usr/bin/env bash
#
# SparBit auf einem VPS einrichten.
#
#   curl -fsSL https://raw.githubusercontent.com/StrikerLUL/spar_bit/HEAD/install.sh | bash
#
# HEAD statt eines Branchnamens: das ist immer der Standard-Branch des
# Repositories, auch nachdem er umbenannt wurde. Ein fest eingetragener
# Name ergibt nach einer Umbenennung einen 404 - und curl | bash zeigt
# dann gar nichts an, sondern tut einfach nichts.
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

lies() {
  # Den Wert zurueckliefern, der wirklich in der .env steht. setze() laesst
  # vorhandene Werte stehen - eine Meldung, die stattdessen den erkannten
  # Wert nennt, sagt dann etwas Falsches.
  grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2-
}

setze_hart() {
  # Wie setze(), aber ersetzt auch einen schon vorhandenen Wert. Noetig fuer
  # Schluessel, die in der .env.example bereits belegt sind.
  local key="$1" wert="$2"
  if grep -qE "^${key}=" .env 2>/dev/null; then
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

  # Gemeinsames Geheimnis zwischen Web-UI und dem Update-Skript auf dem Host.
  # Ohne das gibt es den Update-Bereich im UI nicht.
  local update_token
  update_token="$(openssl rand -hex 32 2>/dev/null \
                  || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  setze SPARBIT_UPDATE_TOKEN "$update_token"

  local tz
  tz="$(cat /etc/timezone 2>/dev/null || echo Europe/Berlin)"
  setze TZ "$tz"
  tz="$(lies TZ)"
  ok "Zeitzone: $tz  (wichtig für Ruhezeiten und den Claimer-Zeitplan)"
  local system_tz
  system_tz="$(cat /etc/timezone 2>/dev/null || echo '?')"
  if [ "$tz" != "$system_tz" ]; then
    ok "Der Server selbst läuft auf $system_tz — SparBit rechnet in $tz."
    printf '    Andere Zeitzone gewünscht? TZ in %s/.env ändern.\n' "$ZIEL"
  fi
}


# --- 4. Domain und HTTPS ---------------------------------------------------

# Wer belegt Port 80/443? Steht dort schon ein Webserver, kann der
# mitgelieferte Caddy nicht starten - und die Fehlermeldung von Docker
# ("address already in use") sagt dem Benutzer nichts.
port_belegt() {
  local port="$1"
  # ss und netstat sehen auch Dienste, die nur auf einer oeffentlichen
  # Adresse lauschen. Fehlen beide (schlanke Images), bleibt der Versuch,
  # selbst eine Verbindung aufzubauen - dafuer braucht es nur die bash.
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${port}$" && return 0
  elif command -v netstat >/dev/null 2>&1; then
    netstat -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${port}$" && return 0
  fi
  (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null && exec 3>&- && return 0
  return 1
}

frage_domain() {
  schritt "Erreichbarkeit"

  if grep -qE '^SPARBIT_DOMAIN=.+' .env 2>/dev/null; then
    DOMAIN="$(grep -E '^SPARBIT_DOMAIN=' .env | head -1 | cut -d= -f2-)"
    ok "Domain aus .env: $DOMAIN"
    return
  fi

  if port_belegt 80 || port_belegt 443; then
    warn "Port 80/443 ist schon belegt - hier läuft bereits ein Webserver."
    printf '\n'
    printf '  Dann bringt SparBit kein eigenes HTTPS mit, sondern kommt als\n'
    printf '  Subdomain hinter deinen vorhandenen Proxy. Das Skript richtet\n'
    printf '  dafür alles ein, was auf dieser Seite liegt:\n'
    printf '    - der Web-Port wird nur an 127.0.0.1 gebunden\n'
    printf '    - den Eintrag im Proxy trägst du danach selbst ein\n'
    printf '      (Anleitung: README.md, "Auf einer Subdomain")\n\n'
    setze_hart SPARBIT_WEB_BIND 127.0.0.1
    DOMAIN=""
    ok "Ohne eigenes HTTPS - nur auf 127.0.0.1:${SPARBIT_WEB_PORT:-8080}"
    HINTER_PROXY=1
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

# --- 5b. Updates per Knopfdruck --------------------------------------------

richte_updates_ein() {
  schritt "Updates"

  if ! command -v systemctl >/dev/null 2>&1; then
    warn "Kein systemd - der Update-Knopf im UI bleibt ohne Wirkung."
    printf '    Von Hand aktualisieren: %s/sparbit update\n' "$ZIEL"
    return
  fi

  # Der Timer laeuft als der Benutzer, dem das Verzeichnis gehoert. Sonst
  # gehoerten die von git angelegten Dateien danach root, und ein spaeteres
  # "./sparbit update" von Hand scheiterte an den Rechten.
  local besitzer
  besitzer="$(stat -c '%U' "$ZIEL" 2>/dev/null || id -un)"

  local unit=/etc/systemd/system/sparbit-update.service
  local timer=/etc/systemd/system/sparbit-update.timer

  als_root cp "$ZIEL/deploy/sparbit-update.service" "$unit"
  als_root cp "$ZIEL/deploy/sparbit-update.timer" "$timer"
  als_root sed -i "s|/opt/sparbit|$ZIEL|g; s|^User=.*|User=$besitzer|" "$unit"

  als_root systemctl daemon-reload
  if als_root systemctl enable --now sparbit-update.timer >/dev/null 2>&1; then
    ok "Timer läuft — der Knopf im UI wirkt binnen einer Minute"
    printf '    Neue Commits werden stündlich bemerkt; ob sie auch\n'
    printf '    eingespielt werden, entscheidet der Schalter im UI\n'
    printf '    unter „Logs & System → Updates".\n'
  else
    warn "Timer ließ sich nicht starten: systemctl status sparbit-update.timer"
  fi
}


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
  elif [ -n "${HINTER_PROXY:-}" ]; then
    url="http://127.0.0.1:${SPARBIT_WEB_PORT:-8080}  (nur lokal)"
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

  if [ -n "${HINTER_PROXY:-}" ]; then
    printf '  %s!%s Noch ein Schritt: Eintrag in deinem Reverse-Proxy.\n' "$Y" "$N"
    printf '    Ziel:      127.0.0.1:%s\n' "${SPARBIT_WEB_PORT:-8080}"
    printf '    Wichtig:   /api/events nicht puffern, X-Forwarded-Proto setzen\n'
    printf '    Anleitung: %s/README.md, Abschnitt "Auf einer Subdomain"\n\n' "$ZIEL"
  elif [ -z "${DOMAIN:-}" ]; then
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
  richte_updates_ein
  abschluss
}

main "$@"
