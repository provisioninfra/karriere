#!/usr/bin/env python3
"""
Legt die Karriereseite als NEUE Entwurfsseite in WordPress an bzw. aktualisiert
die eigene, bereits angelegte Seite (Entwurf oder veröffentlicht, Status bleibt).

Regeln (Vorgabe des Kunden): bestehende Seiten, Menüs, Plugins, Formulare
und Einstellungen werden nicht angefasst. Es entstehen nur neue Medien
und eine neue Seite im Status „Entwurf“.

Zugangsdaten ausschließlich über Umgebungsvariablen:
  WP_URL   (Standard: https://provision-infra.de)
  WP_USER
  WP_PASS
Nichts davon wird geloggt oder in Dateien geschrieben.

Ablauf:
  1. Login (wp-login.php) mit Playwright, REST-Nonce holen
  2. Prüfen, ob bereits eine Seite mit Slug „karriere“ existiert
  3. Bilder aus karriere/assets/img in die Mediathek laden (nur neue Dateien)
     -> tools/wp-media-map.json
  4. Bundle bauen (tools/build_wordpress_bundle.py)
  5. Seite „Karriere“ als Entwurf anlegen (Vorlage: Elementor Canvas)
  6. Elementor-Inhalt (ein Container, ein HTML-Widget, volle Breite) speichern
  7. Vorschau-Screenshot nach dist/ (ohne Admin-Leiste)

Aufruf:  WP_USER=… WP_PASS=… python3 tools/wp_publish_draft.py
"""
import asyncio, json, mimetypes, os, pathlib, random, re, string, subprocess, sys

from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
IMG_DIR = ROOT / "karriere/assets/img"
MAP_FILE = ROOT / "tools/wp-media-map.json"
DIST = ROOT / "dist"
BASE = os.environ.get("WP_URL", "https://provision-infra.de").rstrip("/")
USER = os.environ.get("WP_USER")
PASS = os.environ.get("WP_PASS")
CHROME = os.environ.get("CHROME_PATH")  # optional: eigener Chromium-Pfad

SKIP_IMAGES = {"button-unlocked.svg", "favicon-32.png", "favicon-192.png", "apple-touch-icon.png"}
TITLE_PREFIX = "Karriere – "


async def rest(ctx, method, url, retries=8, **kw):
    """REST-Aufruf mit Backoff bei Ratenlimit (429/503/502/504) oder HTML-Antwort statt JSON (Hoster-Drossel)."""
    r = None
    for i in range(retries):
        r = await getattr(ctx.request, method)(url, **kw)
        ctype = (r.headers.get("content-type") or "").lower()
        json_expected = "/wp-json/" in url or "rest-nonce" in url
        if r.status not in (429, 502, 503, 504) and not (json_expected and r.status == 200 and "json" not in ctype and "text/plain" not in ctype):
            return r
        wait = 15 * (i + 1)
        print(f"  Ratenlimit/Störung ({r.status}, {ctype[:20]}), warte {wait}s ...", flush=True)
        await asyncio.sleep(wait)
    return r


def eid():
    return "".join(random.choice(string.hexdigits.lower()) for _ in range(7))


def build_elements(html: str):
    """Ein Container in voller Breite ohne Innenabstand, darin ein HTML-Widget."""
    zero = {"unit": "px", "top": "0", "right": "0", "bottom": "0", "left": "0", "isLinked": True}
    return [{
        "id": eid(), "elType": "container", "isInner": False,
        "settings": {
            "content_width": "full",
            "width": {"unit": "%", "size": 100, "sizes": []},
            "padding": zero, "padding_tablet": zero, "padding_mobile": zero,
            "margin": zero,
            "flex_gap": {"unit": "px", "size": 0, "sizes": [], "column": "0", "row": "0", "isLinked": True},
        },
        "elements": [{
            "id": eid(), "elType": "widget", "widgetType": "html", "isInner": False,
            "settings": {"html": html, "_margin": zero, "_padding": zero},
            "elements": [],
        }],
    }]


