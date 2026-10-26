#!/usr/bin/env python3
"""
SEO-Metadaten der eigenen Karriereseite (Standard: Seite 4408) in WordPress setzen:
  1. Beitragsbild (für og:image / Vorschaubild): Mediathek-Eintrag „og-karriere“
     wird per REST als featured_media gesetzt.
  2. Yoast-Felder (SEO-Titel, Meta-Beschreibung, Fokus-Keyphrase) über die
     normale Bearbeitungsansicht der Seite (Yoast-Metabox), danach „Aktualisieren“.
  3. Kontrolle über yoast_head_json der REST-API.

Zugangsdaten nur über WP_USER / WP_PASS. Optional: WP_URL, WP_PAGE_ID, CHROME_PATH.
"""
import asyncio, json, os, re, sys

from playwright.async_api import async_playwright

BASE = os.environ.get("WP_URL", "https://provision-infra.de").rstrip("/")
USER = os.environ.get("WP_USER")
PASS = os.environ.get("WP_PASS")
PAGE_ID = int(os.environ.get("WP_PAGE_ID", "4408"))
CHROME = os.environ.get("CHROME_PATH")
SEO_TITLE = "Karriere bei ProVision Infra: Jobs in Bad Bevensen"
SEO_DESC = "Jobs in Bad Bevensen bei ProVision Infra: Servicetechniker, IT, Vertrieb, Büro (m/w/d). Digitale Schließsysteme und Videoüberwachung. Lebenslauf genügt."
FOCUS = "Jobs in Bad Bevensen"
PAUSE = 20


async def rest(ctx, method, url, retries=10, **kw):
    r = None
    for i in range(retries):
        r = await getattr(ctx.request, method)(url, **kw)
        ctype = (r.headers.get("content-type") or "").lower()
        json_expected = "/wp-json/" in url
        if r.status not in (429, 502, 503, 504) and not (json_expected and r.status == 200 and "json" not in ctype):
            return r
        print(f"  Ratenlimit/Störung ({r.status}), warte 60s ...", flush=True)
        await asyncio.sleep(60)
    return r


