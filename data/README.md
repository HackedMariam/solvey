# Classifier data

| Folder | In git? | Content |
|---|---|---|
| `generated/` | yes | Synthetic training tickets, one JSONL file per label (file name = label id). Written by `claude-opus-5-5` from `docs/labeling-guidelines.md` v1.0. |
| `raw/` | **no** | Third-party datasets. Download them yourself (below). |
| `processed/` | **no** | `train.csv` / `val.csv`, rebuilt by `python classification/build_dataset.py`. |

The **test set** is not here: it must be human-written and double-labeled (guidelines, section 6).

## Raw datasets (download into `data/raw/`)

| File | Source | License | Used for |
|---|---|---|---|
| `all_tickets_processed_improved_v3.csv` | [IT Service Ticket Classification Dataset](https://www.kaggle.com/datasets/adisongoh/it-service-ticket-classification-dataset) (Kaggle, adisongoh) — download the zip, extract the CSV | CC0: Public Domain | ~20 `other` tickets (Purchase, Internal Project, HR Support) |
| `customer-support-tickets.csv` | [Tobi-Bueck/customer-support-tickets](https://huggingface.co/datasets/Tobi-Bueck/customer-support-tickets), file `aa_dataset-tickets-multi-lang-5-2-50-version.csv`, renamed | CC BY-NC 4.0 — credit Tobi Bueck, non-commercial use | ~25 `other` tickets (Billing, Returns, Sales; English only) |

## Known limitations (for the report)

- About 94% of training tickets are synthetic. Real-world accuracy must be measured on the human-written test set.
- The Kaggle text is preprocessed (lowercase, no punctuation or digits, stop words removed) and several of its labels were wrong in spot checks; it is used only for a small, reviewed `other` sample.
- The Hugging Face tickets are formal, corporate-style and appear generated; same restricted use.
- Public samples were pre-screened by the generator model and still need confirmation by a teammate (`notes` column).
