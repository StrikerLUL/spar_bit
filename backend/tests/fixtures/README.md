# Fixtures

Diese Dateien sind **format-treue, aber synthetische** Beispiele. Sie wurden
von Hand geschrieben, weil die Build-Umgebung keine der Quellen erreichen
konnte (Egress-Policy). Sie testen also die Parser-Logik, nicht die Realitaet
des jeweiligen Endpoints.

**Echte Fixtures aufnehmen** (auf deinem VPS, wo das Netz offen ist):

    python -m tools.verify_endpoints --save-fixtures tests/fixtures/live

Danach laufen dieselben Tests gegen echte Antworten:

    pytest tests/ --live-fixtures tests/fixtures/live

Weicht das echte Format ab, schlagen die Tests fehl - genau so soll es sein.