async def main():
    if not USER or not PASS:
        sys.exit("WP_USER und WP_PASS müssen gesetzt sein.")
    async with async_playwright() as p:
        browser = await p.chromium.launch(**({"executable_path": CHROME} if CHROME else {}))
        ctx = await browser.new_context(viewport={"width": 1400, "height": 1000}, locale="de-DE")
        page = await ctx.new_page()
        await page.goto(f"{BASE}/wp-login.php?redirect_to={BASE}/", wait_until="domcontentloaded")
        await page.fill("#user_login", USER)
        await page.fill("#user_pass", PASS)
        await page.click("#wp-submit")
        await page.wait_for_load_state("load")
        await page.wait_for_timeout(1500)
        if "wp-login.php" in page.url:
            sys.exit("Login fehlgeschlagen.")
        await page.goto("about:blank")
        print("angemeldet, warte 45s ...", flush=True)
        await asyncio.sleep(45)
        r = await rest(ctx, "get", f"{BASE}/wp-admin/admin-ajax.php?action=rest-nonce")
        nonce = (await r.text()).strip()
        if not re.fullmatch(r"[0-9a-f]{10}", nonce):
            sys.exit("Keine REST-Nonce erhalten.")
        H = {"X-WP-Nonce": nonce}

        # 1) Beitragsbild
        await asyncio.sleep(PAUSE)
        r = await rest(ctx, "get", f"{BASE}/wp-json/wp/v2/media?search=og-karriere&per_page=5", headers=H)
        media = await r.json() if r.status == 200 else []
        media = [m for m in media if "og-karriere" in (m.get("source_url") or "")]
        if not media:
            sys.exit("Mediathek-Eintrag og-karriere nicht gefunden (zuerst wp_publish_draft.py ausführen).")
        media_id = media[0]["id"]
        await asyncio.sleep(PAUSE)
        r = await rest(ctx, "get", f"{BASE}/wp-json/wp/v2/pages/{PAGE_ID}?context=edit", headers=H)
        pg = await r.json()
        if pg.get("featured_media") != media_id:
            await asyncio.sleep(PAUSE)
            r = await rest(ctx, "post", f"{BASE}/wp-json/wp/v2/pages/{PAGE_ID}", headers=H, data={"featured_media": media_id})
            if r.status != 200:
                sys.exit(f"Beitragsbild konnte nicht gesetzt werden: {r.status} {(await r.text())[:200]}")
            print("Beitragsbild gesetzt: Medien-ID", media_id, flush=True)
        else:
            print("Beitragsbild bereits gesetzt.", flush=True)

        # 2) Yoast-Felder über die Bearbeitungsansicht
        await asyncio.sleep(PAUSE)
        await page.goto(f"{BASE}/wp-admin/post.php?post={PAGE_ID}&action=edit", wait_until="domcontentloaded")
        print("Bearbeitungsansicht wird geladen ...", flush=True)
        # Yoast-Metabox (Classic-Metabox oder Block-Editor-Sidebar)
        title_sel = "#focus-keyword-input-metabox, #focus-keyword-input-sidebar"
        await page.wait_for_selector(title_sel, state="attached", timeout=180000)
        await page.wait_for_timeout(2000)
        # Eingeklappte Yoast-Metabox (Classic-Editor) aufklappen und in den Sichtbereich holen
        await page.evaluate("""() => { const box=document.querySelector('#wpseo_meta'); if (box && box.classList.contains('closed')) { const h=box.querySelector('.handlediv, .postbox-header button'); if (h) h.click(); } }""")
        await page.wait_for_timeout(800)
        await page.evaluate("""() => { const el=document.querySelector('#focus-keyword-input-metabox'); if (el) el.scrollIntoView({block:'center'}); }""")
        await page.wait_for_selector(title_sel, state="visible", timeout=30000)
        # Block-Editor: Willkommens-Dialog schließen
        for sel in ["button[aria-label='Diesen Dialog schließen']", "button[aria-label='Close dialog']", ".components-modal__header button"]:
            try:
                await page.locator(sel).first.click(timeout=1500)
            except Exception:
                pass

        async def fill(selector_ids, value):
            for sid in selector_ids:
                el = page.locator(sid).first
                if await el.count():
                    await el.scroll_into_view_if_needed()
                    await el.click()
                    await page.keyboard.press("Control+A")
                    await page.keyboard.press("Backspace")
                    await page.keyboard.type(value, delay=5)
                    return True
            return False

        ok1 = await fill(["#focus-keyword-input-metabox", "#focus-keyword-input-sidebar"], FOCUS)
        # Yoast nutzt für Titel/Beschreibung contenteditable-Felder (Draft.js); bei Bedarf Snippet-Editor öffnen
        for sel in ["#yoast-snippet-editor-metabox button", "#yoast-snippet-editor-sidebar button", "button:has-text('Snippet bearbeiten')", "button:has-text('Edit snippet')"]:
            try:
                await page.locator(sel).first.click(timeout=1500); await page.wait_for_timeout(500); break
            except Exception:
                pass
        ok2 = await fill(["#yoast-google-preview-title-metabox", "#yoast-google-preview-title-sidebar"], SEO_TITLE)
        ok3 = await fill(["#yoast-google-preview-description-metabox", "#yoast-google-preview-description-sidebar"], SEO_DESC)
        print("Felder gefüllt:", {"keyphrase": ok1, "titel": ok2, "beschreibung": ok3}, flush=True)
        if not (ok2 and ok3):
            await page.screenshot(path="dist/wp-seo-metabox.png", full_page=True)
            sys.exit("Yoast-Felder nicht gefunden (Screenshot dist/wp-seo-metabox.png).")
        await page.wait_for_timeout(1000)
        # Speichern: Classic „Aktualisieren“ (#publish) oder Block-Editor „Aktualisieren“
        saved = False
        for sel in ["#publish", "button.editor-post-publish-button__button", "button:has-text('Aktualisieren')", "button:has-text('Update')"]:
            try:
                await page.locator(sel).first.click(timeout=2000); saved = True; break
            except Exception:
                pass
        if not saved:
            sys.exit("Speichern-Button nicht gefunden.")
        await page.wait_for_timeout(6000)
        print("gespeichert.", flush=True)

        # 3) Kontrolle
        await asyncio.sleep(PAUSE)
        r = await rest(ctx, "get", f"{BASE}/wp-json/wp/v2/pages/{PAGE_ID}", headers=H)
        pg = await r.json()
        yh = pg.get("yoast_head_json") or {}
        print("Kontrolle: title =", yh.get("title"), "| description =", (yh.get("description") or "")[:90], "| og:image =", (yh.get("og_image") or [{}])[0].get("url"), "| featured_media =", pg.get("featured_media"), flush=True)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
