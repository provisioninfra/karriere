#!/usr/bin/env python3
"""
Setzt den eigenen Entwurf „Karriere“ (Slug karriere) auf „veröffentlicht“.

- Ändert nur den Status der angegebenen Seite (WP_PAGE_ID, Standard 4408),
  keinen Inhalt. Die Seite muss ein Entwurf sein, der dem angemeldeten
  Benutzer gehört; sonst bricht das Skript ab.
- Prüft anschließend anonym, ob die Seite unter /karriere/ erreichbar ist.

Zugangsdaten nur über Umgebungsvariablen WP_USER / WP_PASS (werden nicht
geloggt). Optional: WP_URL, WP_PAGE_ID, CHROME_PATH.
"""
import asyncio, os, re, sys

from playwright.async_api import async_playwright

BASE = os.environ.get("WP_URL", "https://provision-infra.de").rstrip("/")
USER = os.environ.get("WP_USER")
PASS = os.environ.get("WP_PASS")
PAGE_ID = int(os.environ.get("WP_PAGE_ID", "4408"))
CHROME = os.environ.get("CHROME_PATH")


async def rest(ctx, method, url, retries=6, **kw):
    for i in range(retries):
        r = await getattr(ctx.request, method)(url, **kw)
        if r.status not in (429, 503):
            return r
        wait = 15 * (i + 1)
        print(f"  Ratenlimit ({r.status}), warte {wait}s ...", flush=True)
        await asyncio.sleep(wait)
    return r


async def main():
    if not USER or not PASS:
        sys.exit("WP_USER und WP_PASS müssen gesetzt sein.")
    async with async_playwright() as p:
        browser = await p.chromium.launch(**({"executable_path": CHROME} if CHROME else {}))
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900}, locale="de-DE")
        page = await ctx.new_page()
        await page.goto(f"{BASE}/wp-login.php", wait_until="domcontentloaded")
        await page.fill("#user_login", USER)
        await page.fill("#user_pass", PASS)
        await page.click("#wp-submit")
        await page.wait_for_load_state("load")
        await page.wait_for_timeout(1500)
        if "wp-login.php" in page.url:
            sys.exit("Login fehlgeschlagen.")
        r = await rest(ctx, "get", f"{BASE}/wp-admin/admin-ajax.php?action=rest-nonce")
        nonce = (await r.text()).strip()
        if not re.fullmatch(r"[0-9a-f]{10}", nonce):
            sys.exit("Keine REST-Nonce erhalten.")
        H = {"X-WP-Nonce": nonce}

        r = await rest(ctx, "get", f"{BASE}/wp-json/wp/v2/users/me?context=edit", headers=H)
        me = await r.json()
        r = await rest(ctx, "get", f"{BASE}/wp-json/wp/v2/pages/{PAGE_ID}?context=edit", headers=H)
        if r.status != 200:
            sys.exit(f"Seite {PAGE_ID} nicht lesbar: {r.status}")
        pg = await r.json()
        print("Seite:", pg["id"], "|", pg["title"]["raw"], "| Slug", pg["slug"], "| Status", pg["status"], "| Autor", pg["author"], flush=True)
        if pg["status"] != "draft" or pg["author"] != me["id"]:
            sys.exit("Abbruch: Seite ist kein eigener Entwurf.")
        if pg["slug"] != "karriere" or pg.get("template") != "elementor_canvas":
            sys.exit("Abbruch: Slug oder Vorlage weichen ab.")

        r = await rest(ctx, "post", f"{BASE}/wp-json/wp/v2/pages/{PAGE_ID}", headers=H, data={"status": "publish"})
        if r.status != 200:
            sys.exit(f"Veröffentlichen fehlgeschlagen: {r.status} {(await r.text())[:300]}")
        pg = await r.json()
        print("Veröffentlicht:", pg["status"], "|", pg["link"], flush=True)
        await browser.close()

        # Anonyme Kontrolle
        async with async_playwright() as p2:
            b2 = await p2.chromium.launch(**({"executable_path": CHROME} if CHROME else {}))
            c2 = await b2.new_context(viewport={"width": 1440, "height": 900})
            pg2 = await c2.new_page()
            resp = await pg2.goto(f"{BASE}/karriere/?nowprocket=1", wait_until="load")
            await pg2.wait_for_timeout(2500)
            title = await pg2.title()
            h1 = await pg2.evaluate("document.querySelector('h1')?.textContent?.trim() || ''")
            print("Live-Check:", resp.status if resp else None, "|", title, "|", h1[:80], flush=True)
            await pg2.screenshot(path="dist/live-karriere.png")
            await b2.close()


if __name__ == "__main__":
    asyncio.run(main())
