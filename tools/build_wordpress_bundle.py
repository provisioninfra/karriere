#!/usr/bin/env python3
"""
Baut aus karriere/index.html, assets/css/style.css und assets/js/main.js
einen einzelnen HTML-Block für ein Elementor-HTML-Widget.

- Asset-Pfade (assets/img/…) werden durch Mediathek-URLs ersetzt
  (Mapping aus tools/wp-media-map.json, erzeugt vom Upload-Skript).
- Das Unlock-Icon (SVG) wird als Data-URI eingebettet, weil WordPress
  SVG-Uploads standardmäßig blockiert.
- Poppins kommt aus der auf provision-infra.de bereits vorhandenen,
  selbst gehosteten Elementor-Google-Fonts-Datei.

Aufruf:  python3 tools/build_wordpress_bundle.py [--map tools/wp-media-map.json] [--out dist/karriere-wordpress.html]
"""
import argparse, base64, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "karriere"
POPPINS_CSS = "https://provision-infra.de/wp-content/uploads/elementor/google-fonts/css/poppins.css"


def build(media_map: dict) -> str:
    html = (SRC / "index.html").read_text(encoding="utf-8")
    css = (SRC / "assets/css/style.css").read_text(encoding="utf-8")
    js = (SRC / "assets/js/main.js").read_text(encoding="utf-8")

    # --- CSS: Fonts aus der Site, Bilder aus der Mediathek, SVG inline ---
    css = re.sub(r"@font-face\{[^}]*\}\n?", "", css)  # eigene @font-face raus
    svg = (SRC / "assets/img/button-unlocked.svg").read_bytes()
    data_uri = "data:image/svg+xml;base64," + base64.b64encode(svg).decode()
    css = css.replace('url("../img/button-unlocked.svg")', f'url("{data_uri}")')
    for name, url in media_map.items():
        css = css.replace(f'url("../img/{name}")', f'url("{url}")')
    leftover = re.findall(r'url\("\.\./img/([^"]+)"\)', css)
    if leftover:
        sys.exit(f"Nicht gemappte Bilder im CSS: {sorted(set(leftover))}")

    # --- HTML: nur den Body-Inhalt übernehmen ---
    m = re.search(r"<body[^>]*>(.*)</body>", html, flags=re.S)
    body = m.group(1)
    body = re.sub(r'\s*<script src="assets/js/main.js" defer></script>\s*', "\n", body)
    for name, url in media_map.items():
        body = body.replace(f'src="assets/img/{name}"', f'src="{url}"')
    leftover = re.findall(r'src="assets/img/([^"]+)"', body)
    if leftover:
        sys.exit(f"Nicht gemappte Bilder im HTML: {sorted(set(leftover))}")

    # SVG-Sprite auflösen: jedes <use href="#id"> durch den Symbol-Inhalt ersetzen.
    # Grund: In WordPress/Elementor gehen Sprite-Referenzen verloren (Symbole werden
    # nicht gerendert); eingebettete Pfade funktionieren überall.
    sprite = re.search(r'<svg xmlns="http://www.w3.org/2000/svg" class="svg-sprite" aria-hidden="true">(.*?)</svg>', body, flags=re.S)
    symbols = {}
    if sprite:
        for m in re.finditer(r'<symbol id="([^"]+)" viewBox="([^"]+)">(.*?)</symbol>', sprite.group(1), flags=re.S):
            symbols[m.group(1)] = (m.group(2), m.group(3).strip())
        body = body.replace(sprite.group(0), "")
    def inline_use(m):
        attrs, sid = m.group(1), m.group(2)
        if sid not in symbols:
            sys.exit(f"Unbekanntes Symbol: #{sid}")
        vb, inner = symbols[sid]
        if "viewBox" not in attrs:
            attrs += f' viewBox="{vb}"'
        return f"<svg{attrs}>{inner}</svg>"
    body = re.sub(r'<svg([^>]*)><use href="#([^"]+)"/></svg>', inline_use, body)
    if "<use " in body:
        sys.exit("Es sind noch <use>-Referenzen übrig.")

    # JSON-LD aus dem Head mitnehmen (JobPosting-Schema)
    ld = re.search(r'<script type="application/ld\+json">.*?</script>', html, flags=re.S)
    ld_block = ld.group(0) if ld else ""

    out = []
    out.append("<!-- ProVision Infra – Karriereseite (Elementor-HTML-Widget). Quelle: Repo provisioninfra/karriere -->")
    out.append(f'<link rel="stylesheet" href="{POPPINS_CSS}">')
    out.append("<style>\n" + css + "\n</style>")
    out.append(ld_block)
    out.append(body.strip())
    out.append("<script>\n" + js + "\n</script>")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default=str(ROOT / "tools/wp-media-map.json"))
    ap.add_argument("--out", default=str(ROOT / "dist/karriere-wordpress.html"))
    a = ap.parse_args()
    media_map = json.loads(pathlib.Path(a.map).read_text(encoding="utf-8")) if pathlib.Path(a.map).exists() else {}
    result = build(media_map)
    outp = pathlib.Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(result, encoding="utf-8")
    print(f"geschrieben: {outp} ({len(result.encode('utf-8'))/1024:.0f} KB)")


if __name__ == "__main__":
    main()
