"""Subcategory relevance validation and difficulty classification.

Difficulty rubric (per Solvey spec):
  easy   - common, narrowly scoped problems with a straightforward diagnostic/fix
  medium - several diagnostic steps, log interpretation, multiple plausible causes
  hard   - advanced debugging, system-component interactions, complex root cause

Evidence used: title, body text, error messages, code, tags, resolution text.
NOT used: votes, views, age, answer count, or mere existence of a resolution.
"""

import re
from dataclasses import dataclass, field

from .taxonomy import RELEVANCE_PROFILES

# --------------------------------------------------------------------------- #
# Relevance
# --------------------------------------------------------------------------- #

def _curly(text):
    return (text or "").replace("’", "'").replace("‘", "'")


def relevance_score(subcategory, title, description, tags):
    """Score how well a question fits a subcategory. Returns (score, matched signals)."""
    profile = RELEVANCE_PROFILES.get(subcategory)
    if not profile:
        return 0, []
    title_l = _curly((title or "").lower())
    desc_l = _curly((description or "").lower())
    tag_set = {t.lower() for t in (tags or [])}
    score = 0
    matched = []

    tag_hits = [t for t in profile["tags"] if t.lower() in tag_set]
    if tag_hits:
        score += 3
        matched.append("tag:" + ",".join(tag_hits[:3]))

    strong_hits = [p for p in profile["strong"] if _curly(p.lower()) in title_l or _curly(p.lower()) in desc_l]
    if strong_hits:
        score += min(2 * len(strong_hits), 6)
        matched.append("strong:" + ",".join(strong_hits[:3]))

    weak_hits = [w for w in profile["weak"] if w.lower() in title_l or w.lower() in desc_l]
    if weak_hits:
        score += min(len(weak_hits), 3)
        matched.append("weak:" + ",".join(weak_hits[:3]))

    return score, matched


def is_relevant(subcategory, title, description, tags, min_score=3):
    score, _ = relevance_score(subcategory, title, description, tags)
    return score >= min_score


# --------------------------------------------------------------------------- #
# Difficulty
# --------------------------------------------------------------------------- #

@dataclass
class DifficultyResult:
    label: str
    confidence: float
    evidence: list = field(default_factory=list)
    hard_score: int = 0
    easy_score: int = 0
    needs_review: bool = False


HARD_PATTERNS = [
    ("stack_trace", re.compile(
        r"(Traceback \(most recent call last\)|Exception in thread|"
        r"^\s+at [\w.$<>]+\([\w.$<>]+:\d+\)|at [\w.]+\(.*\.java:\d+\))", re.M)),
    ("hex_error_code", re.compile(r"0x[0-9a-fA-F]{4,}")),
    ("exit_code", re.compile(r"(exit code|error code)\s*[:=]?\s*-?\d{2,}", re.I)),
    ("blue_screen", re.compile(r"(blue screen|bsod|stop code|bugcheck)", re.I)),
]

HARD_KEYWORDS = {
    "diagnostic_tool": ["event viewer", "wireshark", "tcpdump", "packet capture",
                        "netsh trace", "perfmon", "procmon", "windbg", "event log"],
    "kernel_dump": ["minidump", "memory dump", "kernel", "crash dump", ".dmp"],
    "intermittent": ["intermittent", "sporadic", "randomly", "every now and then",
                     "sometimes fails", "works sometimes"],
    "concurrency": ["race condition", "deadlock", "livelock", "thread hang",
                    "hung process", "freezes intermittently"],
    "cert_tls": ["certificate chain", "tls handshake", "cipher suite",
                 "ssl error", "handshake failure", "certificate expired"],
    "os_internals": ["registry", "group policy", "gpo", "powershell", "safe mode",
                     "bcdedit", "boot configuration", "system file checker",
                     "sfc ", "dism "],
    "dependency_conflict": ["version conflict", "dependency", "dll", "framework version",
                            "works on", "but not on", "compatibility"],
    "multi_error": ["multiple errors", "cascade", "followed by", "secondary failure"],
}

COMPONENT_KEYWORDS = [
    "dns", "dhcp", "firewall", "vpn", "active directory", "exchange", "registry",
    "group policy", "kerberos", "ldap", "proxy", "router", "switch", "vlan",
    "sql server", "iis", "azure", "aws", "hyper-v", "vmware", "certificate",
    "smtp", "imap", "ntp", "syslog", "raid", "bios", "UEFI",
]

