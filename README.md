# eifelpunkt.de Hugo Automation

Automatisiertes Hugo-Blogsystem fuer `eifelpunkt.de` mit Fokus auf:

- Theme `pehtheme-hugo`
- Blog-Authority fuer technologische Entwicklung in der Eifel
- 365-Tage-Redaktionsplan fuer regionale Technologie- und Digitalisierungsthemen
- Daily-Post-Generierung per OpenAI (`gpt-4o`)
- Optionaler Bildgenerierung (`gpt-image-1`) inkl. Alt-Text
- Build + optionales FTP-Deploy + GitHub Pages Workflow
- Redirect-Rettung alter URLs via `static/_redirects`

## Wichtige Dateien

- `hugo.toml`: Site- und Theme-Konfiguration
- `layouts/_default/home.html`: Startseite mit Featured + Neueste Beitraege
- `data/redaktionsplan-365.csv`: 365 Tages-Themen
- `planung/redaktionsplan-365.md`: lesbare Planung
- `scripts/build_editorial_plan.py`: Plan-Generator
- `scripts/generate_daily_post.py`: Daily AI Content + Build + optional FTP
- `scripts/generate_redirects.py`: CSV -> `_redirects`
- `.github/workflows/daily-content.yml`: taegliche Content-Automation
- `.github/workflows/deploy-pages.yml`: Build + Deployment auf GitHub Pages

## Lokal starten

```bash
pip install -r requirements.txt
python scripts/build_editorial_plan.py --start-date 2026-03-27 --days 365
python scripts/generate_redirects.py
hugo server -D -F
```

## Daily Post erzeugen

```bash
python scripts/generate_daily_post.py --publish-date 2026-03-27
```

Hinweis: Hugo blendet Beitraege mit zukuenftigem Datum/Uhrzeit standardmaessig aus.
Mit `hugo server -D -F` siehst du auch geplante Posts in der lokalen Vorschau.

Bildlogik:
- zuerst relevantes Bild via Apify Actor (`APIFY_API_TOKEN`, optional `APIFY_ACTOR_ID`)
- bei Prompt-basierten Apify-Actors zusaetzlich:
  - `APIFY_GOOGLE_API_KEY`
  - `APIFY_NEGATIVE_PROMPT`
  - `APIFY_NUMBER_OF_IMAGES`
  - `APIFY_DEMO_MODE`
  - `APIFY_IMAGE_PROMPT_PREFIX`
  - `APIFY_RESOLUTION` (`1K`, `1.5K`, `2K`, `4K`)
  - `APIFY_STYLE` (z. B. `photorealistic`, `cinematic`)
- falls Apify kein Bild liefert: Fallback auf `gpt-image-1`

Optional FTP:

```bash
set DEPLOY_TARGET=ftp
python scripts/generate_daily_post.py --publish-date 2026-03-27 --deploy-target ftp
```
