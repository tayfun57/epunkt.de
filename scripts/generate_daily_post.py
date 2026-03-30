#!/usr/bin/env python3
"""Generate one daily Hugo post via OpenAI and optionally deploy."""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import date
from ftplib import FTP, FTP_TLS, error_perm
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

import requests

try:
    from openai import APIConnectionError, AuthenticationError, OpenAI
except ModuleNotFoundError:  # pragma: no cover - depends on local environment
    OpenAI = None  # type: ignore[assignment]
    AuthenticationError = Exception  # type: ignore[assignment]
    APIConnectionError = Exception  # type: ignore[assignment]

try:
    from PIL import Image, ImageOps, UnidentifiedImageError
except ModuleNotFoundError:  # pragma: no cover - depends on local environment
    Image = None  # type: ignore[assignment]
    ImageOps = None  # type: ignore[assignment]
    UnidentifiedImageError = Exception  # type: ignore[assignment]


ANCHOR_LINK = "[Technologie in der Eifel](/blog/)"
KEYWORDS = ["Technologie Eifel", "Digitalisierung Eifel", "Innovation Eifel"]
PLACEHOLDER_HOSTS = {"via.placeholder.com", "placehold.co", "dummyimage.com"}


@dataclass
class PlanItem:
    publish_date: date
    title: str
    slug: str
    region: str
    healthcare_focus: str
    it_focus: str
    primary_keyword: str
    secondary_keyword: str
    target_url: str


def normalize_slug_no_date(slug: str) -> str:
    cleaned = (slug or "").strip().strip("/")
    cleaned = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", cleaned)
    return cleaned


def yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{escaped}"'


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


def normalize_list(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        cleaned = [str(x).strip() for x in value if str(x).strip()]
        if cleaned:
            return cleaned
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",") if part.strip()]
        if items:
            return items
    return fallback


def normalize_text(value: str) -> str:
    text = (value or "")
    if not text:
        return text

    # Replace common mojibake byte-sequences explicitly.
    byte_mojibake = {
        "\u00c3\u00a4": "ae",
        "\u00c3\u00b6": "oe",
        "\u00c3\u00bc": "ue",
        "\u00c3\u009f": "ss",
        "\u00c3\u0178": "ss",
        "\u00c3\u0084": "Ae",
        "\u00c3\u0096": "Oe",
        "\u00c3\u009c": "Ue",
        "\u00e2\u0080\u0093": "-",
        "\u00e2\u0080\u0094": "-",
        "\u00e2\u0080\u009e": '"',
        "\u00e2\u0080\u009c": '"',
        "\u00e2\u0080\u009d": '"',
        "\u00e2\u0080\u0098": "'",
        "\u00e2\u0080\u0099": "'",
        "\u00c2\u00a0": " ",
        "\u00c2": "",
    }
    for source, target in byte_mojibake.items():
        text = text.replace(source, target)

    # Keep output ASCII-stable to avoid encoding surprises in templates.
    text = (
        text.replace("\u00e4", "ae")
        .replace("\u00f6", "oe")
        .replace("\u00fc", "ue")
        .replace("\u00df", "ss")
        .replace("\u00c4", "Ae")
        .replace("\u00d6", "Oe")
        .replace("\u00dc", "Ue")
    )
    return text


def clean_env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def clean_secret_env(name: str) -> str:
    return clean_env(name).replace("\r", "").replace("\n", "")


def first_non_empty_env(*names: str) -> str:
    for name in names:
        value = clean_env(name)
        if value:
            return value
    return ""


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


def int_from_env(name: str, default: int) -> int:
    raw_value = clean_env(name)
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def save_image_as_webp(image_bytes: bytes, out_path: Path, quality: int) -> None:
    if Image is None or ImageOps is None:
        raise RuntimeError("Python package 'Pillow' fehlt. Bitte: pip install -r requirements.txt")

    safe_quality = clamp(quality, 1, 100)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(BytesIO(image_bytes)) as raw_image:
            image = ImageOps.exif_transpose(raw_image)
            # Keep alpha if available, otherwise normalize to RGB for stable output size.
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            image.save(out_path, format="WEBP", quality=safe_quality, method=6)
    except UnidentifiedImageError as exc:
        raise RuntimeError("Bilddaten konnten nicht als Bild erkannt werden.") from exc


