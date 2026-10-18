# ProVision Infra – Karriereseite (`/karriere`)

Statische Unterseite für **provision-infra.de/karriere/** im exakten Design der Hauptseite
(Elementor-Kit „ProVision“: Poppins, Navy `#000D30`, Gelb `#FBC91B`, Glass-Cards, Glow-Hintergründe,
Pill-Header, Unlock-Button, Scroll-Animationen, Counter, Testimonial-Karussell, FAQ-Akkordeon).

Inhalt, Aufbau und Struktur orientieren sich an <https://muenchener-marketing-gruppe.de/karriere/>.

## Struktur

```
karriere/
├── index.html            # die Karriereseite
└── assets/
    ├── css/style.css     # Design-System + Komponenten + Breakpoints (1440 / 1280 / 1024 / 767)
    ├── js/main.js        # Animationen, Counter, Menü, Karussell, FAQ, Stellen-Filter
    ├── fonts/            # Poppins 400/500/600/700 (selbst gehostet, DSGVO-konform)
    └── img/              # Logo, Favicons, Glow-Grafiken, Icons (aus der Hauptseite übernommen)
index.html                # leitet auf /karriere/ weiter (nur für lokale Vorschau / Hosting im Root)
```

## Deployment

**Variante A – statisch neben WordPress:** Den Ordner `karriere/` per FTP/SFTP in das Web-Root
der Hauptseite legen (gleiche Ebene wie `wp-content/`). Die Seite ist dann unter
`https://provision-infra.de/karriere/` erreichbar. WordPress-Permalinks greifen nicht, weil der
Webserver vorhandene Ordner zuerst ausliefert.

**Variante B – in WordPress/Elementor:** Neue Seite „Karriere“ (Slug `karriere`) mit Vorlage
„Elementor Canvas“ anlegen, ein HTML-Widget einfügen und den Inhalt von `karriere/index.html`
(Body) hineinkopieren. CSS/JS/Bilder vorher unter `wp-content/uploads/karriere/` hochladen und die
Pfade `assets/…` entsprechend anpassen.

Lokale Vorschau: `cd karriere && python3 -m http.server 8080` → <http://localhost:8080/>

## Sicherheit und Datenschutz

- Die Seite lädt keine fremden Skripte. Einzige externe Ressourcen sind die beiden ProvenExpert-Siegel
  (`images.provenexpert.com`), wie auf der Hauptseite. Beim Laden wird die IP-Adresse des Besuchers an
  ProvenExpert übertragen; die Bilder werden mit `referrerpolicy="no-referrer"` eingebunden. Wer das vermeiden
  will, bindet die Siegel über den Cookie-Manager (Borlabs) ein oder entfernt die beiden `<img>`-Tags.
- Externe Links öffnen mit `rel="noopener noreferrer"`; die Seite setzt `referrer: strict-origin-when-cross-origin`.
- Das Skript nutzt kein `innerHTML`, `eval` oder externe Eingaben. Formulare gibt es keine; Bewerbungen laufen
  über `mailto:`-Links an die bereits im Impressum veröffentlichte Adresse.
- `tools/wp_publish_draft.py` liest Zugangsdaten ausschließlich aus Umgebungsvariablen und schreibt sie nirgends
  hin. `dist/`, `__pycache__/` und `.env*` sind per `.gitignore` ausgeschlossen.
- Eine Content-Security-Policy lässt sich für die statische Variante nur serverseitig setzen (z. B. in der
  `.htaccess`); innerhalb von WordPress/Elementor greifen die Regeln der Hauptseite.

## Vor dem Livegang prüfen

- **Stellentexte** (3 Stellen: Servicetechniker, IT-Projekttechniker, Kundenberater) sind Vorschläge
  auf Basis des Geschäftsmodells – Aufgaben, Anforderungen und Benefits bitte fachlich prüfen.
- **Benefits-Sektion** ebenfalls abgleichen (z. B. Firmenwagen, Homeoffice, Arbeitszeiten).
- **Team-Stimmen** sind als Platzhalter markiert – echte Zitate und Namen eintragen.
- **Bewerbungs-E-Mail**: aktuell `info@provision-infra.de` (aus dem Impressum). Bei Bedarf auf eine
  eigene Adresse wie `bewerbung@provision-infra.de` ändern (`mailto:`-Links in `index.html`).
- **JobPosting-Schema** (JSON-LD im `<head>`): `validThrough`-Datum regelmäßig verlängern.
