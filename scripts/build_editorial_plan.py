#!/usr/bin/env python3
"""Generate a 365-day editorial plan for technology topics in the Eifel."""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


@dataclass(frozen=True)
class PlanEntry:
    publish_date: date
    title: str
    slug: str
    region: str
    audience: str
    it_focus: str
    angle: str
    primary_keyword: str
    secondary_keyword: str
    target_url: str


REGIONS = [
    "Euskirchen",
    "Bad Muenstereifel",
    "Mechernich",
    "Monschau",
    "Schleiden",
    "Nideggen",
    "Pruem",
    "Bitburg",
    "Daun",
    "Gerolstein",
    "Adenau",
    "Mayen",
    "Kall",
    "Nettersheim",
    "Blankenheim",
    "Heimbach",
    "Vulkaneifel",
    "Eifelkreis Bitburg-Pruem",
]

AUDIENCES = [
    "Kommunen",
    "Mittelstand",
    "Startups",
    "Handwerksbetriebe",
    "Schulen und Bildung",
    "Tourismusbetriebe",
    "Energieprojekte",
    "Logistik und Mobilitaet",
    "Vereine und Ehrenamt",
    "regionale Netzwerke",
    "Gesundheitseinrichtungen",
    "Industriebetriebe",
    "Buergerinitiativen",
    "Co-Working-Communities",
]

IT_FOCUSES = [
    "Glasfaserausbau",
    "5G- und Campusnetze",
    "IT-Sicherheit und Incident Response",
    "Cloud-Migration",
    "KI-Anwendungen im Alltag",
    "Open-Data-Initiativen",
    "Smart-City-Technologien",
    "Cyberabwehr gegen Phishing",
    "Datenschutz nach DSGVO",
    "digitale Verwaltungsprozesse",
    "Standortvernetzung",
    "digitale Bildung",
    "digitale Zwillinge",
    "IoT-Sensorik",
    "Energie-Monitoring",
    "Telemedizinische Infrastruktur",
    "Low-Code-Automatisierung",
    "Geo- und Umweltdaten",
    "E-Government-Schnittstellen",
    "Rechenzentrum-Modernisierung",
]

ANGLES = [
    "Praxischeck",
    "Umsetzungsfahrplan",
    "Kosten-Nutzen-Betrachtung",
    "Foerdermittel und Finanzierung",
    "Sicherheits- und Datenschutzperspektive",
    "Personal- und Fachkraefteblick",
    "Standortentwicklung",
    "Resilienz und Krisenvorsorge",
    "Nachhaltigkeit",
    "Kooperationsmodelle",
    "Datenstrategie",
    "Betriebsorganisation",
]

PRIMARY_KEYWORDS = [
    "Technologie Eifel",
    "Digitalisierung Eifel",
    "Innovation Eifel",
]

SECONDARY_KEYWORDS = [
    "Breitbandausbau Eifel",
    "Smart Region Eifel",
    "IT-Standort Eifel",
    "Digitale Infrastruktur Eifel",
]

TITLE_PATTERNS = [
    "{it_focus} in {region}: Was {audience} jetzt wissen muessen",
    "{region}: {it_focus} als Hebel fuer {audience}",
    "{audience} in {region}: Leitfaden fuer {it_focus}",
    "Technologie-Update {region}: {it_focus} im Praxischeck fuer {audience}",
    "{it_focus} in der Region {region}: Chancen, Risiken und naechste Schritte fuer {audience}",
    "{region} im Fokus: Wie {audience} mit {it_focus} resilienter werden",
    "{it_focus} in {region}: {angle} fuer {audience}",
    "{region}: Einstieg von {audience} in {it_focus}",
    "{audience} und {it_focus} in {region}: 7 konkrete Handlungsfelder",
    "Standortfaktor {region}: Warum {it_focus} fuer {audience} strategisch ist",
]


def slugify(value: str) -> str:
    lowered = value.lower().strip()
    lowered = (
        lowered.replace("\u00e4", "ae")
        .replace("\u00f6", "oe")
        .replace("\u00fc", "ue")
        .replace("\u00df", "ss")
    )
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered).strip("-")
    return lowered


