#!/usr/bin/env python3
"""Live-Verifikation aller Quellen - auf DEINEM Server auszufuehren.

Die Build-Umgebung, in der SparBit erzeugt wurde, hatte keinen Netzzugang zu
den Deal-Hosts. Dieses Skript holt die Verifikation nach: es ruft jeden
Endpoint wirklich auf, laesst den echten Parser der Quelle darueberlaufen und
schreibt die Machbarkeitstabelle, die dabei herauskommt.

    python -m tools.verify_endpoints                     # Tabelle ausgeben
    python -m tools.verify_endpoints --json bericht.json # maschinenlesbar
    python -m tools.verify_endpoints --save-fixtures tests/fixtures/live
    python -m tools.verify_endpoints --only epic,steam,mydealz

Mit --save-fixtures werden die echten Antworten gespeichert; danach laufen
die Parser-Tests gegen echte Daten statt gegen synthetische:

    pytest tests/ --live-fixtures tests/fixtures/live
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SPARBIT_DATA_DIR", "/tmp/sparbit-verify")

from app.config import settings                            # noqa: E402
from app.http import NotModified, PoliteClient, RateLimited  # noqa: E402
from app.sources import all_sources, get_source            # noqa: E402
from app.sources.base import FetchContext                  # noqa: E402

RESET, BOLD = "\033[0m", "\033[1m"
GREEN, RED, YELLOW, GREY = "\033[32m", "\033[31m", "\033[33m", "\033[90m"


def colour(text: str, code: str, on: bool) -> str:
    return f"{code}{text}{RESET}" if on else text


async def check_one(src, api_key: str | None, http: PoliteClient,
                    fixture_dir: Path | None) -> dict:
    """Eine Quelle mit ihrem echten Parser gegen den echten Endpoint fahren."""
    ctx = FetchContext(http=http, options=dict(src.default_options),
                       api_key=api_key, log=None)

    captured: list[tuple[str, bytes, str]] = []
    if fixture_dir is not None:
        original_get = http.get

        async def recording_get(url, **kwargs):
            resp = await original_get(url, **kwargs)
            captured.append((url, resp.content,
                             resp.headers.get("content-type", "")))
            return resp

        http.get = recording_get   # type: ignore[method-assign]

    t0 = time.monotonic()
    row = {
        "id": src.id,
        "quelle": src.display_name,
        "kategorie": src.category.value,
        "key_noetig": src.requires_api_key,
        "key_gesetzt": bool(api_key),
        "experimentell": src.experimental,
        "docs": src.docs_url,
        "endpoints": _endpoints_of(src),
    }

    if src.requires_api_key and not api_key:
        row |= {"ok": None, "status": "uebersprungen",
                "detail": f"API-Key noetig - setze {_env_name(src.id)}",
                "items": 0, "ms": 0}
        return row

    try:
        result = await src.health_check(ctx)
        row |= {
            "ok": result.ok,
            "status": "ok" if result.ok else "fehler",
            "detail": result.detail,
            "items": result.items_found,
            "ms": result.latency_ms,
            "beispiel": (result.samples[0].titel[:90] if result.samples else None),
        }
    except NotModified:
        row |= {"ok": True, "status": "ok", "detail": "304 Not Modified",
                "items": 0, "ms": int((time.monotonic() - t0) * 1000)}
    except RateLimited as exc:
        row |= {"ok": False, "status": "rate-limit", "detail": str(exc),
                "items": 0, "ms": int((time.monotonic() - t0) * 1000)}
    except Exception as exc:
        row |= {"ok": False, "status": "fehler",
                "detail": f"{type(exc).__name__}: {exc}"[:300],
                "items": 0, "ms": int((time.monotonic() - t0) * 1000)}
    finally:
        if fixture_dir is not None:
            http.get = original_get   # type: ignore[method-assign]

    if fixture_dir is not None and captured:
        fixture_dir.mkdir(parents=True, exist_ok=True)
        for idx, (url, body, ctype) in enumerate(captured):
            ext = "json" if "json" in ctype else "xml"
            name = f"{src.id}" + (f"_{idx}" if idx else "") + f".{ext}"
            (fixture_dir / name).write_bytes(body)
        row["fixtures"] = len(captured)

    return row


def _endpoints_of(src) -> list[str]:
    """Welche URLs eine Quelle mit Default-Optionen anfassen wuerde."""
    opts = src.default_options
    urls: list[str] = []
    for key in ("endpoint", "catalog_endpoint", "giveaway_endpoint",
                "featured_endpoint", "appdetails_endpoint", "stores_endpoint",
                "feed_url"):
        if opts.get(key):
            urls.append(str(opts[key]))
    base = getattr(src, "base_url", "")
    for path in (opts.get("feeds") or []):
        urls.append(path if str(path).startswith("http")
                    else base.rstrip("/") + "/" + str(path).lstrip("/"))
    for sub in (opts.get("subreddits") or [])[:3]:
        urls.append(f"{opts.get('base', 'https://www.reddit.com')}/r/{sub}/new/.rss")
    return urls or ["(im UI zu konfigurieren)"]


def _env_name(source_id: str) -> str:
    return f"SPARBIT_KEY_{source_id.upper()}"


def render_table(rows: list[dict], use_colour: bool = True) -> str:
    head = (f"{'Quelle':<22} {'Kategorie':<13} {'Funktioniert':<14} "
            f"{'Key':<6} {'Items':>6} {'Zeit':>8}  Detail")
    lines = [BOLD + head + RESET if use_colour else head, "-" * 118]

    for r in sorted(rows, key=lambda x: (x["kategorie"], x["quelle"])):
        if r["ok"] is True:
            verdict, code = "ja", GREEN
        elif r["ok"] is False:
            verdict, code = "NEIN", RED
        else:
            verdict, code = "uebersprungen", YELLOW
        key = ("ja" if r["key_noetig"] else "nein")
        lines.append(
            f"{r['quelle']:<22} {r['kategorie']:<13} "
            f"{colour(f'{verdict:<14}', code, use_colour)} "
            f"{key:<6} {r['items']:>6} {r['ms']:>7}ms  {r['detail'][:70]}"
        )
    return "\n".join(lines)


def render_markdown(rows: list[dict]) -> str:
    out = ["| Quelle | Endpoint | Funktioniert | Key noetig | Items | Latenz | Detail |",
           "|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda x: (x["kategorie"], x["quelle"])):
        verdict = {True: "ja", False: "**nein**", None: "uebersprungen"}[r["ok"]]
        endpoint = r["endpoints"][0] if r["endpoints"] else "-"
        if len(r["endpoints"]) > 1:
            endpoint += f" (+{len(r['endpoints']) - 1})"
        out.append(f"| {r['quelle']} | `{endpoint}` | {verdict} | "
                   f"{'ja' if r['key_noetig'] else 'nein'} | {r['items']} | "
                   f"{r['ms']}ms | {r['detail'][:110].replace('|', '/')} |")
    return "\n".join(out)


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="Komma-Liste von Quellen-IDs")
    ap.add_argument("--json", metavar="DATEI", help="Bericht als JSON speichern")
    ap.add_argument("--markdown", metavar="DATEI", help="Tabelle als Markdown speichern")
    ap.add_argument("--save-fixtures", metavar="ORDNER",
                    help="Echte Antworten als Test-Fixtures ablegen")
    ap.add_argument("--no-colour", action="store_true")
    args = ap.parse_args()

    wanted = {s.strip() for s in args.only.split(",")} if args.only else None
    sources = [s for s in all_sources() if wanted is None or s.id in wanted]
    if wanted:
        for missing in wanted - {s.id for s in sources}:
            print(f"Unbekannte Quelle: {missing}", file=sys.stderr)

    fixture_dir = Path(args.save_fixtures) if args.save_fixtures else None
    use_colour = not args.no_colour and sys.stdout.isatty()

    print(f"Pruefe {len(sources)} Quellen live gegen die echten Endpoints ...\n")

    rows = []
    with_client = PoliteClient(user_agent=settings.user_agent,
                                     timeout=settings.http_timeout,
                                     per_host_delay=settings.per_host_delay)
    try:
        for src in sources:
            api_key = os.environ.get(_env_name(src.id))
            row = await check_one(src, api_key, with_client, fixture_dir)
            rows.append(row)
            mark = {True: "ok  ", False: "FEHL", None: "uebs"}[row["ok"]]
            print(f"  [{mark}] {src.display_name:<24} {row['detail'][:78]}")
    finally:
        await with_client.aclose()

    print("\n" + render_table(rows, use_colour))

    ok = sum(1 for r in rows if r["ok"] is True)
    bad = sum(1 for r in rows if r["ok"] is False)
    skipped = sum(1 for r in rows if r["ok"] is None)
    print(f"\n{ok} funktionieren, {bad} nicht, {skipped} uebersprungen (kein Key).")

    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=2, ensure_ascii=False))
        print(f"JSON-Bericht: {args.json}")
    if args.markdown:
        Path(args.markdown).write_text(render_markdown(rows))
        print(f"Markdown-Tabelle: {args.markdown}")
    if fixture_dir:
        print(f"Fixtures in: {fixture_dir}  "
              f"(danach: pytest tests/ --live-fixtures {fixture_dir})")

    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