EASY_KEYWORDS = {
    "howto": ["how do i", "how to", "where is", "what is the way"],
    "forgot_reset": ["forgot my password", "forgot password", "reset my password",
                     "reset password", "change my password"],
    "simple_fix": ["just need to", "simple question", "basic question",
                   "thanks in advance", "please help", "i'm new to", "beginner"],
    "single_step": ["restart it", "reinstall it", "uninstall and reinstall"],
}


def _count_keywords(text, keywords):
    return sum(1 for kw in keywords if kw in text)


def classify_difficulty(title, description, tags, resolution=""):
    """Assign exactly one difficulty label with evidence and confidence.

    ``tags`` is used only as weak corroborating context (broad tags like
    'kernel' or 'tcpdump' push toward hard; generic ones do nothing).
    Never uses score/views/answer_count/creation_date.
    """
    title_l = _curly((title or "").lower())
    desc_l = _curly((description or "").lower())
    res_l = _curly((resolution or "").lower())
    text = title_l + " " + desc_l
    evidence = []
    hard = 0
    easy = 0

    for name, pattern in HARD_PATTERNS:
        if pattern.search(text):
            hard += 1
            evidence.append(f"hard:{name}")

    for name, kws in HARD_KEYWORDS.items():
        hits = _count_keywords(text, kws)
        if hits:
            hard += min(hits, 2)
            evidence.append(f"hard:{name}({min(hits, 2)})")

    components = {c for c in COMPONENT_KEYWORDS if c in text}
    if len(components) >= 3:
        hard += 2
        evidence.append(f"hard:multi_component({len(components)})")
    elif len(components) == 2:
        hard += 1
        evidence.append("hard:two_components")

    tag_l = {t.lower() for t in (tags or [])}
    advanced_tags = {"kernel", "tcpdump", "wireshark", "gdb", "strace", "minidump",
                     "bsod", "xdebug", "perf", "dmesg", "windbg"}
    if tag_l & advanced_tags:
        hard += 1
        evidence.append("hard:advanced_tag")

    body_len = len(desc_l)
    codeish = desc_l.count("<code>") + desc_l.count("<pre")
    if codeish:
        evidence.append(f"info:code_blocks({codeish})")

    if body_len > 1200:
        hard += 1
        evidence.append("hard:long_body")
    if desc_l and desc_l.count("error") >= 3:
        hard += 1
        evidence.append("hard:repeated_errors")

    if res_l:
        step_markers = sum(1 for m in ("step 1", "first,", " then", "finally", "1.", "2.")
                           if m in res_l)
        if len(res_l) > 1500 and step_markers >= 2:
            hard += 1
            evidence.append("hard:multi_step_resolution")

    # ---- easy signals ----
    if 0 < body_len < 400:
        easy += 1
        evidence.append("easy:short_body")
    if _count_keywords(text, EASY_KEYWORDS["howto"]):
        easy += 1
        evidence.append("easy:howto_phrase")
    if _count_keywords(text, EASY_KEYWORDS["forgot_reset"]):
        easy += 1
        evidence.append("easy:forgot_reset")
    if _count_keywords(text, EASY_KEYWORDS["simple_fix"]):
        easy += 1
        evidence.append("easy:simple_fix_language")
    if _count_keywords(text, EASY_KEYWORDS["single_step"]) and body_len < 800:
        easy += 1
        evidence.append("easy:single_step")
    if res_l and len(res_l) < 250 and any(k in res_l for k in (
            "restart", "reinstall", "reset", "enable", "install", "change the", "update")):
        easy += 1
        evidence.append("easy:short_fix_resolution")
    if title_l.count("?") >= 1 and 0 < body_len < 600 and codeish == 0:
        easy += 1
        evidence.append("easy:focus_narrow")

    # Label: hard needs clear hard net evidence (>=2); easy needs at least one
    # easy signal and no hard net evidence (score <= -1); else medium.
    score = hard - easy
    if score >= 2:
        label = "hard"
    elif score <= -1:
        label = "easy"
    else:
        label = "medium"

    if label == "medium":
        confidence = 0.55 if score == 0 else 0.5
    else:
        confidence = round(min(0.95, 0.55 + 0.08 * abs(score)), 2)

    needs_review = abs(score) <= 1 or (hard > 0 and easy > 0 and abs(score) <= 2)

    return DifficultyResult(
        label=label,
        confidence=confidence,
        evidence=evidence,
        hard_score=hard,
        easy_score=easy,
        needs_review=needs_review,
    )