def read_plan(plan_file: Path, publish_date: date) -> PlanItem:
    with plan_file.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("date") != publish_date.isoformat():
                continue
            raw_slug = (row.get("slug") or "").strip() or slugify((row.get("title") or "").strip())
            normalized_slug = normalize_slug_no_date(raw_slug)
            return PlanItem(
                publish_date=publish_date,
                title=(row.get("title") or "").strip(),
                slug=normalized_slug,
                region=(row.get("region") or "Eifel").strip(),
                healthcare_focus=(row.get("healthcare_focus") or "Kommunen").strip(),
                it_focus=(row.get("it_focus") or "Glasfaserausbau").strip(),
                primary_keyword=(row.get("primary_keyword") or "Technologie Eifel").strip(),
                secondary_keyword=(row.get("secondary_keyword") or "Smart Region Eifel").strip(),
                target_url=(row.get("target_url") or "").strip(),
            )
    raise ValueError(f"Kein Redaktionsplan-Eintrag fuer {publish_date.isoformat()} in {plan_file}")


def ensure_internal_link(markdown: str) -> str:
    if ANCHOR_LINK in markdown:
        return markdown
    addition = (
        "\n\n## Umsetzung in der Praxis\n\n"
        "Fuer konkrete Planung, Betrieb und Support vor Ort: "
        f"{ANCHOR_LINK}\n"
    )
    return markdown.rstrip() + addition


def ensure_required_keywords(markdown: str) -> str:
    missing = [kw for kw in KEYWORDS if kw.lower() not in markdown.lower()]
    if not missing:
        return markdown
    suffix = "\n\n" + " ".join(f"{kw}." for kw in missing)
    return markdown.rstrip() + suffix


def build_prompt(item: PlanItem) -> str:
    return f"""
Erstelle einen SEO-optimierten deutschen Blogartikel als JSON.

Kontext:
- Region: {item.region}
- Regionaler Fokus: {item.healthcare_focus}
- IT-Fokus: {item.it_focus}
- Primaer-Keyword: {item.primary_keyword}
- Sekundaer-Keyword: {item.secondary_keyword}

Pflichtregeln:
1) Schreibe sachlich, lokal und praxisnah.
2) Nutze kurze Absaetze, H2/H3-Struktur und eine Liste.
3) Der Text muss die Keywords "Technologie Eifel", "Digitalisierung Eifel" und "Innovation Eifel" natuerlich enthalten.
4) Kein Floskeldeutsch, kein Marketing-Blabla.
5) Der Body darf KEINE Frontmatter enthalten.
6) Thema immer als Mix aus regionalem Eifel-Bezug (Kommune, Infrastruktur, Standortfaktor) und technologischer Entwicklung schreiben.
7) Schreibe als neutraler Fachblog zum Authority-Aufbau, ohne Service-Pitch.
8) Mindestens 700 Wörter soll der Artikel haben, aber nicht mehr als 1100 Wörter.

Gib NUR JSON mit exakt diesen Feldern zurueck:
{{
  "title": "string",
  "description": "string max 155 chars",
  "excerpt": "string max 220 chars",
  "tags": ["string", "..."],
  "categories": ["string", "..."],
  "image_prompt": "string fuer DALL-E Stilmotiv",
  "image_alt": "string Alt-Text auf Deutsch",
  "body_markdown": "string mit 700-1100 Woertern"
}}

Vorgesehener Arbeitstitel: {item.title}
"""


def call_openai_json(client: OpenAI, model: str, prompt: str) -> dict[str, Any]:
    completion = client.chat.completions.create(
        model=model,
        temperature=0.7,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "Du bist Senior SEO-Redakteur fuer die Themenkombination "
                    "Eifel, regionale Digitalisierung und technologische Entwicklung."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )
    content = completion.choices[0].message.content or "{}"
    return json.loads(content)


def generate_image(
    client: OpenAI,
    image_model: str,
    prompt: str,
    out_path: Path,
    webp_quality: int,
    size: str = "1536x1024",
) -> None:
    result = client.images.generate(model=image_model, prompt=prompt, size=size)
    b64_data = result.data[0].b64_json
    if not b64_data:
        raise RuntimeError("Image API did not return b64 data")
    raw_bytes = base64.b64decode(b64_data)
    save_image_as_webp(raw_bytes, out_path=out_path, quality=webp_quality)


def _extract_image_urls(item: Any) -> list[str]:
    urls: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, str) and value.startswith(("http://", "https://")):
                    key_lower = key.lower()
                    if any(k in key_lower for k in ("image", "img", "thumbnail", "src", "url")):
                        urls.append(value)
                else:
                    walk(value)
            return
        if isinstance(node, list):
            for element in node:
                walk(element)
            return
        if isinstance(node, str) and node.startswith(("http://", "https://")):
            urls.append(node)

    walk(item)
    # De-duplicate while preserving order.
    return list(dict.fromkeys(urls))


