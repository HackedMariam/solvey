from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "data" / "upstream" / "SupportArticles-docs"
CORPUS = ROOT / "data" / "corpus"
MANIFEST = ROOT / "data" / "corpus_manifest.csv"
TAXONOMY = ("network_vpn", "auth_access", "email_communication", "software_apps", "system_os")
SOURCE_PREFIXES = (
    "Outlook/classic-outlook-for-windows/",
    "Exchange/ExchangeOnline/",
    "Microsoft365/admin/",
    "Office/Client/",
    "support/entra/entra-id/",
    "support/windows-client/networking/",
    "support/windows-client/installing-updates-features-roles/",
    "support/windows-client/setup-upgrade-and-drivers/",
    "support/windows-client/application-management/",
    "support/windows-client/active-directory/",
    "support/windows-hardware/drivers/",
)

_AUTH = re.compile(r"(?i)\b(authentication|authenticat\w*|sign[\s-]?in|login|password|credential|MFA|multi[\s-]?factor|account locked|account disabled|AADSTS)\b")
_NETWORK = re.compile(r"(?i)\b(network|Wi[\s-]?Fi|wireless|VPN|DNS|DHCP|TCP/?IP|proxy|connectivity|internet connection|Ethernet|802\.1x|WAN|adapter)\b")
_EMAIL = re.compile(r"(?i)\b(Outlook|email|e-?mail|mailbox|message|send|sending|receive|receiving|outbox|attachment|calendar|sync|synchroni[sz]e|profile)\b")
_APP = re.compile(r"(?i)\b(app(?:lication)?|install(?:ation)?|launch|start(?:up)?|crash|Office|Excel|Word|PowerPoint|Access|OneNote|activation|Microsoft Store|program|error|fail(?:ure)?|can't|cannot|unable|freeze|stuck)\b")
_OS = re.compile(r"(?i)\b(Windows Update|update error|driver|blue screen|BSOD|boot|startup|upgrade|feature update|install(?:ation)? error|device manager|Windows 10|Windows 11)\b")
_ADMIN_ONLY = re.compile(r"(?i)\b(PowerShell cmdlet|Exchange Management Shell|tenant-wide|organization-wide|mail flow rule|transport rule|admin center|Azure subscription)\b")


def _title(text: str, path: Path) -> str:
    for line in text.splitlines():
        heading = re.match(r"^#\s+(.+?)\s*#*$", line.strip())
        if heading:
            return heading.group(1).strip()
    frontmatter_title = re.search(r"(?m)^title:\s*[\"']?(.+?)[\"']?\s*$", text[:3000])
    return frontmatter_title.group(1).strip() if frontmatter_title else path.stem.replace("-", " ")


def classify_article(relative: str, text: str) -> tuple[str, int] | None:
    path = relative.replace("\\", "/")
    title = _title(text, Path(path))
    context = f"{path} {title} {text[:5000]}"
    if _ADMIN_ONLY.search(title):
        return None

    if (
        path.startswith("support/windows-client/networking/")
        or path.startswith("support/windows-hardware/drivers/")
    ) and _NETWORK.search(context):
        return "network_vpn", 5 + int(bool(_NETWORK.search(title)))

    auth_path = any(token in path.lower() for token in ("/authentication/", "/sign-in/", "/active-directory/"))
    if auth_path and _AUTH.search(f"{title} {path}"):
        return "auth_access", 5 + int(bool(_AUTH.search(title)))

    if path.startswith(("Outlook/classic-outlook-for-windows/", "Exchange/ExchangeOnline/")) and _EMAIL.search(title):
        if _AUTH.search(title):
            return "auth_access", 5 + int(bool(_AUTH.search(title)))
        return "email_communication", 5 + int(bool(re.search(r"(?i)\b(send|receive|mailbox|email|outlook)\b", title)))

    if (
        path.startswith("support/windows-client/installing-updates-features-roles/")
        or path.startswith("support/windows-client/setup-upgrade-and-drivers/")
    ) and _OS.search(f"{title} {path}"):
        return "system_os", 5 + int(bool(_OS.search(title)))

    if (
        path.startswith("support/windows-client/application-management/")
        or path.startswith("Outlook/classic-outlook-for-windows/Installation/")
        or path.startswith("Office/Client/")
    ) and _APP.search(title):
        return "software_apps", 5 + int(bool(_APP.search(title)))

    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Select and copy relevant Microsoft SupportArticles Markdown.")
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--per-category-limit", type=int, default=50)
    args = parser.parse_args()
    repo = args.repo.resolve()
    if not repo.is_dir():
        raise SystemExit(f"Missing sparse checkout: {repo}")
    revision = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()

    candidates: dict[str, list[tuple[int, str, Path, str]]] = {category: [] for category in TAXONOMY}
    for path in sorted(repo.rglob("*.md")):
        relative = path.relative_to(repo).as_posix()
        if not relative.startswith(SOURCE_PREFIXES):
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        classification = classify_article(relative, content)
        if classification:
            category, score = classification
            candidates[category].append((score, relative.casefold(), path, content))

    records = []
    for category in TAXONOMY:
        ordered = sorted(candidates[category], key=lambda row: (-row[0], row[1]))[:args.per_category_limit]
        for _score, relative_key, path, content in ordered:
            relative = path.relative_to(repo).as_posix()
            destination = CORPUS / category / "microsoftdocs" / Path(relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and destination.read_text(encoding="utf-8", errors="replace") != content:
                raise FileExistsError(f"Refusing to overwrite changed corpus article: {destination}")
            if not destination.exists():
                shutil.copyfile(path, destination)
            records.append({
                "source": destination.relative_to(ROOT / "data").as_posix(),
                "url": f"https://github.com/MicrosoftDocs/SupportArticles-docs/blob/{revision}/{relative}",
                "format": "md",
                "category": category,
                "source_type": "official_doc",
                "licence": "CC-BY-4.0",
                "status": "included",
                "attribution": f"MicrosoftDocs/SupportArticles-docs; repository LICENSE (CC-BY-4.0); commit {revision}",
                "notes": "Markdown article; code samples remain subject to repository LICENSE-CODE (MIT) where applicable.",
            })

    existing = []
    if MANIFEST.exists():
        with MANIFEST.open(newline="", encoding="utf-8") as stream:
            existing = list(csv.DictReader(stream))
    old_articles = [
        row for row in existing
        if row.get("source_type") == "official_doc"
        and "MicrosoftDocs/SupportArticles-docs/blob/" in row.get("url", "")
    ]
    existing = [row for row in existing if row not in old_articles]
    for row in existing:
        if "licence" not in row and "license" in row:
            row["licence"] = row.pop("license")
    selected_sources = {row["source"] for row in records}
    for row in old_articles:
        old_path = ROOT / "data" / Path(row["source"])
        if row["source"] not in selected_sources and old_path.is_file():
            relative_source = old_path.relative_to(CORPUS / row["category"] / "microsoftdocs")
            original = repo / Path(relative_source.as_posix())
            if original.is_file() and old_path.read_bytes() == original.read_bytes():
                old_path.unlink()
    fieldnames = ["source", "url", "format", "category", "source_type", "licence", "status", "attribution", "notes"]
    with MANIFEST.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing + records)

    counts = {category: sum(row["category"] == category for row in records) for category in TAXONOMY}
    print(f"Source revision: {revision}")
    for category, count in counts.items():
        print(f"{category}: {count}")
    print(f"Total selected Markdown articles: {len(records)}")
    if not 150 <= len(records) <= 250:
        print("NOTE: Selected article count is outside the requested 150-250 range; inspect category counts.")


if __name__ == "__main__":
    main()
