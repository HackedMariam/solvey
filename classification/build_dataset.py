"""Build the Solvey classifier training data.

Combines the generated tickets in data/generated/ with a small sample of
out-of-scope ("other") tickets from two public datasets, validates every row
against the labeling guidelines (docs/labeling-guidelines.md), removes
duplicates, and writes a stratified train/validation split to data/processed/.

The test set is NOT built here: it must be human-written and kept separate.

Usage (from the repo root, with the venv active):
    python classification/build_dataset.py
"""

import json
import re
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parent.parent
GENERATED_DIR = ROOT / "data" / "generated"
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "processed"

KAGGLE_CSV = RAW_DIR / "all_tickets_processed_improved_v3.csv"
HF_CSV = RAW_DIR / "customer-support-tickets.csv"

GENERATOR = "claude-opus-5-5"
SEED = 42
VAL_FRACTION = 0.15

# Labels and their allowed subcategories (labeling guidelines v1.0, section 4).
TAXONOMY = {
    "network_vpn": ["VPN authentication failure", "VPN connection failure", "Wi-Fi connectivity issue",
                    "DNS configuration error", "Internet connection problem"],
    "authentication_access": ["Wrong/expired password", "Account locked", "MFA authentication failure",
                              "Permission denied", "Access to restricted resource"],
    "email_communication": ["Cannot send email", "Cannot receive email", "Email authentication failure",
                            "Mailbox storage full", "Email client configuration problem"],
    "software_applications": ["Application won't launch", "Application crash", "Installation failure",
                              "Application configuration error", "Software update failure"],
    "system_os": ["OS error (Windows/Linux/macOS)", "Driver problem", "OS update failure",
                  "System performance issue", "Hardware-related error"],
    "other": ["Not IT", "Unsupported IT", "Too vague"],
}

# Public "other" samples: (source group, how many). Kept small on purpose so a
# source's writing style cannot become a shortcut for predicting "other".
KAGGLE_OTHER_GROUPS = {"Purchase": 10, "Internal Project": 10, "HR Support": 10}
HF_OTHER_QUEUES = {"Billing and Payments": 10, "Returns and Exchanges": 10, "Sales and Pre-Sales": 10}

# Tickets mentioning these words may really be IT problems; skip them when
# sampling "other" from public data.
IT_WORDS = re.compile(
    r"\b(?:password|login|log in|account|access|laptop|computer|pc|printer|email|e-mail|mail|outlook|"
    r"wifi|wi-fi|network|vpn|internet|software|install|system|server|application|app|error|"
    r"crash|update|device|monitor|screen|drive|folder|security|integration|platform)\b",
    re.IGNORECASE,
)


# Pre-screen of the sampled public tickets (2026-10-18, by the generator model;
# a teammate should confirm). Keys are source_ref values, stable for SEED=42.
PUBLIC_DROP = {
    # Really IT problems (network port, bandwidth, login, installation, app setup) or junk.
    "row:14072|Topic_group:HR Support", "row:25659|Topic_group:HR Support", "row:37644|Topic_group:HR Support",
    "row:46080|Topic_group:HR Support", "row:5468|Topic_group:Purchase", "row:33713|Topic_group:HR Support",
    "row:32868|Topic_group:Purchase", "row:13259|Topic_group:HR Support", "row:5944|Topic_group:Internal Project",
    "row:5441|queue:Sales and Pre-Sales", "row:26430|queue:Returns and Exchanges",
    # Near-copies of the same "digital strategies for brand growth" template.
    "row:27859|queue:Billing and Payments", "row:19695|queue:Billing and Payments",
    "row:19991|queue:Returns and Exchanges", "row:8339|queue:Billing and Payments",
}
PUBLIC_UNSUPPORTED_IT = {  # Developer tooling (Keras/Azure, Docker, OBS integration).
    "row:9707|queue:Sales and Pre-Sales", "row:2719|queue:Sales and Pre-Sales", "row:1682|queue:Sales and Pre-Sales",
}


