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
        await page.wait_for_selector("#wpseo_meta, #focus-keyword-input-sidebar", state="attached", timeout=180000)
        await page.wait_for_timeout(3000)
        # Diagnose: warum ist das Keyphrase-Feld ggf. unsichtbar?
        diag = await page.evaluate("""() => {
            const out = {};
            const box = document.querySelector('#wpseo_meta');
            out.box = box ? {cls: box.className, display: getComputedStyle(box).display} : null;
            const hide = document.querySelector('#wpseo_meta-hide');
            out.screenOption = hide ? hide.checked : null;
            const el = document.querySelector('#focus-keyword-input-metabox');
            out.input = !!el;
            if (el) {
                const chain = [];
                for (let n = el; n && n !== document.body; n = n.parentElement) {
                    const cs = getComputedStyle(n);
                    if (cs.display === 'none' || cs.visibility === 'hidden' || n.hidden) chain.push((n.id ? '#' + n.id : n.tagName.toLowerCase() + '.' + [...n.classList].slice(0, 3).join('.')) + ' [' + cs.display + '/' + cs.visibility + ']');
                }
                out.hiddenBy = chain;
            }
            out.hiddenFields = ['yoast_wpseo_focuskw', 'yoast_wpseo_title', 'yoast_wpseo_metadesc'].map(id => [id, !!document.getElementById(id)]);
            out.store = !!(window.wp && wp.data && wp.data.select && wp.data.select('yoast-seo/editor'));
            return out;
        }""")
        print("Diagnose:", json.dumps(diag, ensure_ascii=False), flush=True)
        # Metabox über „Ansicht anpassen“ einblenden, falls ausgeblendet
        if diag.get("screenOption") is False:
            await page.click("#show-settings-link")
            await page.wait_for_timeout(600)
            await page.check("#wpseo_meta-hide")
            await page.wait_for_timeout(1200)
            await page.click("#show-settings-link")
            print("Yoast-Metabox über „Ansicht anpassen“ eingeblendet.", flush=True)
        # Eingeklappte Metabox aufklappen
        await page.evaluate("""() => { const box=document.querySelector('#wpseo_meta'); if (box && box.classList.contains('closed')) { const h=box.querySelector('.handlediv, .postbox-header button'); if (h) h.click(); } }""")
        await page.wait_for_timeout(800)
        # Werte direkt in den Yoast-Store und die versteckten Formularfelder schreiben
        res = await page.evaluate("""([focus, title, desc]) => {
            const out = {};
            try {
                const d = wp.data.dispatch('yoast-seo/editor');
                if (d.setFocusKeyword) { d.setFocusKeyword(focus); out.focusStore = true; }
                if (d.updateData) { d.updateData({ title: title, description: desc }); out.dataStore = true; }
            } catch (e) { out.storeError = String(e).slice(0, 120); }
            const set = (id, v) => { const el = document.getElementById(id); if (!el) return false; el.value = v; el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); return true; };
            out.hidden = [set('yoast_wpseo_focuskw', focus), set('yoast_wpseo_title', title), set('yoast_wpseo_metadesc', desc)];
            return out;
        }""", [FOCUS, SEO_TITLE, SEO_DESC])
        print("Store/Felder:", res, flush=True)
        await page.wait_for_timeout(1500)
        check = await page.evaluate("""() => ['yoast_wpseo_focuskw', 'yoast_wpseo_title', 'yoast_wpseo_metadesc'].map(id => { const el = document.getElementById(id); return el ? el.value : null; })""")
        print("Formularfelder jetzt:", check, flush=True)
        if check[1] != SEO_TITLE or check[2] != SEO_DESC:
            # Erneut setzen, falls ein Store-Abgleich die Felder überschrieben hat
            await page.evaluate("""([focus, title, desc]) => { const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; }; set('yoast_wpseo_focuskw', focus); set('yoast_wpseo_title', title); set('yoast_wpseo_metadesc', desc); }""", [FOCUS, SEO_TITLE, SEO_DESC])
            check = await page.evaluate("""() => ['yoast_wpseo_focuskw', 'yoast_wpseo_title', 'yoast_wpseo_metadesc'].map(id => { const el = document.getElementById(id); return el ? el.value : null; })""")
            print("Formularfelder (2. Versuch):", check, flush=True)
            if check[1] != SEO_TITLE or check[2] != SEO_DESC:
                await page.screenshot(path="dist/wp-seo-metabox.png", full_page=True)
                sys.exit("Yoast-Formularfelder konnten nicht gesetzt werden (Screenshot dist/wp-seo-metabox.png).")
        # Speichern. Block-Editor: Metabox-Felder über den eigenen Metabox-Request des Editors
        # speichern (derselbe Weg wie beim Klick auf „Aktualisieren“, aber ohne den Seiteninhalt
        # erneut zu übertragen). Klassischer Editor: „Aktualisieren“ (#publish).
        status_before = await page.evaluate("() => { const el = document.querySelector('#original_post_status'); return el ? el.value : null; }")
        print("Status vor dem Speichern:", status_before, flush=True)
        has_block_editor = await page.evaluate("() => !!(window.wp && wp.data && wp.data.select('core/edit-post') && typeof wp.data.dispatch('core/edit-post').requestMetaBoxUpdates === 'function')")
        if has_block_editor:
            result = await page.evaluate("""async () => {
                try {
                    await wp.data.dispatch('core/edit-post').requestMetaBoxUpdates();
                    for (let i = 0; i < 90; i++) {
                        if (!wp.data.select('core/edit-post').isSavingMetaBoxes()) return 'gespeichert';
                        await new Promise(r => setTimeout(r, 1000));
                    }
                    return 'timeout';
                } catch (e) { return 'Fehler: ' + String(e).slice(0, 160); }
            }""")
            print("Metabox-Speicherung (Block-Editor):", result, flush=True)
            if result != 'gespeichert':
                sys.exit("Speichern der Yoast-Felder fehlgeschlagen.")
        else:
            btn = page.locator("#publish").first
            if not await btn.count():
                sys.exit("Speichern-Button (#publish) nicht gefunden.")
            async with page.expect_navigation(wait_until="domcontentloaded", timeout=120000):
                await btn.click()
            await page.wait_for_timeout(3000)
            print("gespeichert (klassischer Editor):", page.url.split("?")[-1], flush=True)

        # 3) Kontrolle
        await asyncio.sleep(PAUSE)
        r = await rest(ctx, "get", f"{BASE}/wp-json/wp/v2/pages/{PAGE_ID}", headers=H)
        pg = await r.json()
        yh = pg.get("yoast_head_json") or {}
        print("Kontrolle: title =", yh.get("title"), "| description =", (yh.get("description") or "")[:90], "| og:image =", (yh.get("og_image") or [{}])[0].get("url"), "| featured_media =", pg.get("featured_media"), flush=True)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
