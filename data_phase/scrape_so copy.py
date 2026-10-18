"""
Stack Overflow IT Support Bug Screenshot Scraper
Searches for bug reports matching IT support taxonomy, extracts the issue
(title + description), its associated screenshots, and the resolution
(accepted or top-voted answer). Saves images and a CSV.

Usage: python "scrape_so copy.py"
"""

import csv
import os
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

OUTPUT_DIR = "with resolution"
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


def html_to_text(body_html):
    """Convert an HTML body to a clean plain-text description."""
    if not body_html:
        return ""
    return BeautifulSoup(body_html, "html.parser").get_text(" ", strip=True)


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


def get_answers(session, question_ids):
    """
    Fetch the answers for a set of question ids (batched, 100 ids per call).
    Returns dict: question_id -> list[answer dicts] (sorted by votes desc).
    """
    answers_by_qid = {}

    for i in range(0, len(question_ids), 100):
        chunk = question_ids[i:i + 100]
        ids = ";".join(str(qid) for qid in chunk)

        page = 1
        while True:
            params = {
                "order": "desc",
                "sort": "votes",
                "site": SITE,
                "filter": "withbody",   # includes answer body HTML
                "pagesize": 100,        # API max; answers span all questions
                "page": page,
                "key": API_KEY,
            }

            try:
                resp = session.get(
                    f"{API_BASE}/questions/{ids}/answers", params=params, timeout=30
                )
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as e:
                print(f"    Answers request failed: {e}")
                break

            backoff = data.get("backoff")
            if backoff:
                print(f"    API requested backoff: {backoff}s")
                time.sleep(backoff)

            for ans in data.get("items", []):
                answers_by_qid.setdefault(ans["question_id"], []).append(ans)

            if not data.get("has_more", False):
                break

            page += 1
            time.sleep(0.5)

        time.sleep(0.5)

    return answers_by_qid


def pick_resolution(answers):
    """
    Choose the issue resolution from a question's answers.
    Prefers the accepted answer, otherwise the highest-voted answer.
    Returns (answer or None, status string).
    """
    if not answers:
        return None, "none"

    for ans in answers:                # already sorted by votes desc
        if ans.get("is_accepted"):
            return ans, "accepted"

    return answers[0], "top_voted"


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
    pending = []   # questions with images, awaiting resolution lookup

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
                print(f"  Found: {title[:70]}... ({len(images)} image(s))")

                # Download images
                local_paths = []
                image_urls = []
                for img_url, filename in images:
                    filepath = os.path.join(IMAGES_DIR, filename)
                    if download_image(session, img_url, filepath):
                        local_paths.append(filename)
                        image_urls.append(img_url)
                        print(f"    Saved: {filename}")
                    time.sleep(0.1)

                if not local_paths:
                    continue  # No images successfully downloaded

                pending.append({
                    "category": category,
                    "subcategory": subcat_name,
                    "question_id": qid,
                    "title": title,
                    "link": q.get("link", ""),
                    "score": q.get("score", 0),
                    "creation_date": q.get("creation_date", 0),
                    "tags": ";".join(q.get("tags", []) or []),
                    "view_count": q.get("view_count", 0),
                    "answer_count": q.get("answer_count", 0),
                    "image_count": len(local_paths),
                    "image_files": ";".join(local_paths),
                    "image_urls": ";".join(image_urls),
                    "description": html_to_text(body_html),
                    "body_html": body_html,
                })

            # Rate limit courtesy
            time.sleep(1)

    # Fetch resolutions for every collected question (batched)
    all_rows = []
    if pending:
        print(f"\nFetching resolutions for {len(pending)} questions...")
        answers_by_qid = get_answers(session, [p["question_id"] for p in pending])

        for p in pending:
            ans, status = pick_resolution(answers_by_qid.get(p["question_id"], []))
            p["resolution_status"] = status
            p["has_answer"] = bool(ans)
            p["answer_id"] = ans.get("answer_id", "") if ans else ""
            p["answer_score"] = ans.get("score", "") if ans else ""
            p["answer_link"] = (
                (ans.get("link") or f"https://stackoverflow.com/a/{ans.get('answer_id')}")
                if ans else ""
            )
            p["answer_owner"] = (
                ans.get("owner", {}).get("display_name", "") if ans else ""
            )
            p["answer_creation_date"] = ans.get("creation_date", "") if ans else ""
            p["resolution"] = html_to_text(ans.get("body", "")) if ans else ""
            p["answer_body_html"] = ans.get("body", "") if ans else ""
            all_rows.append(p)

    # Write CSV
    if all_rows:
        fieldnames = [
            "category", "subcategory", "question_id", "title", "link",
            "score", "creation_date", "tags", "view_count", "answer_count",
            "image_count", "image_files", "image_urls",
            "description", "body_html",
            "resolution_status", "has_answer", "answer_id", "answer_score",
            "answer_link", "answer_owner", "answer_creation_date",
            "resolution", "answer_body_html",
        ]
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)

        resolved = sum(1 for r in all_rows if r["has_answer"])
        print(f"\n{'='*60}")
        print(f"Done! {len(all_rows)} posts with images saved.")
        print(f"Resolutions found: {resolved}/{len(all_rows)}")
        print(f"CSV:  {CSV_PATH}")
        print(f"Images: {IMAGES_DIR}/ ({sum(r['image_count'] for r in all_rows)} files)")
    else:
        print("\nNo posts with images found.")


if __name__ == "__main__":
    main()
