## Worum es geht

<!-- Was ändert sich für den Benutzer? Nicht welche Datei angefasst wurde. -->

## Das Problem dahinter

<!-- Warum ist das so? Der Grund gehört auch in den Code, aber hier steht
     der längere Weg dorthin. -->

## Geprüft

- [ ] `ruff check .`
- [ ] `python -m pytest -q`
- [ ] `cd frontend && npm run lint && npm run typecheck && npm run build`
- [ ] `cd frontend && npm test` (falls die Oberfläche betroffen ist)

## Checkliste

- [ ] Verhaltensänderung hat einen Test, und der Testname sagt, worum es geht
- [ ] Schema-Änderung ist ein **neuer, nummerierter** Schritt in `migrations.py` — kein bestehender wurde geändert
- [ ] Neue Quelle startet als `UNVERIFIED` und steht in `ENDPOINTS.md`
- [ ] Neue Einstellung steht in `.env.example` und in `docs/`
- [ ] `CHANGELOG.md` unter *Unveröffentlicht* ergänzt
