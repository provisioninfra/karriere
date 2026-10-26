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
  --group     Header-Menüs ordnen: erste Punkte nebeneinander, Rest als
              Aufklappmenü „Mehr“ (Sicherung nach dist/wp-menu-backup.json)
  --ungroup   Gruppierung anhand der Sicherung wieder aufheben

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
# Gruppierung (--group): welche Punkte bleiben nebeneinander, welche wandern ins Aufklappmenü
GROUP_LABEL = os.environ.get("GROUP_LABEL", "Mehr")
GROUP_URL = "#mehr"  # nicht existierender Anker: kein Sprung, kein Scrollen
GROUP_PLAN = {
    "Startseite": {"inline": ["Mit digitalen Schlüsseln Kosten sparen", "So arbeiten wir zusammen", "Komm in unser Team"],
                   "dropdown": ["Über uns", "FAQ"]},
    "Kamerasysteme": {"inline": ["Durch Videoüberwachung teure Schäden verhindern", "Komm in unser Team"],
                      "dropdown": ["So arbeiten wir zusammen", "Über uns", "FAQ"]},
}
BACKUP = DIST / "wp-menu-backup.json"

TARGET_HINTS = {
    "Startseite": ["Mit digitalen Schlüsseln Kosten sparen"],
    "Zutrittssystem": ["Zur Startseite"],
    "Kamerasysteme": ["Durch Videoüberwachung teure Schäden ver"],
}


async def rest(ctx, method, url, retries=12, **kw):
    """REST-Aufruf mit Backoff bei Ratenlimit (429/503/502/504) oder HTML-Antwort statt JSON (Hoster-Drossel)."""
    r = None
    for i in range(retries):
        r = await getattr(ctx.request, method)(url, **kw)
        ctype = (r.headers.get("content-type") or "").lower()
        json_expected = "/wp-json/" in url  # admin-ajax (rest-nonce) antwortet als text/html
        if r.status not in (429, 502, 503, 504) and not (json_expected and r.status == 200 and "json" not in ctype and "text/plain" not in ctype):
            return r
        wait = 60
        ra = r.headers.get("retry-after")
        if i == 0:
            print(f"  Antwort-Header bei {r.status}: {sorted(k for k in r.headers.keys() if k.lower() not in ('set-cookie',))}", flush=True)
        if ra and ra.isdigit():
            wait = max(wait, min(int(ra), 300))
        print(f"  Ratenlimit/Störung ({r.status}, {ctype[:20]}), warte {wait}s ...", flush=True)
        await asyncio.sleep(wait)
    return r


async def login(p):
    browser = await p.chromium.launch(**({"executable_path": CHROME} if CHROME else {}))
    ctx = await browser.new_context(viewport={"width": 1280, "height": 800}, locale="de-DE")
    page = await ctx.new_page()
    # redirect_to=Startseite: das Dashboard würde Dutzende Hintergrund-Anfragen auslösen und die Drossel des Hosters aktivieren
    await page.goto(f"{BASE}/wp-login.php?redirect_to={BASE}/", wait_until="domcontentloaded")
    await page.fill("#user_login", USER)
    await page.fill("#user_pass", PASS)
    await page.click("#wp-submit")
    await page.wait_for_load_state("load")
    await page.wait_for_timeout(1500)
    if "wp-login.php" in page.url:
        sys.exit("Login fehlgeschlagen.")
    await page.goto("about:blank")
    print(f"angemeldet, warte {SETTLE}s, bis die Anfrage-Drossel zur Ruhe kommt ...", flush=True)
    await asyncio.sleep(SETTLE)
    r = await rest(ctx, "get", f"{BASE}/wp-admin/admin-ajax.php?action=rest-nonce")
    nonce = (await r.text()).strip()
    if not re.fullmatch(r"[0-9a-f]{10}", nonce):
        sys.exit("Keine REST-Nonce erhalten.")
    return browser, ctx, {"X-WP-Nonce": nonce}


def plain(s):
    return re.sub(r"<[^>]+>", "", s or "").replace("&amp;", "&").strip()


PAUSE = 30   # Sekunden zwischen API-Aufrufen, damit die Drossel des Hosters nicht anspringt
SETTLE = 60  # Sekunden Ruhe nach dem Login