def fetch_apify_image(
    out_path: Path,
    item: PlanItem,
    webp_quality: int,
    prompt_override: str | None = None,
    timeout_seconds: int = 120,
) -> bool:
    token = os.getenv("APIFY_API_TOKEN", "").strip()
    if not token:
        return False

    actor_id = os.getenv("APIFY_ACTOR_ID", "YtJT8AmK1AtfmsNh5").strip()
    run_url = (
        f"https://api.apify.com/v2/acts/{quote_plus(actor_id)}/run-sync-get-dataset-items"
        f"?token={quote_plus(token)}"
    )

    # Nanobanana Pro payload (prompt-based actor).
    google_api_key = os.getenv("APIFY_GOOGLE_API_KEY", "").strip()
    prompt_prefix = os.getenv("APIFY_IMAGE_PROMPT_PREFIX", "Professional photo, regional context,")
    effective_prompt = (prompt_override or "").strip()
    if not effective_prompt:
        effective_prompt = f"{item.title}, {item.region}, Eifel technology landscape"
    prompt = f"{prompt_prefix} {effective_prompt}"
    negative_prompt = os.getenv("APIFY_NEGATIVE_PROMPT", "text overlays, watermarks, logos").strip()
    try:
        number_of_images = int(os.getenv("APIFY_NUMBER_OF_IMAGES", "1"))
    except ValueError:
        number_of_images = 1
    number_of_images = max(1, min(number_of_images, 4))
    resolution = os.getenv("APIFY_RESOLUTION", "2K").strip() or "2K"
    if resolution not in {"1K", "1.5K", "2K", "4K"}:
        resolution = "2K"
    style = os.getenv("APIFY_STYLE", "photorealistic").strip() or "photorealistic"
    demo_mode = os.getenv("APIFY_DEMO_MODE", "false").strip().lower() in ("1", "true", "yes")
    if not google_api_key and not demo_mode:
        print("Apify skipped: APIFY_GOOGLE_API_KEY fehlt und APIFY_DEMO_MODE ist false.")
        return False

    payload: dict[str, Any] = {
        "demoMode": demo_mode,
        "negativePrompt": negative_prompt,
        "numberOfImages": number_of_images,
        "prompt": prompt,
        "resolution": resolution,
        "style": style,
    }
    if google_api_key:
        payload["googleApiKey"] = google_api_key

    try:
        response = requests.post(run_url, json=payload, timeout=timeout_seconds)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:  # pragma: no cover - network/API dependent
        print(f"Apify fetch skipped due to error: {exc}")
        return False

    items = data if isinstance(data, list) else [data]
    image_urls: list[str] = []
    for result in items:
        if isinstance(result, dict):
            images = result.get("images")
            if isinstance(images, list):
                for image_obj in images:
                    if isinstance(image_obj, dict):
                        url = image_obj.get("url")
                        if isinstance(url, str) and url.startswith(("http://", "https://")):
                            image_urls.append(url)
        image_urls.extend(_extract_image_urls(result))

    image_urls = list(dict.fromkeys(image_urls))
    if not image_urls:
        print("Apify fetch returned no image URL.")
        return False

    for image_url in image_urls:
        host = (urlparse(image_url).hostname or "").lower()
        if host in PLACEHOLDER_HOSTS:
            print(f"Skipping placeholder image host from Apify: {host}")
            continue
        try:
            image_response = requests.get(image_url, timeout=45)
            image_response.raise_for_status()
            save_image_as_webp(image_response.content, out_path=out_path, quality=webp_quality)
            print(f"Using image from Apify: {image_url}")
            return True
        except Exception as exc:  # pragma: no cover - network/API dependent
            print(f"Downloading Apify image failed for {image_url}: {exc}")

    print("No downloadable Apify image found; fallback to OpenAI image generation.")
    return False


