"""Deterministic guardrails used by the Validator."""
from __future__ import annotations

import re
import unicodedata

_SENSITIVE_PATTERNS = [
    r"\bhack(ed|é|ée)?\b", r"pirat(é|ée|age)", r"compromi(s|se|sed)\b", r"phishing", r"hame[cç]onn",
    r"ransomware", r"ran[cç]ongiciel", r"malware", r"\bvirus\b", r"trojan", r"cheval de troie",
    r"(stolen|vol[ée]?) (laptop|pc|ordinateur|phone|t[ée]l[ée]phone)", r"data (leak|breach)",
    r"fuite de donn[ée]es", r"someone (logged|signed) in", r"quelqu'?un (s'est )?connect[ée]",
    r"suspicious (login|activity|email)", r"activit[ée] suspecte", r"(clicked|cliqu[ée]) (on )?(the|le|un|a)? ?lien",
    r"admin(istrator)? (password|rights|access)", r"droits? admin", r"bypass", r"contourner",
]
_SENSITIVE_RE = re.compile("|".join(_SENSITIVE_PATTERNS), re.IGNORECASE)


def detect_sensitive(text: str) -> str | None:
    """Return a matched expression when a request looks security-sensitive."""
    match = _SENSITIVE_RE.search(text or "")
    return match.group(0) if match else None


_DESTRUCTIVE_PATTERNS = [
    r"\brm\s+-[a-z]*r[a-z]*f", r"\brm\s+-[a-z]*f[a-z]*r", r"\bmkfs", r"\bdd\s+if=", r"\bformat\s+[a-z]:",
    r"\bdel\s+/[sfq]", r"\brmdir\s+/s", r"\breg\s+delete", r"chmod\s+(-R\s+)?777", r"\bprune\s+(-a|--all)",
    r"system\s+prune", r"volume\s+rm", r"\bdrop\s+(table|database)", r"diskpart", r"bcdedit",
    r"Set-ExecutionPolicy\s+Unrestricted", r"netsh\s+advfirewall\s+set\s+\w+\s+state\s+off",
    r"setenforce\s+0", r"ufw\s+disable",
]
_DESTRUCTIVE_RE = re.compile("|".join(_DESTRUCTIVE_PATTERNS), re.IGNORECASE)


def find_destructive(command: str) -> str | None:
    """Return the destructive command fragment, if any."""
    match = _DESTRUCTIVE_RE.search(command or "")
    return match.group(0) if match else None


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = text.replace("`", " ").replace("$ ", " ")
    return re.sub(r"\s+", " ", text).strip()


def command_is_grounded(command: str, source_texts: list[str]) -> bool:
    """Check that the command's first two meaningful tokens occur in a cited passage."""
    tokens = [
        token for token in _norm(command).split()
        if token not in {"sudo", "$", "#", ">"}
        and not (token.startswith("<") and token.endswith(">"))
    ]
    if not tokens:
        return True
    core = " ".join(tokens[:2])
    return any(core in _norm(source) for source in source_texts)


_FR_WORDS = {
    "le", "la", "les", "je", "mon", "ma", "mes", "ne", "pas", "est", "une", "un", "des", "erreur",
    "connexion", "impossible", "marche", "fonctionne", "depuis", "avec", "pour", "sur", "et", "mot", "passe",
}


def detect_language(text: str) -> str:
    """Return French or English using the established lightweight word heuristic."""
    words = re.findall(r"[a-zàâçéèêëîïôûùüÿœ']+", (text or "").lower())
    if not words:
        return "en"
    french = sum(word in _FR_WORDS for word in words)
    return "fr" if french / len(words) > 0.12 or re.search(r"[éèàçù]", text or "") else "en"