async def load_menus(ctx, H):
    await asyncio.sleep(PAUSE)
    r = await rest(ctx, "get", f"{BASE}/wp-json/wp/v2/menus?per_page=100", headers=H)
    if r.status != 200:
        sys.exit(f"Menüs nicht lesbar: {r.status} {(await r.text())[:200]}")
    menus = await r.json()
    items = []
    page = 1
    while True:
        await asyncio.sleep(PAUSE)
        r = await rest(ctx, "get", f"{BASE}/wp-json/wp/v2/menu-items?per_page=100&page={page}", headers=H)
        if r.status != 200:
            sys.exit(f"Menüeinträge nicht lesbar: {r.status} {(await r.text())[:200]}")
        batch = await r.json()
        items += batch
        if len(batch) < 100:
            break
        page += 1
    out = []
    for m in menus:
        mine = [it for it in items if m["id"] in (it.get("menus") if isinstance(it.get("menus"), list) else [it.get("menus")])]
        mine.sort(key=lambda x: x.get("menu_order", 0))
        out.append({"id": m["id"], "name": m["name"], "items": [{"id": it["id"], "title": plain(it["title"]["rendered"]), "url": it.get("url"), "order": it.get("menu_order"), "parent": it.get("parent", 0)} for it in mine]})
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
                await asyncio.sleep(PAUSE)
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

        if mode == "--group":
            backup = json.loads(BACKUP.read_text()) if BACKUP.exists() else {}
            for label, plan in GROUP_PLAN.items():
                m = targets.get(label)
                if not m:
                    sys.exit(f"Abbruch: Zielmenü für {label} nicht erkannt")
                by_title = {it["title"]: it for it in m["items"]}
                missing = [t for t in plan["inline"] + plan["dropdown"] if t not in by_title]
                if missing:
                    sys.exit(f"Abbruch: Einträge fehlen in Menü {m['id']}: {missing}")
                if str(m["id"]) not in backup:
                    backup[str(m["id"])] = [{"id": it["id"], "parent": it["parent"], "order": it["order"]} for it in m["items"]]
                    BACKUP.write_text(json.dumps(backup, indent=2, ensure_ascii=False) + "\n")
                parent = by_title.get(GROUP_LABEL)
                if parent:
                    print(f"Menü {m['id']}: „{GROUP_LABEL}“ existiert bereits (ID {parent['id']}), wird wiederverwendet.", flush=True)
                    parent_id = parent["id"]
                else:
                    await asyncio.sleep(PAUSE)
                    r = await rest(ctx, "post", f"{BASE}/wp-json/wp/v2/menu-items", headers=H,
                                   data={"title": GROUP_LABEL, "url": GROUP_URL, "menus": m["id"], "type": "custom", "object": "custom",
                                         "status": "publish", "menu_order": len(plan["inline"]) + 1, "parent": 0})
                    if r.status not in (200, 201):
                        sys.exit(f"„{GROUP_LABEL}“ konnte nicht angelegt werden (Menü {m['id']}): {r.status} {(await r.text())[:300]}")
                    parent_id = (await r.json())["id"]
                    print(f"Menü {m['id']}: Aufklappmenü „{GROUP_LABEL}“ angelegt (ID {parent_id})", flush=True)
                order = 1
                updates = []
                for t in plan["inline"]:
                    updates.append((by_title[t], 0, order)); order += 1
                order += 1  # Platz für „Mehr“
                for t in plan["dropdown"]:
                    updates.append((by_title[t], parent_id, order)); order += 1
                for it, par, order_ in updates:
                    if it["parent"] == par and it["order"] == order_:
                        continue
                    await asyncio.sleep(PAUSE)
                    r = await rest(ctx, "post", f"{BASE}/wp-json/wp/v2/menu-items/{it['id']}", headers=H, data={"parent": par, "menu_order": order_})
                    if r.status != 200:
                        sys.exit(f"Eintrag {it['id']} „{it['title']}“ konnte nicht geändert werden: {r.status} {(await r.text())[:300]}")
                    print(f"  „{it['title']}“ -> {'unter „' + GROUP_LABEL + '“' if par else 'oben'}, Position {order_}", flush=True)
            print("Gruppierung abgeschlossen.", flush=True)
            await browser.close()
            return

        if mode == "--ungroup":
            backup = json.loads(BACKUP.read_text()) if BACKUP.exists() else {}
            if not backup:
                sys.exit("Keine Sicherung vorhanden.")
            for m in menus:
                saved = backup.get(str(m["id"]))
                if not saved:
                    continue
                for it in m["items"]:
                    if it["title"] == GROUP_LABEL and it["url"] == GROUP_URL:
                        await asyncio.sleep(PAUSE)
                        r = await rest(ctx, "delete", f"{BASE}/wp-json/wp/v2/menu-items/{it['id']}?force=true", headers=H)
                        print(f"Menü {m['id']}: „{GROUP_LABEL}“ gelöscht ({r.status})", flush=True)
                for sv in saved:
                    await asyncio.sleep(PAUSE)
                    r = await rest(ctx, "post", f"{BASE}/wp-json/wp/v2/menu-items/{sv['id']}", headers=H, data={"parent": sv["parent"], "menu_order": sv["order"]})
                    print(f"  Eintrag {sv['id']} zurückgesetzt ({r.status})", flush=True)
            BACKUP.write_text("{}\n")
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
                await asyncio.sleep(PAUSE)
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
        sys.exit("Unbekannter Modus. --list | --add | --rollback | --group | --ungroup")


if __name__ == "__main__":
    asyncio.run(main())