def write_post(
    out_file: Path,
    item: PlanItem,
    payload: dict[str, Any],
    image_rel_path: str | None,
) -> None:
    title = normalize_text(str(payload.get("title") or item.title))
    description = normalize_text(str(payload.get("description") or f"{title} in der Region Eifel"))
    excerpt = normalize_text(str(payload.get("excerpt") or description))
    tags = [normalize_text(x) for x in normalize_list(payload.get("tags"), [item.region, item.it_focus, item.healthcare_focus])]
    categories = [normalize_text(x) for x in normalize_list(payload.get("categories"), ["Technologische Entwicklung Eifel"])]
    image_alt = normalize_text(str(payload.get("image_alt") or f"{title} in der Region Eifel"))
    body_markdown = ensure_internal_link(normalize_text(str(payload.get("body_markdown") or "")))
    body_markdown = ensure_required_keywords(body_markdown)

    if not body_markdown:
        raise RuntimeError("OpenAI payload enthaelt keinen Body-Text.")

    # Publish early in local time so same-day posts are immediately visible in Hugo
    # without needing --buildFuture during normal preview/build.
    post_date = f"{item.publish_date.isoformat()}T00:01:00+01:00"
    lines: list[str] = [
        "---",
        f"title: {yaml_quote(title)}",
        f"date: {post_date}",
        f"slug: {yaml_quote(item.slug)}",
        "draft: false",
        f"description: {yaml_quote(description)}",
        f"summary: {yaml_quote(excerpt)}",
        f"region: {yaml_quote(item.region)}",
        f"primary_keyword: {yaml_quote(item.primary_keyword)}",
        "keywords:",
    ]

    merged_keywords = list(dict.fromkeys(KEYWORDS + [item.primary_keyword, item.secondary_keyword]))
    for keyword in merged_keywords:
        lines.append(f"  - {yaml_quote(str(keyword))}")

    lines.append("tags:")
    for tag in tags:
        lines.append(f"  - {yaml_quote(str(tag))}")

    lines.append("categories:")
    for category in categories:
        lines.append(f"  - {yaml_quote(str(category))}")

    if image_rel_path:
        lines.append(f"image: {yaml_quote(image_rel_path)}")
        lines.append("images:")
        lines.append(f"  - {yaml_quote(image_rel_path)}")
        lines.append(f"imageAlt: {yaml_quote(image_alt)}")

    lines.extend(["---", "", body_markdown.rstrip(), ""])

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def run_hugo(site_root: Path) -> None:
    subprocess.run(["hugo", "--minify", "--gc"], cwd=site_root, check=True)


def ftp_mkdirs(ftp: FTP, remote_dir: str) -> None:
    if not remote_dir:
        return
    parts = [part for part in remote_dir.split("/") if part]
    for part in parts:
        try:
            ftp.cwd(part)
        except error_perm:
            ftp.mkd(part)
            ftp.cwd(part)