def unique_slug(candidate: str, used: set[str]) -> str:
    if candidate not in used:
        used.add(candidate)
        return candidate

    i = 2
    while True:
        test = f"{candidate}-{i}"
        if test not in used:
            used.add(test)
            return test
        i += 1


def build_entries(start_date: date, days: int) -> list[PlanEntry]:
    entries: list[PlanEntry] = []
    used_slugs: set[str] = set()

    for i in range(days):
        publish_date = start_date + timedelta(days=i)
        region = REGIONS[(i * 3 + i // 17) % len(REGIONS)]
        audience = AUDIENCES[(i * 5 + i // 11) % len(AUDIENCES)]
        it_focus = IT_FOCUSES[(i * 7 + i // 13) % len(IT_FOCUSES)]
        angle = ANGLES[(i * 11 + i // 19) % len(ANGLES)]
        primary_keyword = PRIMARY_KEYWORDS[i % len(PRIMARY_KEYWORDS)]
        secondary_keyword = SECONDARY_KEYWORDS[(i * 3) % len(SECONDARY_KEYWORDS)]
        pattern = TITLE_PATTERNS[(i * 2 + i // 9) % len(TITLE_PATTERNS)]

        title = pattern.format(
            region=region,
            audience=audience,
            it_focus=it_focus,
            angle=angle,
        )
        title = title[:1].upper() + title[1:]

        # Slugs are intentionally date-free for stable evergreen URLs.
        base_slug = slugify(f"{region} {it_focus} {audience} {angle}")
        slug = unique_slug(base_slug, used_slugs)
        target_url = f"/blog/{slug}/"

        entries.append(
            PlanEntry(
                publish_date=publish_date,
                title=title,
                slug=slug,
                region=region,
                audience=audience,
                it_focus=it_focus,
                angle=angle,
                primary_keyword=primary_keyword,
                secondary_keyword=secondary_keyword,
                target_url=target_url,
            )
        )

    return entries


def write_csv(entries: list[PlanEntry], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "date",
                "title",
                "slug",
                "region",
                "healthcare_focus",
                "it_focus",
                "angle",
                "primary_keyword",
                "secondary_keyword",
                "target_url",
            ]
        )
        for entry in entries:
            writer.writerow(
                [
                    entry.publish_date.isoformat(),
                    entry.title,
                    entry.slug,
                    entry.region,
                    entry.audience,
                    entry.it_focus,
                    entry.angle,
                    entry.primary_keyword,
                    entry.secondary_keyword,
                    entry.target_url,
                ]
            )


def write_markdown(entries: list[PlanEntry], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Redaktionsplan 365 Tage\n\n")
        handle.write(
            "Taeglicher Themenplan mit bewusst abwechslungsreichen Perspektiven fuer "
            "`Technologie Eifel`, `Digitalisierung Eifel` und `Innovation Eifel`.\n\n"
        )
        handle.write("| Datum | Titel | Themenwinkel |\n")
        handle.write("|---|---|---|\n")
        for entry in entries:
            safe_title = entry.title.replace("|", "\\|")
            safe_angle = entry.angle.replace("|", "\\|")
            handle.write(
                f"| {entry.publish_date.isoformat()} | {safe_title} | {safe_angle} |\n"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a 365-day editorial plan")
    parser.add_argument("--start-date", default=date.today().isoformat(), help="Start date YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=365, help="Number of daily entries")
    parser.add_argument("--output-csv", default="data/redaktionsplan-365.csv", help="CSV output path")
    parser.add_argument("--output-md", default="planung/redaktionsplan-365.md", help="Markdown output path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start_date = date.fromisoformat(args.start_date)
    entries = build_entries(start_date=start_date, days=args.days)
    write_csv(entries, Path(args.output_csv))
    write_markdown(entries, Path(args.output_md))
    print(f"Wrote {len(entries)} plan entries to {args.output_csv} and {args.output_md}")


if __name__ == "__main__":
    main()
