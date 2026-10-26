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

**Hinweis zu Icons in WordPress:** Das Child-Theme der Hauptseite benennt per `uniquifySvgIds()` alle
SVG-Symbol-IDs um; Sprite-Verweise (`<use href="#…">`) laufen dort ins Leere. `tools/build_wordpress_bundle.py`
löst den Sprite deshalb auf und bettet jedes Icon direkt ein.

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


## Team-Zitate

Die Sektion „Das sagt das Team“ (`#team`) ist mit der Klasse `is-draft` und dem Attribut `hidden` ausgeblendet, weil noch keine echten Zitate vorliegen. Zum Aktivieren beide entfernen und die drei Platzhalter in `karriere/index.html` durch echte Zitate ersetzen.


## Header-Menü der Hauptseite

`tools/wp_menu_karriere.py` pflegt den Reiter „Komm in unser Team“ in den WordPress-Menüs der Header
(Startseite: Menü 6 „Main“, /zutrittssystem: Menü 15 „Secandary Menu“, /kamerasysteme: Menü 17).
Damit die Leiste auf allen Bildschirmbreiten einzeilig bleibt, sind die weiteren Punkte unter einem
Aufklappmenü „Mehr“ zusammengefasst (Elementor-Nav-Menu-Widget zeigt Untermenüs als Dropdown).

- `--list` zeigt die Menüs, `--add` legt den Reiter an, `--group` gruppiert, `--ungroup` und `--rollback`
  nehmen die Änderungen anhand von `tools/wp-menu-backup.json` und `tools/wp-menu-items.json` zurück.
- Angelegte Einträge: 4558, 4559, 4560 („Komm in unser Team“), 4568 und 4569 („Mehr“).
- Der Hoster-Cache (Varnish, lange Haltezeit) wird von Menüänderungen nicht geleert; nach Änderungen
  Server-Cache und WP-Rocket-Cache leeren.