def ftp_upload_dir(local_dir: Path, remote_dir: str, use_tls: bool) -> None:
    host = os.getenv("FTP_HOST", "")
    user = os.getenv("FTP_USER", "")
    password = os.getenv("FTP_PASS", "")
    port = int(os.getenv("FTP_PORT", "21"))
    base_dir = os.getenv("FTP_DIR", remote_dir)

    if not host or not user or not password:
        raise RuntimeError("FTP_HOST, FTP_USER und FTP_PASS muessen gesetzt sein.")

    ftp_cls = FTP_TLS if use_tls else FTP
    with ftp_cls() as ftp:
        ftp.connect(host=host, port=port, timeout=30)
        ftp.login(user=user, passwd=password)
        if use_tls and isinstance(ftp, FTP_TLS):
            ftp.prot_p()

        ftp.cwd("/")
        ftp_mkdirs(ftp, base_dir)

        for path in sorted(local_dir.rglob("*")):
            rel = path.relative_to(local_dir).as_posix()
            if path.is_dir():
                try:
                    ftp.mkd(rel)
                except error_perm:
                    pass
                continue
            parent = Path(rel).parent.as_posix()
            ftp.cwd("/")
            ftp_mkdirs(ftp, f"{base_dir}/{parent}" if parent != "." else base_dir)
            with path.open("rb") as handle:
                ftp.storbinary(f"STOR {path.name}", handle)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate one daily Hugo post with OpenAI.")
    parser.add_argument("--publish-date", default=date.today().isoformat(), help="Date YYYY-MM-DD")
    parser.add_argument("--plan-file", default="data/redaktionsplan-365.csv", help="Path to plan CSV")
    parser.add_argument("--content-dir", default="content/blog", help="Hugo content dir for posts")
    parser.add_argument("--images-dir", default="static/images/blog", help="Image output dir")
    parser.add_argument("--model", default="gpt-4o", help="OpenAI model for text generation")
    parser.add_argument("--image-model", default="gpt-image-1", help="OpenAI model for images")
    parser.add_argument("--image-size", default="1536x1024", help="Image size for generated image")
    parser.add_argument(
        "--image-webp-quality",
        type=int,
        default=int_from_env("IMAGE_WEBP_QUALITY", 82),
        help="WebP quality from 1-100 (higher = better quality, larger files)",
    )
    parser.add_argument(
        "--deploy-target",
        choices=["none", "ftp"],
        default=os.getenv("DEPLOY_TARGET", "none"),
        help="Optional deployment target",
    )
    parser.add_argument("--ftp-tls", action="store_true", help="Use FTP_TLS for uploads")
    parser.add_argument("--skip-image", action="store_true", help="Skip DALL-E image generation")
    parser.add_argument("--no-build", action="store_true", help="Skip hugo build")
    parser.add_argument("--site-root", default=".", help="Hugo project root")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    image_webp_quality = clamp(int(args.image_webp_quality), 1, 100)
    publish_date = date.fromisoformat(args.publish_date)
    site_root = Path(args.site_root).resolve()
    plan_item = read_plan(Path(args.plan_file), publish_date)
    post_path = site_root / args.content_dir / f"{plan_item.slug}.md"
    legacy_match = list((site_root / args.content_dir).glob(f"*{plan_item.slug}.md"))

    if post_path.exists() or legacy_match:
        existing = legacy_match[0] if legacy_match else post_path
        print(f"Post already exists: {existing}")
        return

    api_key = clean_secret_env("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY ist nicht gesetzt.")
    if api_key == "***":
        raise RuntimeError("OPENAI_API_KEY ist als Platzhalter ('***') gesetzt und deshalb ungueltig.")
    if any(ch.isspace() for ch in api_key):
        raise RuntimeError("OPENAI_API_KEY enthaelt Whitespace und ist dadurch ungueltig.")
    if OpenAI is None:
        raise RuntimeError("Python package 'openai' fehlt. Bitte: pip install -r requirements.txt")

    organization = (
        first_non_empty_env("OPENAI_ORG_ID", "OPENAI_ORGANIZATION").replace("\r", "").replace("\n", "")
        or None
    )
    project = clean_secret_env("OPENAI_PROJECT_ID") or None
    client = OpenAI(api_key=api_key, organization=organization, project=project)
    try:
        payload = call_openai_json(client=client, model=args.model, prompt=build_prompt(plan_item))
    except AuthenticationError as exc:
        raise RuntimeError(
            "OpenAI Auth fehlgeschlagen (401). Bitte OPENAI_API_KEY in GitHub Secrets erneuern "
            "(nur den reinen Key ohne Quotes/Prefix) und Workflow neu starten."
        ) from exc
    except APIConnectionError as exc:
        raise RuntimeError("OpenAI APIConnectionError: Verbindung zur OpenAI API fehlgeschlagen.") from exc

    image_rel_path: str | None = None
    if not args.skip_image:
        if Image is None or ImageOps is None:
            raise RuntimeError("Bildverarbeitung aktiv, aber Pillow fehlt. Bitte: pip install -r requirements.txt")

        image_name = f"{plan_item.slug}.webp"
        image_file = site_root / args.images_dir / image_name
        image_prompt = str(payload.get("image_prompt") or plan_item.title).strip()
        fetched_from_apify = fetch_apify_image(
            out_path=image_file,
            item=plan_item,
            webp_quality=image_webp_quality,
            prompt_override=image_prompt,
        )
        if fetched_from_apify:
            image_rel_path = f"/images/blog/{image_name}"
        else:
            try:
                generate_image(
                    client=client,
                    image_model=args.image_model,
                    prompt=image_prompt,
                    out_path=image_file,
                    webp_quality=image_webp_quality,
                    size=args.image_size,
                )
                image_rel_path = f"/images/blog/{image_name}"
            except Exception as exc:  # pragma: no cover - network/API dependent
                print(f"Image generation skipped due to error: {exc}")

    write_post(out_file=post_path, item=plan_item, payload=payload, image_rel_path=image_rel_path)
    print(f"Created post: {post_path}")

    if not args.no_build:
        run_hugo(site_root=site_root)
        print("Hugo build completed.")

    if args.deploy_target == "ftp":
        public_dir = site_root / "public"
        if not public_dir.exists():
            raise RuntimeError("public/ nicht gefunden. Build muss vor FTP laufen.")
        ftp_upload_dir(local_dir=public_dir, remote_dir=os.getenv("FTP_DIR", ""), use_tls=args.ftp_tls)
        print("FTP deployment completed.")


if __name__ == "__main__":
    main()
