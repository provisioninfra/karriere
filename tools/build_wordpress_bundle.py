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



# --- Selektor-Präfix: Alle eigenen Regeln bekommen den Wrapper "#pk-karriere" vorangestellt.
# Grund: WordPress/Elementor laden eigene Stylesheets (z. B. Kit-Regel ".elementor-kit-8 a{color:#FBC91B}"),
# deren Spezifität Klassenselektoren der Seite schlägt. Mit ID-Präfix gewinnen die Seitenregeln immer;
# die Rangfolge der eigenen Regeln untereinander bleibt erhalten (alle +1 ID).
_KEEP = re.compile(r"^(:root|html|body|\*)")


def _split_selectors(sel: str) -> list:
    parts, buf, depth, quote = [], "", 0, None
    for ch in sel:
        if quote:
            buf += ch
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    parts.append(buf)
    return [p.strip() for p in parts if p.strip()]


def prefix_selectors(css: str, prefix: str) -> str:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out, i, n = [], 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j == -1:
            out.append(css[i:])
            break
        head = css[i:j]
        k = head.rfind(";")  # blocklose Anweisungen (z. B. @import ...;) unverändert
        if k != -1:
            out.append(head[: k + 1])
            head = head[k + 1:]
        depth, m = 0, j
        while m < n:
            if css[m] == "{":
                depth += 1
            elif css[m] == "}":
                depth -= 1
                if depth == 0:
                    break
            m += 1
        inner = css[j + 1:m]
        sel = head.strip()
        lead = head[: len(head) - len(head.lstrip())]
        if sel.startswith("@"):
            name = sel.split("(")[0].split()[0].lower()
            if name in ("@media", "@supports", "@container", "@layer", "@document"):
                out.append(head + "{" + prefix_selectors(inner, prefix) + "}")
            else:  # @font-face, @keyframes, @page: unverändert
                out.append(head + "{" + inner + "}")
        else:
            new_sel = ",".join(s if _KEEP.match(s) else f"{prefix} {s}" for s in _split_selectors(sel))
            out.append(lead + new_sel + "{" + inner + "}")
        i = m + 1
    return "".join(out)


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
    css = prefix_selectors(css, "#pk-karriere")
    if "#pk-karriere" not in css or "#pk-karriere :root" in css or "#pk-karriere body" in css:
        sys.exit("Selektor-Präfix fehlgeschlagen.")

    # --- HTML: nur den Body-Inhalt übernehmen ---
    m = re.search(r"<body[^>]*>(.*)</body>", html, flags=re.S)
    body = m.group(1)
    body = re.sub(r'\s*<script src="assets/js/main.js" defer></script>\s*', "\n", body)
    for name, url in media_map.items():
        body = body.replace(f'src="assets/img/{name}"', f'src="{url}"')
    leftover = re.findall(r'src="assets/img/([^"]+)"', body)
    if leftover:
        sys.exit(f"Nicht gemappte Bilder im HTML: {sorted(set(leftover))}")

    # Entwurfs-Sektionen (class is-draft, z. B. Team-Zitate ohne Inhalt) nicht ausliefern:
    # unsichtbarer Platzhaltertext gehört nicht in den Quelltext der Live-Seite.
    body = re.sub(r'<section class="section is-draft"[^>]*>.*?(?=<!-- =+ )', "", body, flags=re.S)
    if "is-draft" in body:
        sys.exit("Entwurfs-Sektion konnte nicht entfernt werden.")

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
    out.append("<!-- ProVision Infra: Karriereseite (Elementor-HTML-Widget) -->")
    out.append(f'<link rel="stylesheet" href="{POPPINS_CSS}">')
    if "glow-ellipse-5.png" in media_map:  # Hero-Glow ist das LCP-Element: vorladen
        out.append(f'<link rel="preload" as="image" href="{media_map["glow-ellipse-5.png"]}">')
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
