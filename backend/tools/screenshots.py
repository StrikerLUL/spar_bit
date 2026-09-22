import asyncio
import pathlib

from playwright.async_api import async_playwright

BASIS = "http://127.0.0.1:8811"
ZIEL = pathlib.Path("docs/bilder")
ZIEL.mkdir(parents=True, exist_ok=True)

SEITEN = [
    ("feed", "/feed", "Feed mit Urteilen"),
    ("preisfehler", "/preisfehler", "Preisfehler-Wächter"),
    ("regeln", "/regeln", "Regel-Editor mit Live-Vorschau"),
    ("wunschliste", "/wunschliste", "Wunschlisten mit Budget"),
    ("statistiken", "/statistiken", "Statistiken und Sparbilanz"),
    ("dashboard", "/", "Dashboard"),
]

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
            args=["--no-sandbox"])
        ctx = await browser.new_context(viewport={"width": 1440, "height": 950},
                                        device_scale_factor=2)
        seite = await ctx.new_page()

        await seite.goto(f"{BASIS}/", wait_until="networkidle")
        # Anmelden
        if await seite.locator('input#username').count():
            await seite.fill("input#username", "cillian")
            await seite.fill("input#password", "einGutesPasswort1")
            await seite.click('button[type="submit"]')
            await seite.wait_for_timeout(2500)

        for name, pfad, titel in SEITEN:
            await seite.goto(f"{BASIS}{pfad}", wait_until="networkidle")
            await seite.wait_for_timeout(2000)
            datei = ZIEL / f"{name}.png"
            await seite.screenshot(path=str(datei))
            print(f"{datei} ({datei.stat().st_size // 1024} KB) - {titel}")

        await browser.close()

asyncio.run(main())