def apply_public_review(rows):
    kept = []
    for r in rows:
        if r["source_ref"] in PUBLIC_DROP:
            continue
        if r["source_ref"] in PUBLIC_UNSUPPORTED_IT:
            r["subcategory"] = "Unsupported IT"
        r["notes"] = "pre-screened by generator model; needs human confirmation"
        kept.append(r)
    return kept


def load_generated():
    rows = []
    for path in sorted(GENERATED_DIR.glob("*.jsonl")):
        label = path.stem
        if label not in TAXONOMY:
            raise ValueError(f"{path.name}: file name is not a label id")
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            item = json.loads(line)
            if item["subcategory"] not in TAXONOMY[label]:
                raise ValueError(f"{path.name}:{line_no}: subcategory {item['subcategory']!r} not allowed for {label}")
            rows.append({
                "title": item.get("title", "").strip(),
                "description": item["description"].strip(),
                "label": label,
                "subcategory": item["subcategory"],
                "source": "generated",
                "source_ref": f"{GENERATOR}:{path.name}:{line_no}",
                "labeler": GENERATOR,
                "notes": "",
            })
    return rows


def sample_public_other():
    rows = []
    kaggle = pd.read_csv(KAGGLE_CSV)
    words = kaggle["Document"].str.split().str.len()
    kaggle = kaggle[words.between(8, 80) & ~kaggle["Document"].str.contains(IT_WORDS)]
    for group, n in KAGGLE_OTHER_GROUPS.items():
        for idx, r in kaggle[kaggle["Topic_group"] == group].sample(n, random_state=SEED).iterrows():
            rows.append({
                "title": "",
                "description": r["Document"].strip(),
                "label": "other",
                "subcategory": "Not IT",
                "source": "kaggle_it_tickets",
                "source_ref": f"row:{idx}|Topic_group:{group}",
                "labeler": "auto-mapped",
                "notes": "needs human review",
            })

    hf = pd.read_csv(HF_CSV)
    hf = hf[(hf["language"] == "en") & hf["body"].notna()]
    text = hf["subject"].fillna("") + " " + hf["body"]
    hf = hf[~text.str.contains(IT_WORDS)]
    for queue, n in HF_OTHER_QUEUES.items():
        for idx, r in hf[hf["queue"] == queue].sample(n, random_state=SEED).iterrows():
            rows.append({
                "title": "" if pd.isna(r["subject"]) else str(r["subject"]).strip(),
                "description": str(r["body"]).replace("\\n", " ").strip(),
                "label": "other",
                "subcategory": "Not IT",
                "source": "hf_customer_support",
                "source_ref": f"row:{idx}|queue:{queue}",
                "labeler": "auto-mapped",
                "notes": "needs human review",
            })
    return rows


def model_text(title, description):
    """Classifier input, as defined in docs/contracts/classifier-output.md."""
    return f"{title}. {description}" if title else description


def normalize(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def main():
    df = pd.DataFrame(load_generated() + apply_public_review(sample_public_other()))
    df["text"] = [model_text(t, d) for t, d in zip(df["title"], df["description"])]

    before = len(df)
    df = df[df["description"].str.len() > 0].copy()
    df["key"] = df["text"].map(normalize)
    df = df.drop_duplicates(subset="key").drop(columns="key")
    print(f"rows: {before} -> {len(df)} after removing empty and duplicate tickets")

    prefix = {"generated": "gen", "kaggle_it_tickets": "kaggle", "hf_customer_support": "hf"}
    df = df.reset_index(drop=True)
    df.insert(0, "ticket_id", [f"{prefix[s]}-{i:05d}" for i, s in enumerate(df["source"])])

    train, val = train_test_split(df, test_size=VAL_FRACTION, stratify=df["label"], random_state=SEED)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    columns = ["ticket_id", "title", "description", "text", "label", "subcategory",
               "source", "source_ref", "labeler", "notes"]
    train[columns].to_csv(OUT_DIR / "train.csv", index=False, encoding="utf-8")
    val[columns].to_csv(OUT_DIR / "val.csv", index=False, encoding="utf-8")

    summary = pd.crosstab(df["label"], df["source"], margins=True, margins_name="total")
    print("\nTickets per label and source:\n", summary.to_string())
    print(f"\ntrain: {len(train)}  val: {len(val)}  -> {OUT_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
