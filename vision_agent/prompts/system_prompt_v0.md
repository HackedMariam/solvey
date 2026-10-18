# Intake prompt v0 — baseline

**Role:** Describe a screenshot for the user.
**Techniques:** role prompting, zero-shot.
**Status:** deprecated.

## Prompt

```text
You are a helpful assistant. Describe this screenshot in detail and explain what the user should do to fix the problem.
```

## Observed failures

- Produced prose instead of structured data.
- Diagnosed the issue and proposed fixes; the triage agent needs observations, not answers.
- Invented details that were not visible.
- Did not separate image evidence from the user's text.
- No `missing_information`, `uncertainties`, or confidence.

## Fix

Replaced by `system_prompt_v1.md`: observation-only JSON, explicit field contract,
source separation, missing-info extraction, and confidence.
