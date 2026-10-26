#!/usr/bin/env python3
"""
Trägt den CSS-Block aus tools/header-nav.css im WordPress-Customizer unter
„Zusätzliches CSS“ ein (oder entfernt ihn wieder). Genutzt wird die
Customizer-Oberfläche selbst (wp.customize-API im Browser), also derselbe Weg,
den ein Mensch im Backend gehen würde. Andere Inhalte des Feldes bleiben erhalten.

Modi:
  --show     aktuelles Zusätzliches CSS anzeigen (nichts ändern)
  --apply    Block einfügen bzw. ersetzen und veröffentlichen
  --remove   Block entfernen und veröffentlichen

Zugangsdaten nur über WP_USER / WP_PASS (werden nicht geloggt).
Optional: WP_URL, CHROME_PATH.
"""
import asyncio, os, pathlib, re, sys

from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
CSS_FILE = ROOT / "tools/header-nav.css"
BASE = os.environ.get("WP_URL", "https://provision-infra.de").rstrip("/")
USER = os.environ.get("WP_USER")
PASS = os.environ.get("WP_PASS")
CHROME = os.environ.get("CHROME_PATH")
START = "/* === ProVision Karriere-Header: Anfang === */"
END = "/* === ProVision Karriere-Header: Ende === */"


def merge(existing: str, block: str) -> str:
    existing = existing or ""
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END) + r"\n?", re.S)
    existing = pattern.sub("", existing).rstrip()
    if not block:
        return existing + ("\n" if existing else "")
    return (existing + "\n\n" if existing else "") + block.strip() + "\n"


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--show"
    if not USER or not PASS:
        sys.exit("WP_USER und WP_PASS müssen gesetzt sein.")
    block = CSS_FILE.read_text(encoding="utf-8") if mode == "--apply" else ""
    async with async_playwright() as p:
        browser = await p.chromium.launch(**({"executable_path": CHROME} if CHROME else {}))
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900}, locale="de-DE")
        page = await ctx.new_page()
        await page.goto(f"{BASE}/wp-login.php?redirect_to={BASE}/", wait_until="domcontentloaded")
        await page.fill("#user_login", USER)
        await page.fill("#user_pass", PASS)
        await page.click("#wp-submit")
        await page.wait_for_load_state("load")
        await page.wait_for_timeout(1500)
        if "wp-login.php" in page.url:
            sys.exit("Login fehlgeschlagen.")
        print("angemeldet, warte 45s (Anfrage-Drossel) ...", flush=True)
        await asyncio.sleep(45)

        await page.goto(f"{BASE}/wp-admin/customize.php?autofocus[section]=custom_css", wait_until="domcontentloaded")
        print("Customizer wird geladen ...", flush=True)
        await page.wait_for_function("() => window.wp && wp.customize && wp.customize('custom_css') && wp.customize.state && wp.customize.state('saved')", timeout=180000)
        await page.wait_for_timeout(3000)
        current = await page.evaluate("() => wp.customize('custom_css').get() || ''")
        print(f"Aktuelles Zusätzliches CSS: {len(current)} Zeichen", flush=True)
        if mode == "--show":
            print(current[:3000])
            await browser.close()
            return
        new = merge(current, block)
        if new.strip() == current.strip():
            print("Keine Änderung nötig.", flush=True)
            await browser.close()
            return
        await page.evaluate("(css) => wp.customize('custom_css').set(css)", new)
        await page.wait_for_timeout(1500)
        # Veröffentlichen über den regulären Button (Status muss „publish“ bleiben)
        await page.evaluate("() => { const s = wp.customize.state('selectedChangesetStatus'); if (s) s.set('publish'); }")
        await page.click("#save")
        await page.wait_for_function("() => wp.customize.state('saved').get() === true", timeout=120000)
        await page.wait_for_timeout(2000)
        check = await page.evaluate("() => wp.customize('custom_css').get() || ''")
        ok = (START in check) if mode == "--apply" else (START not in check)
        print("gespeichert:", "ok" if ok else "unerwarteter Inhalt", f"| {len(check)} Zeichen", flush=True)
        await browser.close()
        # Kontrolle von außen
        async with async_playwright() as p2:
            b2 = await p2.chromium.launch(**({"executable_path": CHROME} if CHROME else {}))
            c2 = await b2.new_context(viewport={"width": 1440, "height": 900})
            pg2 = await c2.new_page()
            await pg2.goto(f"{BASE}/?nowprocket=1", wait_until="load")
            has = await pg2.evaluate("() => !!document.querySelector('#wp-custom-css') && document.querySelector('#wp-custom-css').textContent.includes('ProVision Karriere-Header')")
            print("Live sichtbar (Startseite, ohne Cache):", has, flush=True)
            await b2.close()


if __name__ == "__main__":
    asyncio.run(main())
