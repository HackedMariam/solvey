"""HTML/text helpers shared by the pipeline (logic reused from scrape_so copy.py)."""

import html
import os
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

IMAGE_HOSTS = ("i.stack.imgur.com", "i.sstatic.net", "stack.imgur.com")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def html_to_text(body_html):
    """Convert an HTML body to a clean plain-text description."""
    if not body_html:
        return ""
    return BeautifulSoup(body_html, "html.parser").get_text(" ", strip=True)


def unescape_title(raw_title):
    return html.unescape(raw_title or "")


def extract_images_from_html(body_html, post_id):
    """Parse HTML body, extract screenshot URLs (Stack Exchange image hosts only).

    Returns list of (url, filename) tuples. Logic identical to the baseline
    scraper so image naming stays compatible: so_<question_id>_<index>.<ext>.
    """
    if not body_html:
        return []
    soup = BeautifulSoup(body_html, "html.parser")
    images = []
    for idx, img in enumerate(soup.find_all("img")):
        src = img.get("src", "")
        if not src:
            continue
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = "https://stackoverflow.com" + src
        if not any(host in src for host in IMAGE_HOSTS):
            continue
        path = urlparse(src).path
        ext = os.path.splitext(path)[1].lower()
        if ext not in IMAGE_EXTS:
            ext = ".png"
        images.append((src, f"so_{post_id}_{idx}{ext}"))
    return images


def has_code_block(body_html):
    if not body_html:
        return False
    return "<code>" in body_html or "<pre" in body_html


def count_code_blocks(body_html):
    if not body_html:
        return 0
    return body_html.count("<code>") + body_html.count("<pre")


_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def normalize_title(title):
    """Lowercased alphanumeric-only title used for near-duplicate matching."""
    if not title:
        return ""
    return _NORMALIZE_RE.sub(" ", title.lower()).strip()


def canonical_question_id(url):
    """Extract the question id from a canonical SO URL (secondary identifier)."""
    if not url:
        return None
    m = re.search(r"/questions/(\d+)", url)
    return m.group(1) if m else None
