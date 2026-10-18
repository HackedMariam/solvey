# Classifier Output Contract

**Schema version:** `1.0`
**Status:** PROPOSED — not implemented yet. The n8n workflow currently uses a mock
(`Mock DistilBERT Output`) whose output has a *different*, older shape
(`category`, `subcategory`, `confidence` as flat fields). The mock will be updated
to this contract before the real model replaces it.
**Owner:** Mohamed Mahmoud (classifier + n8n architecture)
**Consumers:** validator / risk-and-escalation rules, downstream n8n steps

---

## 1. What the classifier does — and does not do

The classifier reads the ticket text and predicts **one of 6 labels**:
the 5 parent categories of the Solvey taxonomy plus `other`.

It does **not** output:

| Not provided | Why |
|---|---|
| Subcategory (the 25) | Not enough training data yet. Subcategories are recorded during labeling for a possible later model. |
| Urgency / priority | The model is not trained for it. |
| An escalation decision | Deciding to escalate is the **validator's** job. The classifier only reports what it predicted and how sure it is. |

## 2. Input (for reference)

- Text = `title + ". " + description`, English.
- Screenshot text from Qwen (`vision_description`) is **not** part of the input.
- Inputs longer than the model limit (256 tokens, provisional) are truncated;
  this is reported in `input_truncated`.

## 3. Labels

Use the `label` **id** in code. Display names may change; ids will not.

| `label` (id) | Display name |
|---|---|
| `network_vpn` | Network & VPN |
| `authentication_access` | Authentication & Access |
| `email_communication` | Email & Communication |
| `software_applications` | Software & Applications |
| `system_os` | System & OS |
| `other` | Other / out of scope |

## 4. Output shape

The classifier adds one object, `classifier`, to the ticket item.
In n8n it is read as `$json.classifier.<field>`.

```json
{
  "request_id": "a3f1c2e4-...",
  "classifier": {
    "schema_version": "1.0",
    "status": "ok",
    "model_name": "solvey-distilbert",
    "model_version": "0.1.0",
    "label": "network_vpn",
    "label_display": "Network & VPN",
    "confidence": 0.87,
    "margin": 0.79,
    "scores": {
      "network_vpn": 0.87,
      "authentication_access": 0.08,
      "email_communication": 0.01,
      "software_applications": 0.01,
      "system_os": 0.02,
      "other": 0.01
    },
    "calibrated": false,
    "input_truncated": false,
    "error": null
  }
}
```

### Field definitions

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | string | Version of this contract. Currently `"1.0"`. |
| `status` | `"ok"` \| `"error"` | `"error"` = no prediction was made (model down, timeout, bad input). |
| `model_name` | string | Which model produced the result. |
| `model_version` | string | Exact trained version, so results can be traced to a training run. |
| `label` | string \| null | Predicted label id (section 3). `null` when `status` is `"error"`. |
| `label_display` | string \| null | Human-readable name of `label`. |
| `confidence` | number 0–1 \| null | Probability of the predicted label. Always equals the highest value in `scores`. |
| `margin` | number 0–1 \| null | `confidence` minus the **second**-highest score. Small margin = the model hesitated between two labels. |
| `scores` | object \| null | Probability for **every** label. All 6 keys always present; values sum to 1 (±0.001). |
| `calibrated` | boolean | `true` once confidence scores have been calibrated on the validation set. Until then, treat `confidence` as a rough signal, not a true probability. |
| `input_truncated` | boolean | `true` if the ticket was too long and its end was cut before classification. |
| `error` | object \| null | When `status` is `"error"`: `{ "code": string, "message": string }`. Otherwise `null`. |

## 5. Rules the validator can rely on

1. If `status` is `"ok"`: `label`, `confidence`, `margin` and `scores` are never `null`.
2. If `status` is `"error"`: `label`, `label_display`, `confidence`, `margin` and `scores` are all `null`.
3. `confidence == max(scores)` and `label` is the key of that maximum.
4. `scores` always contains exactly the 6 label ids from section 3, no others.
5. Values are plain numbers (not strings), rounded to 4 decimals.

## 6. Recommendations for the validator (team agreements, to confirm)

These are **not** classifier behaviour — they are how the team agreed to use its output:

- `status == "error"` → escalate to a human.
- `label == "other"` → always escalate, whatever the confidence.
- `confidence < threshold` → escalate. Threshold is **0.70, provisional**; it will be
  tuned on the validation set after calibration. **Read it from configuration — do not hard-code it.**
- Optionally: small `margin` (e.g. < 0.15, provisional) → treat as ambiguous.
- Deterministic risk rules (passwords, compromised accounts, data loss, security) apply
  **regardless** of the classifier — a confident prediction never makes a sensitive ticket safe.

## 7. More examples

**Out of scope:**

```json
"classifier": {
  "schema_version": "1.0", "status": "ok",
  "model_name": "solvey-distilbert", "model_version": "0.1.0",
  "label": "other", "label_display": "Other / out of scope",
  "confidence": 0.91, "margin": 0.86,
  "scores": { "network_vpn": 0.01, "authentication_access": 0.02, "email_communication": 0.01,
              "software_applications": 0.02, "system_os": 0.03, "other": 0.91 },
  "calibrated": false, "input_truncated": false, "error": null
}
```

**Ambiguous (low margin):**

```json
"classifier": {
  "schema_version": "1.0", "status": "ok",
  "model_name": "solvey-distilbert", "model_version": "0.1.0",
  "label": "email_communication", "label_display": "Email & Communication",
  "confidence": 0.46, "margin": 0.05,
  "scores": { "network_vpn": 0.02, "authentication_access": 0.41, "email_communication": 0.46,
              "software_applications": 0.04, "system_os": 0.02, "other": 0.05 },
  "calibrated": false, "input_truncated": false, "error": null
}
```

**Classifier failed:**

```json
"classifier": {
  "schema_version": "1.0", "status": "error",
  "model_name": "solvey-distilbert", "model_version": "0.1.0",
  "label": null, "label_display": null,
  "confidence": null, "margin": null, "scores": null,
  "calibrated": false, "input_truncated": false,
  "error": { "code": "model_unavailable", "message": "Classifier service did not respond within 30 s" }
}
```

Error codes (initial list): `model_unavailable`, `timeout`, `empty_input`, `internal_error`.

## 8. Changing this contract

Any change to field names, types or labels increases `schema_version` and must be
agreed with the validator owner before merging.
