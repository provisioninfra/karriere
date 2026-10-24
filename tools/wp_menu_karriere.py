#!/usr/bin/env python3
"""
Fügt den Menüpunkt „Komm in unser Team“ (Link auf /karriere/) in die
WordPress-Menüs ein, die im Header der Startseite, von /zutrittssystem und
/kamerasysteme verwendet werden (Elementor-Nav-Menu-Widget).

Modi:
  --list      nur Menüs und Einträge anzeigen (nichts ändern)
  --add       Menüpunkt in die Zielmenüs einfügen (idempotent), IDs nach
              dist/wp-menu-items.json schreiben
  --rollback  die in dist/wp-menu-items.json gespeicherten Einträge löschen

Zugangsdaten nur über WP_USER / WP_PASS (werden nicht geloggt).
Optional: WP_URL, CHROME_PATH, MENU_LABEL, MENU_URL.
"""
import asyncio, json, os, pathlib, re, sys

from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
STATE = DIST / "wp-menu-items.json"
BASE = os.environ.get("WP_URL", "https://provision-infra.de").rstrip("/")
USER = os.environ.get("WP_USER")
PASS = os.environ.get("WP_PASS")
CHROME = os.environ.get("CHROME_PATH")
LABEL = os.environ.get("MENU_LABEL", "Komm in unser Team")
URL = os.environ.get("MENU_URL", f"{BASE}/karriere/")

# Zielmenüs werden über vorhandene Einträge erkannt (Titel, wie sie im Header stehen)
TARGET_HINTS = {
    "Startseite": ["Mit digitalen Schlüsseln Kosten sparen"],
    "Zutrittssystem": ["Zur Startseite"],
    "Kamerasysteme": ["Durch Videoüberwachung teure Schäden ver"],
}


async def rest(ctx, method, url, retries=6, **kw):
    for i in range(retries):
        r = await getattr(ctx.request, method)(url, **kw)
        if r.status not in (429, 503):
            return r
        wait = 15 * (i + 1)
        print(f"  Ratenlimit ({r.status}), warte {wait}s ...", flush=True)
        await asyncio.sleep(wait)
    return r


async def login(p):
    browser = await p.chromium.launch(**({"executable_path": CHROME} if CHROME else {}))
    ctx = await browser.new_context(viewport={"width": 1280, "height": 800}, locale="de-DE")
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
    return browser, ctx, {"X-WP-Nonce": nonce}


def plain(s):
    return re.sub(r"<[^>]+>", "", s or "").replace("&amp;", "&").strip()


async def load_menus(ctx, H):
    r = await rest(ctx, "get", f"{BASE}/wp-json/wp/v2/menus?per_page=100", headers=H)
    if r.status != 200:
        sys.exit(f"Menüs nicht lesbar: {r.status} {(await r.text())[:200]}")
    menus = await r.json()
    out = []
    for m in menus:
        r = await rest(ctx, "get", f"{BASE}/wp-json/wp/v2/menu-items?menus={m['id']}&per_page=100&context=edit", headers=H)
        items = await r.json() if r.status == 200 else []
        items.sort(key=lambda x: x.get("menu_order", 0))
        out.append({"id": m["id"], "name": m["name"], "items": [{"id": it["id"], "title": plain(it["title"]["rendered"]), "url": it.get("url"), "order": it.get("menu_order")} for it in items]})
    return out


def find_targets(menus):
    targets = {}
    for label, hints in TARGET_HINTS.items():
        for m in menus:
            titles = " | ".join(it["title"] for it in m["items"])
            if all(h in titles for h in hints):
                targets[label] = m
                break
    return targets


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--list"
    if not USER or not PASS:
        sys.exit("WP_USER und WP_PASS müssen gesetzt sein.")
    DIST.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser, ctx, H = await login(p)

        if mode == "--rollback":
            state = json.loads(STATE.read_text()) if STATE.exists() else []
            for s in state:
                r = await rest(ctx, "delete", f"{BASE}/wp-json/wp/v2/menu-items/{s['item_id']}?force=true", headers=H)
                print("gelöscht:", s, r.status, flush=True)
            STATE.write_text("[]\n")
            await browser.close()
            return

        menus = await load_menus(ctx, H)
        for m in menus:
            print(f"Menü {m['id']} „{m['name']}“:", [it["title"] for it in m["items"]], flush=True)
        targets = find_targets(menus)
        print("Zielmenüs:", {k: (v["id"], v["name"]) for k, v in targets.items()}, flush=True)
        if mode == "--list":
            await browser.close()
            return

        if mode == "--add":
            missing = [k for k in TARGET_HINTS if k not in targets]
            if missing:
                sys.exit(f"Abbruch: Zielmenü nicht erkannt für {missing}")
            state = json.loads(STATE.read_text()) if STATE.exists() else []
            done_menus = set()
            for label, m in targets.items():
                if m["id"] in done_menus:
                    continue
                done_menus.add(m["id"])
                if any(it["url"] and it["url"].rstrip("/") == URL.rstrip("/") for it in m["items"]):
                    print(f"Menü {m['id']} enthält den Link bereits, übersprungen.", flush=True)
                    continue
                order = max([it["order"] or 0 for it in m["items"]] + [0]) + 1
                r = await rest(ctx, "post", f"{BASE}/wp-json/wp/v2/menu-items", headers=H,
                               data={"title": LABEL, "url": URL, "menus": m["id"], "type": "custom",
                                     "object": "custom", "status": "publish", "menu_order": order, "parent": 0})
                if r.status not in (200, 201):
                    sys.exit(f"Menüpunkt konnte nicht angelegt werden (Menü {m['id']}): {r.status} {(await r.text())[:300]}")
                it = await r.json()
                state.append({"menu_id": m["id"], "menu_name": m["name"], "item_id": it["id"], "title": LABEL, "url": URL})
                STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
                print(f"angelegt: Menü {m['id']} „{m['name']}“ -> Eintrag {it['id']} „{LABEL}“", flush=True)
            await browser.close()
            return
        sys.exit("Unbekannter Modus. --list | --add | --rollback")


if __name__ == "__main__":
    asyncio.run(main())
