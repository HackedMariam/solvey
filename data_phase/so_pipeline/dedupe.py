"""Deduplication: question id (primary), canonical URL, normalized/near-duplicate titles."""

from dataclasses import dataclass
from difflib import SequenceMatcher

from .textutils import canonical_question_id, normalize_title

NEAR_DUP_RATIO = 0.93
MIN_TITLE_LEN_FOR_NEAR_DUP = 25


@dataclass
class DuplicateHit:
    reason: str          # duplicate_id | duplicate_url | duplicate_title | near_duplicate_title
    existing_id: str
    detail: str = ""


class DedupeRegistry:
    """Tracks every accepted question so later candidates can be rejected."""

    def __init__(self):
        self.by_id = {}            # question_id -> record meta
        self.by_url_id = {}        # canonical url id -> question_id
        self.titles = []           # (normalized_title, question_id) in insertion order

    def __len__(self):
        return len(self.by_id)

    def check(self, question_id, url, title):
        """Return a DuplicateHit if this question duplicates an existing one, else None."""
        qid = str(question_id)
        if qid in self.by_id:
            return DuplicateHit("duplicate_id", qid)

        url_id = canonical_question_id(url)
        if url_id and url_id in self.by_url_id:
            return DuplicateHit("duplicate_url", self.by_url_id[url_id], url)

        norm = normalize_title(title)
        if len(norm) >= MIN_TITLE_LEN_FOR_NEAR_DUP:
            for existing_norm, existing_id in self.titles:
                if norm == existing_norm:
                    return DuplicateHit("duplicate_title", existing_id, norm)
                # cheap pre-filter: only compare titles sharing a long prefix word set
                if abs(len(norm) - len(existing_norm)) > 15:
                    continue
                if SequenceMatcher(None, norm, existing_norm).ratio() >= NEAR_DUP_RATIO:
                    return DuplicateHit("near_duplicate_title", existing_id, norm)
        return None

    def add(self, question_id, url, title):
        qid = str(question_id)
        self.by_id[qid] = {"url": url, "title": title}
        url_id = canonical_question_id(url)
        if url_id:
            self.by_url_id.setdefault(url_id, qid)
        norm = normalize_title(title)
        if norm:
            self.titles.append((norm, qid))