async def main():
    if not USER or not PASS:
        sys.exit("WP_USER und WP_PASS müssen als Umgebungsvariablen gesetzt sein.")
    DIST.mkdir(exist_ok=True)

    async with async_playwright() as p:
        launch = {"executable_path": CHROME} if CHROME else {}
        browser = await p.chromium.launch(**launch)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900}, locale="de-DE")
        page = await ctx.new_page()

        # 1) Login
        await page.goto(f"{BASE}/wp-login.php", wait_until="domcontentloaded")
        await page.fill("#user_login", USER)
        await page.fill("#user_pass", PASS)
        await page.click("#wp-submit")
        await page.wait_for_load_state("load")
        await page.wait_for_timeout(1500)
        if "wp-login.php" in page.url:
            err = await page.locator("#login_error").all_inner_texts()
            sys.exit("Login fehlgeschlagen (Seite blieb auf wp-login.php). Meldung: " + " | ".join(t.strip() for t in err)[:300])
        r = await rest(ctx, "get", f"{BASE}/wp-admin/admin-ajax.php?action=rest-nonce")
        nonce = (await r.text()).strip()
        if not re.fullmatch(r"[0-9a-f]{10}", nonce):
            sys.exit("Keine REST-Nonce erhalten.")
        H = {"X-WP-Nonce": nonce}
        r = await rest(ctx, "get", f"{BASE}/wp-json/wp/v2/users/me?context=edit", headers=H)
        if r.status != 200 or not (await r.text()).lstrip().startswith("{"):
            body = (await r.text())[:400]
            sys.exit(f"REST-Zugriff fehlgeschlagen: HTTP {r.status}, Content-Type {r.headers.get('content-type')}, Anfang: {body!r}")
        me = await r.json()
        print("Angemeldet, Rollen:", me.get("roles"))

        # 2) Slug-Check (nur lesen)
        r = await rest(ctx, "get", f"{BASE}/wp-json/wp/v2/pages?slug=karriere&status=publish,draft,pending,private,future&context=edit", headers=H)
        existing = await r.json()
        if existing:
            print("Hinweis: Es existiert bereits eine Seite mit Slug 'karriere':",
                  [(e["id"], e["status"], e["link"]) for e in existing])
            print("Die neue Seite bekommt deshalb automatisch einen abweichenden Slug (z. B. karriere-2).")

        # 3) Medien hochladen (nur Dateien, die laut Map noch fehlen)
        media_map = json.loads(MAP_FILE.read_text()) if MAP_FILE.exists() else {}
        for f in sorted(IMG_DIR.iterdir()):
            if f.name in SKIP_IMAGES or f.name in media_map:
                continue
            mime = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            await asyncio.sleep(1.5)
            r = await rest(ctx, "post",
                f"{BASE}/wp-json/wp/v2/media",
                headers=H,
                multipart={
                    "file": {"name": f.name, "mimeType": mime, "buffer": f.read_bytes()},
                    "title": TITLE_PREFIX + f.stem,
                    "alt_text": "",
                },
            )
            if r.status not in (200, 201):
                sys.exit(f"Upload fehlgeschlagen für {f.name}: {r.status} {await r.text()}")
            j = await r.json()
            media_map[f.name] = j["source_url"]
            MAP_FILE.write_text(json.dumps(media_map, indent=2, ensure_ascii=False) + "\n")
            print("hochgeladen:", f.name, "->", j["source_url"], flush=True)

        # 4) Bundle bauen
        subprocess.run([sys.executable, str(ROOT / "tools/build_wordpress_bundle.py")], check=True)
        bundle = (DIST / "karriere-wordpress.html").read_text(encoding="utf-8")

        # 5) Eigene Seite wiederverwenden oder neu anlegen (nie fremde Seiten anfassen).
        #    Eine bereits veröffentlichte eigene Seite behält ihren Status, nur der Inhalt wird aktualisiert.
        own = [e for e in existing if e.get("author") == me.get("id") and e.get("status") in ("draft", "publish")]
        status = "draft"
        if own:
            pg = own[0]; post_id = pg["id"]; status = pg["status"]
            print("Eigene Seite vorhanden, wird aktualisiert: ID", post_id, "| Status", status, flush=True)
        else:
            r = await rest(ctx, "post",
                f"{BASE}/wp-json/wp/v2/pages", headers=H,
                data={"title": "Karriere", "slug": "karriere", "status": "draft",
                      "template": "elementor_canvas", "content": "",
                      "excerpt": "Karriere bei ProVision Infra: Servicetechniker, IT-Projekttechniker, Kundenberater und Büro- und Dispositionskraft (m/w/d)."},
            )
            if r.status not in (200, 201):
                sys.exit(f"Seite konnte nicht angelegt werden: {r.status} {await r.text()}")
            pg = await r.json()
            post_id = pg["id"]
            print("Entwurf angelegt: ID", post_id, "Slug", pg["slug"], "Template", pg.get("template"), flush=True)

        # 6) Elementor-Inhalt speichern (im Editor der NEUEN Seite)
        await page.goto(f"{BASE}/wp-admin/post.php?post={post_id}&action=elementor", wait_until="domcontentloaded")
        print("Elementor-Editor wird geladen ...", flush=True)
        await page.wait_for_function("() => window.elementor && window.elementorCommon && elementorCommon.ajax", timeout=120000)
        await page.wait_for_function("() => window.elementor.documents && elementor.documents.getCurrent && elementor.documents.getCurrent()", timeout=120000)
        await page.wait_for_timeout(3000)
        result = await page.evaluate(
            """([elements, settings]) => new Promise((resolve) => {
                elementorCommon.ajax.addRequest('save_builder', {
                    data: { status: settings.post_status, elements: elements, settings: settings },
                    success: (res) => resolve({ ok: true, res: res }),
                    error: (err) => resolve({ ok: false, err: (err && (err.message || JSON.stringify(err))) || 'unbekannt' })
                });
            })""",
            [build_elements(bundle), {"template": "elementor_canvas", "post_status": status}],
        )
        if not result.get("ok"):
            sys.exit(f"save_builder fehlgeschlagen: {result}")
        print("Elementor-Inhalt gespeichert.")

        # Kontrolle: Seite neu lesen
        r = await rest(ctx, "get", f"{BASE}/wp-json/wp/v2/pages/{post_id}?context=edit", headers=H)
        pg = await r.json()
        preview = pg["link"] if pg["status"] == "publish" else pg["link"] + ("&" if "?" in pg["link"] else "?") + "preview=true"
        print("Status:", pg["status"], "| Template:", pg.get("template"), "| Vorschau:", preview)

        # 7) Vorschau-Screenshot (Admin-Leiste ausgeblendet, keine Zugangsdaten sichtbar)
        await page.goto(preview, wait_until="load")
        await page.add_style_tag(content="#wpadminbar{display:none!important} html{margin-top:0!important}")
        for sel in ["text=Nur essenzielle Cookies akzeptieren", "text=Ich akzeptiere alle"]:
            try:
                await page.locator(sel).first.click(timeout=3000); break
            except Exception:
                pass
        await page.wait_for_timeout(2500)
        await page.screenshot(path=str(DIST / "wp-vorschau-oben.png"))
        h = await page.evaluate("document.body.scrollHeight"); y = 0
        while y < h:
            await page.evaluate(f"window.scrollTo({{top:{y},behavior:'instant'}})"); await page.wait_for_timeout(120); y += 500
            h = await page.evaluate("document.body.scrollHeight")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(DIST / "wp-vorschau-komplett.png"), full_page=True)
        (DIST / "wp-page.json").write_text(json.dumps({"id": post_id, "slug": pg["slug"], "status": pg["status"], "edit": f"{BASE}/wp-admin/post.php?post={post_id}&action=elementor", "preview": preview}, indent=2))
        print("fertig.")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
