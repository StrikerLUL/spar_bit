# Grafana-Dashboard

`sparbit-dashboard.json` importieren (Grafana → Dashboards → New → Import →
JSON hochladen) und beim Import die Prometheus-Datenquelle auswählen.

## Was Prometheus dafür braucht

`/api/metrics` ist **nicht offen** — die Zahlen verraten, welche Quellen
laufen und wie viele Deals hier liegen. Zugang hat, wer angemeldet ist oder
ein API-Token mitschickt. Ein Token legst du unter *Logs & System → API-Token*
an.

```yaml
# prometheus.yml
scrape_configs:
  - job_name: sparbit
    scrape_interval: 60s          # öfter bringt nichts, die Quellen laufen
                                  # im Minutentakt und länger
    metrics_path: /api/metrics
    static_configs:
      - targets: ["sparbit:8000"]
    authorization:
      type: Bearer
      credentials_file: /etc/prometheus/sparbit-token
```

## Die Panels

| Panel | Wofür es da ist |
|---|---|
| **Deals gesamt / Neue Deals (24 h)** | Flacht die zweite Zahl über Tage ab, liefert meist eine Quelle nicht mehr. |
| **Gesperrte Quellen** | Der Schutzschalter. Über 0 für mehrere Stunden ist ein echter Ausfall. |
| **Fehlerquote der Läufe** | Einzelne 429 sind normal. Dauerhaft über 30 % ist es nicht. |
| **Alter der Wechselkurse** | Der einzige Fehler, der sich sonst nie meldet — veraltete Kurse lassen Preisgrenzen bei USD/GBP/AUD leise danebengreifen. |
| **Zustand je Quelle** | Eine Zeile je Quelle, zum Nachsehen, wenn oben etwas rot ist. |
| **Zustellung je Kanal** | Fehlgeschlagene Zustellungen sind fast immer ein abgelaufenes Token. |

## Alarme, die sich lohnen

```promql
# Eine Quelle liefert seit sechs Stunden nichts mehr
sparbit_quelle_sekunden_seit_erfolg > 21600 and sparbit_quelle_eingeschaltet == 1

# Zustellung schlägt fehl
sum(sparbit_meldungen_fehler_24h) > 0

# Kurse veraltet
sparbit_kurse_alter_tage > 90 or sparbit_kurse_alter_tage == -1

# SparBit selbst meldet einen Mangel
min(sparbit_gesund) == 0
```

`sparbit_meldungen_24h` und `sparbit_meldungen_fehler_24h` sind **Gauges über
ein 24-Stunden-Fenster**, keine Counter. Grund: das Versandprotokoll wird nach
`SPARBIT_LOG_RETENTION_DAYS` gelöscht, und ein Counter, der dabei zurückspringt,
sieht für Prometheus wie ein Neustart aus — `increase()` würde dann einen Berg
zeigen, wo nichts war. Darum kein `rate()`/`increase()` auf diese beiden.
