"""
Stack Overflow IT Support Bug Screenshot Scraper
Searches for bug reports matching IT support taxonomy, extracts images, saves to CSV.

Usage: python scrape_so.py
"""

import csv
import os
import re
import time
import html
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ============ CONFIGURATION ============
load_dotenv()
# Get a free key at https://stackapps.com/apps/oauth/register
# Set API_KEY in a .env file (never commit it)
API_KEY = os.environ.get("API_KEY")
if not API_KEY:
    raise SystemExit("API_KEY not set. Add API_KEY=... to your .env file.")

OUTPUT_DIR = "so_bug_data"
IMAGES_DIR = os.path.join(OUTPUT_DIR, "images")
CSV_PATH = os.path.join(OUTPUT_DIR, "results.csv")

SITE = "stackoverflow"
API_BASE = "https://api.stackexchange.com/2.3"

# Your 25 subcategories mapped to search queries
# We search for each and collect unique posts
TAXONOMY_QUERIES = {
    "Network & VPN": [
        ("VPN authentication failure", "vpn authentication failure"),
        ("VPN connection failure", "vpn connection failure"),
        ("Wi-Fi connectivity issue", "wifi connectivity issue"),
        ("DNS configuration error", "dns configuration error"),
        ("Internet connection problem", "internet connection problem"),
    ],
    "Authentication & Access": [
        ("Wrong/expired password", "wrong expired password"),
        ("Account locked", "account locked"),
        ("MFA authentication failure", "mfa authentication failure"),
        ("Permission denied", "permission denied"),
        ("Access to restricted resource", "access restricted resource"),
    ],
    "Email & Communication": [
        ("Cannot send email", "cannot send email"),
        ("Cannot receive email", "cannot receive email"),
        ("Email authentication failure", "email authentication failure"),
        ("Mailbox storage full", "mailbox storage full"),
        ("Email client configuration problem", "email client configuration"),
    ],
    "Software & Applications": [
        ("Application won't launch", "application won't launch"),
        ("Application crash", "application crash"),
        ("Installation failure", "installation failure"),
        ("Application configuration error", "application configuration error"),
        ("Software update failure", "software update failure"),
    ],
    "System & OS": [
        ("Windows/system error", "windows system error"),
        ("Driver problem", "driver problem"),
        ("OS update failure", "os update failure"),
        ("System performance issue", "system performance issue"),
        ("Hardware-related error", "hardware error"),
    ],
}
# =======================================


def ensure_dirs():
    os.makedirs(IMAGES_DIR, exist_ok=True)


def get_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "ITBugScraper/1.0 (educational research)"
    })
    return session


def extract_images_from_html(body_html, post_id):
    """
    Parse HTML body, extract image URLs.
    Returns list of (url, local_filename) tuples.
    """
    if not body_html:
        return []

    soup = BeautifulSoup(body_html, "html.parser")
    images = []

    for idx, img in enumerate(soup.find_all("img")):
        src = img.get("src", "")
        if not src:
            continue

        # Normalize relative URLs
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = "https://stackoverflow.com" + src

        # Only keep likely screenshot hosts
        if not any(host in src for host in [
            "i.stack.imgur.com", "i.sstatic.net", "stack.imgur.com"
        ]):
            continue

        # Determine extension
        parsed = urlparse(src)
        path = parsed.path
        ext = os.path.splitext(path)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            ext = ".png"

        filename = f"so_{post_id}_{idx}{ext}"
        images.append((src, filename))

    return images


def search_questions(session, query, max_pages=2):
    """
    Search Stack Overflow for questions matching query.
    Returns list of question dicts (with body when possible).
    """
    results = []

    for page in range(1, max_pages + 1):
        params = {
            "order": "desc",
            "sort": "relevance",
            "q": query,
            "site": SITE,
            "pagesize": 50,          # API max for search is lower in practice
            "page": page,
            "filter": "withbody",    # CRITICAL: includes body HTML
            "key": API_KEY,
        }

        try:
            resp = session.get(f"{API_BASE}/search/advanced", params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"    Request failed: {e}")
            break

        # Honor API backoff
        backoff = data.get("backoff")
        if backoff:
            print(f"    API requested backoff: {backoff}s")
            time.sleep(backoff)

        quota_remaining = data.get("quota_remaining")
        if quota_remaining is not None and quota_remaining < 10:
            print(f"    WARNING: Only {quota_remaining} API calls remaining today!")

        items = data.get("items", [])
        if not items:
            break

        results.extend(items)

        # Check if more pages available
        if not data.get("has_more", False):
            break

        # Be nice to the API
        time.sleep(0.5)

    return results


def download_image(session, url, filepath):
    """Download a single image. Returns True on success."""
    try:
        resp = session.get(url, timeout=30, stream=True)
        resp.raise_for_status()

        # Validate it's actually an image by checking content-type
        ct = resp.headers.get("Content-Type", "")
        if "image" not in ct.lower():
            return False

        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"      Failed to download {url}: {e}")
        return False


def main():
    ensure_dirs()
    session = get_session()

    # Track unique posts by question_id to avoid duplicates
    seen_ids = set()
    all_rows = []

    total_queries = sum(len(v) for v in TAXONOMY_QUERIES.values())
    current = 0

    for category, subcategories in TAXONOMY_QUERIES.items():
        for subcat_name, query in subcategories:
            current += 1
            print(f"\n[{current}/{total_queries}] Searching: {subcat_name} ({category})")

            questions = search_questions(session, query, max_pages=1)

            for q in questions:
                qid = q.get("question_id")
                if qid in seen_ids:
                    continue
                seen_ids.add(qid)

                body_html = q.get("body", "")
                images = extract_images_from_html(body_html, qid)

                if not images:
                    continue  # Skip posts without images

                title = html.unescape(q.get("title", ""))
                link = q.get("link", "")
                score = q.get("score", 0)
                creation_date = q.get("creation_date", 0)

                print(f"  Found: {title[:70]}... ({len(images)} image(s))")

                # Download images
                local_paths = []
                for img_url, filename in images:
                    filepath = os.path.join(IMAGES_DIR, filename)
                    if download_image(session, img_url, filepath):
                        local_paths.append(filename)
                        print(f"    Saved: {filename}")
                    time.sleep(0.1)

                if not local_paths:
                    continue  # No images successfully downloaded

                row = {
                    "category": category,
                    "subcategory": subcat_name,
                    "question_id": qid,
                    "title": title,
                    "link": link,
                    "score": score,
                    "creation_date": creation_date,
                    "image_count": len(local_paths),
                    "image_files": ";".join(local_paths),
                    "body_html": body_html,  # full HTML, useful for text extraction
                }
                all_rows.append(row)

            # Rate limit courtesy
            time.sleep(1)

    # Write CSV
    if all_rows:
        fieldnames = [
            "category", "subcategory", "question_id", "title",
            "link", "score", "creation_date", "image_count",
            "image_files", "body_html"
        ]
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)

        print(f"\n{'='*60}")
        print(f"Done! {len(all_rows)} posts with images saved.")
        print(f"CSV:  {CSV_PATH}")
        print(f"Images: {IMAGES_DIR}/ ({sum(r['image_count'] for r in all_rows)} files)")
    else:
        print("\nNo posts with images found.")


if __name__ == "__main__":
    main()