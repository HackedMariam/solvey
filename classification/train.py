"""Fine-tune DistilBERT on the Solvey ticket classification data.

Reads data/processed/train.csv and val.csv (built by build_dataset.py),
fine-tunes distilbert-base-uncased for the 6 labels of the classifier contract
(docs/contracts/classifier-output.md), and saves the best checkpoint by
validation macro-F1 to models/solvey-distilbert-<version>/.

Usage (from the repo root, with the venv active):
    python classification/train.py
"""

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from datasets import Dataset
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
    set_seed,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "processed"

BASE_MODEL = "distilbert-base-uncased"
MODEL_NAME = "solvey-distilbert"
MODEL_VERSION = "0.1.0"
OUT_DIR = ROOT / "models" / f"{MODEL_NAME}-{MODEL_VERSION}"

# Order fixes the integer ids; must match the contract's label list.
LABELS = ["network_vpn", "authentication_access", "email_communication",
          "software_applications", "system_os", "other"]
LABEL2ID = {label: i for i, label in enumerate(LABELS)}
ID2LABEL = dict(enumerate(LABELS))

MAX_LENGTH = 128
SEED = 42


def load_split(name, tokenizer):
    df = pd.read_csv(DATA_DIR / f"{name}.csv", keep_default_na=False)
    unknown = set(df["label"]) - set(LABELS)
    if unknown:
        raise ValueError(f"{name}.csv has unknown labels: {unknown}")
    ds = Dataset.from_dict({"text": df["text"].tolist(), "label": df["label"].map(LABEL2ID).tolist()})
    return ds.map(lambda b: tokenizer(b["text"], truncation=True, max_length=MAX_LENGTH), batched=True)


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    return {"accuracy": accuracy_score(labels, preds), "macro_f1": f1_score(labels, preds, average="macro")}


def main():
    set_seed(SEED)
    if not torch.cuda.is_available():
        print("WARNING: no GPU found, training on CPU will be slow")

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    train_ds = load_split("train", tokenizer)
    val_ds = load_split("val", tokenizer)

    lengths = [len(ids) for ids in train_ds["input_ids"]]
    print(f"train {len(train_ds)} | val {len(val_ds)} | tokens median {int(np.median(lengths))}, "
          f"max {max(lengths)}, truncated {sum(n >= MAX_LENGTH for n in lengths)}")

    model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL, num_labels=len(LABELS), id2label=ID2LABEL, label2id=LABEL2ID)

    epochs, batch_size = 8, 16
    # 10% of all optimizer steps warm up the learning rate (warmup_ratio was removed in transformers 5).
    warmup_steps = int(0.1 * epochs * math.ceil(len(train_ds) / batch_size))

    args = TrainingArguments(
        output_dir=str(OUT_DIR / "checkpoints"),
        num_train_epochs=epochs,
        learning_rate=3e-5,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=32,
        weight_decay=0.01,
        warmup_steps=warmup_steps,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="macro_f1",
        greater_is_better=True,
        fp16=torch.cuda.is_available(),
        logging_steps=10,
        report_to="none",
        seed=SEED,
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        processing_class=tokenizer,
        data_collator=DataCollatorWithPadding(tokenizer),
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )
    trainer.train()

    # Final evaluation of the best checkpoint on the validation set.
    pred = trainer.predict(val_ds)
    y_true, y_pred = pred.label_ids, pred.predictions.argmax(-1)
    probs = torch.softmax(torch.tensor(pred.predictions, dtype=torch.float32), dim=-1).numpy()
    report = classification_report(y_true, y_pred, labels=range(len(LABELS)), target_names=LABELS,
                                   digits=3, output_dict=True, zero_division=0)
    print("\n" + classification_report(y_true, y_pred, labels=range(len(LABELS)), target_names=LABELS,
                                       digits=3, zero_division=0))
    cm = confusion_matrix(y_true, y_pred, labels=range(len(LABELS)))
    print("Confusion matrix (rows = true, columns = predicted):")
    print(pd.DataFrame(cm, index=LABELS, columns=LABELS).to_string())
    confident = probs.max(-1)
    print(f"\nconfidence: median {np.median(confident):.3f} | below 0.70: {(confident < 0.70).sum()} of {len(confident)}")

    trainer.save_model(str(OUT_DIR))
    tokenizer.save_pretrained(str(OUT_DIR))
    metrics = {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "base_model": BASE_MODEL,
        "labels": LABELS,
        "max_length": MAX_LENGTH,
        "best_epoch_metric": trainer.state.best_metric,
        "val_accuracy": report["accuracy"],
        "val_macro_f1": report["macro avg"]["f1-score"],
        "per_label": {k: report[k] for k in LABELS},
        "confusion_matrix": cm.tolist(),
        "calibrated": False,
        "note": "Validation set is synthetic like the training data; real accuracy needs the human-written test set.",
    }
    (OUT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"\nsaved model and metrics.json to {OUT_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
