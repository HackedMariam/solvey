# Solvey — Ticket Labeling Guidelines

**Version:** 1.0 — approved by Mohamed Mahmoud on 2026-10-18 (team review still welcome)
**Owner:** Mohamed Mahmoud
**Used for:** labeling the test set, reviewing generated training tickets, writing the generation prompt.

Items marked **[DECIDED 2026-10-18]** were open proposals, approved in v1.0.

---

## 1. The task

Read one support ticket (title + description) and assign **exactly one** label:
the problem the person **needs fixed**.

Also record the **subcategory** (section 4). The classifier is not trained on
subcategories yet, but recording them now lets us train a finer model later
without relabeling.

Do **not** label urgency or priority.

## 2. The 6 labels

| Label id | Name | Covers |
|---|---|---|
| `network_vpn` | Network & VPN | No or unstable internet, Wi-Fi, campus network, DNS, VPN connection |
| `authentication_access` | Authentication & Access | Passwords, locked accounts, MFA, permissions, access to restricted resources |
| `email_communication` | Email & Communication | Sending/receiving email, mailbox full, email client setup, calendar, Teams/chat, video calls |
| `software_applications` | Software & Applications | A specific program that won't install, launch, update, or behaves wrongly |
| `system_os` | System & OS | The device or operating system as a whole: Windows/Linux/macOS errors, OS updates, drivers, slowness, hardware, **printers** |
| `other` | Other / out of scope | Not an IT problem, or an IT topic Solvey does not support |

### Examples

**`network_vpn`**
- "wifi in the library keeps disconnecting every 5 min"
- "VPN says 'connection timed out' when I try to reach the uni portal from home"
- "Internet works on my phone but not on my laptop, websites don't load"

**`authentication_access`**
- "my account got locked after I typed the wrong password 3 times"
- "I don't get the MFA code on my phone anymore since I changed phone"
- "I can't open the shared research drive, it says access denied"

**`email_communication`**
- "Outlook says my mailbox is full and I can't send anything"
- "emails from my professor aren't arriving, not even in spam"
- "Teams meeting has no sound for the other participants"

**`software_applications`**
- "MATLAB installer stops at 80% with error 1603"
- "SPSS crashes every time I open a dataset"
- "Moodle desktop app won't start after the update"

**`system_os`**
- "laptop is super slow since the Windows update yesterday"
- "blue screen with DRIVER_IRQL_NOT_LESS_OR_EQUAL when I plug in my headset"
- "the printer on floor 2 shows 'paper jam' but there's no paper stuck"

**`other`**
- "the projector cable in room B12 is missing"
- "how do I pay my registration fees?"
- "my Docker container exits with code 137 on the lab server" (unsupported — see 3.2)

## 3. Decision rules

### 3.1 When a ticket fits more than one label

Apply the rules **in this order** and stop at the first that matches:

1. **Not IT, or unsupported** → `other`.
2. **The person's account itself** is the problem — wrong/expired password, locked
   account, MFA, missing permission — → `authentication_access`, **whatever service** it is for.
   **[DECIDED 2026-10-18 — see 3.3]**
3. **No connectivity**: several apps or websites fail because the connection fails → `network_vpn`.
4. **An email, calendar or communication tool** (Outlook, webmail, Teams, Zoom) → `email_communication`,
   even if it crashes or won't start.
5. **One specific application** → `software_applications`.
6. **The whole device, the OS, a driver, hardware or a printer** → `system_os`.

If two problems are described, label the one the person asks to be fixed, or the
first one mentioned if unclear. Note the second one in `notes`.

### 3.2 What counts as `other`

- Not IT: facilities (projectors, heating, furniture), fees, HR, timesheets,
  purchase orders, registration, general questions.
- IT but unsupported: Docker/containers, programming or code errors, development
  servers, requests to buy equipment. **[DECIDED 2026-10-18 — revisit if university IT supports lab servers]**
- Too vague to tell, **only if** no label can reasonably be chosen
  (e.g. "it doesn't work"). Prefer a real label when there is any clue.

### 3.3 Known conflict in the taxonomy **[DECIDED 2026-10-18]**

The taxonomy has authentication subcategories in three places:
*VPN authentication failure* (Network), *Email authentication failure* (Email),
and *Wrong/expired password* / *MFA* (Authentication). Without a rule, labelers will disagree.

**Rule:**
- The **account** is the problem (wrong password, locked, expired, MFA, no permission)
  → `authentication_access`, even for VPN or email.
- The account is fine, but **the service's own login setup** fails
  (VPN profile/certificate error, email client "authentication failed" after changing
  server settings) → that service's label (`network_vpn` / `email_communication`).
- If you cannot tell which → `authentication_access`.

### 3.4 Label what is written, not what you guess

Do not use your own diagnosis. "Laptop can't open any website" is `network_vpn`
even if you suspect a driver. The label describes the **reported problem**.

## 4. Subcategories (record, do not train on yet)

| Label | Subcategories |
|---|---|
| `network_vpn` | VPN authentication failure · VPN connection failure · Wi-Fi connectivity issue · DNS configuration error · Internet connection problem |
| `authentication_access` | Wrong/expired password · Account locked · MFA authentication failure · Permission denied · Access to restricted resource |
| `email_communication` | Cannot send email · Cannot receive email · Email authentication failure · Mailbox storage full · Email client configuration problem |
| `software_applications` | Application won't launch · Application crash · Installation failure · Application configuration error · Software update failure |
| `system_os` | OS error (Windows/Linux/macOS) · Driver problem · OS update failure · System performance issue · Hardware-related error (incl. printers) |
| `other` | Not IT · Unsupported IT · Too vague |

Changes from the original taxonomy: "Windows/system error" → "OS error (Windows/Linux/macOS)";
printers added under Hardware-related error; `other` subcategories added.

## 5. Edge cases

| Ticket | Label | Why |
|---|---|---|
| "Outlook won't open" | `email_communication` | Rule 4: communication tool, even if it's a launch problem |
| "Mailbox almost full" | `email_communication` | Mailbox storage full |
| "Forgot my password for Moodle" | `authentication_access` | Rule 2: the account |
| "Moodle shows error 500" | `software_applications` | One application misbehaving |
| "Can't log in to VPN, password rejected" | `authentication_access` | Rule 2 (3.3) |
| "VPN connects then drops after 2 min" | `network_vpn` | Connection problem |
| "No internet on any device in my dorm room" | `network_vpn` | Connectivity |
| "Printer prints blank pages" | `system_os` | Printers → Hardware-related error |
| "Need admin rights to install Python" | `authentication_access` | Permission denied |
| "Python script throws KeyError" | `other` | Programming help — unsupported |
| "Linux laptop won't boot after update" | `system_os` | OS update failure |
| "Docker won't start on my laptop" | `other` | Unsupported **[DECIDED 2026-10-18]** |
| "Screen flickers" | `system_os` | Hardware/driver |
| "Teams says I'm not part of the organisation" | `authentication_access` | Account/permission problem |
| "it doesn't work, please help" | `other` | Too vague — nothing to go on |
| Ticket not in English | **Do not label** | Excluded from the dataset; Solvey escalates non-English tickets **[DECIDED 2026-10-18]** |

## 6. Procedure

**Test set**
1. Two people label each ticket **independently**, without seeing each other's labels.
2. Compare. Where they disagree, discuss and record the agreed `final_label`.
3. Report agreement (percent agreement and Cohen's kappa) in the project report.
4. If a disagreement reveals a missing rule, add it to section 5 and bump the version.

**Training set (generated or public)**
- One person reviews each ticket: keep, fix the label, or delete.
- Delete duplicates, near-duplicates, non-English tickets and tickets that contain
  real personal data (names, emails, student IDs).

**Never** move tickets between the test set and the training set.

## 7. File format

CSV, UTF-8, one ticket per row.

| Column | Required | Content |
|---|---|---|
| `ticket_id` | yes | Unique id, e.g. `gen-000123`, `kaggle-04512`, `team-mm-017` |
| `title` | no | Ticket title (may be empty) |
| `description` | yes | Ticket text |
| `label` | yes | One label id from section 2 (test set: the agreed final label) |
| `subcategory` | yes | From section 4 |
| `source` | yes | `generated` · `kaggle_it_tickets` · `hf_customer_support` · `team_written` · `university_real` |
| `source_ref` | no | Original row id / generator model name |
| `labeler` | yes | Initials (test set: `label_a`, `label_b` columns as well) |
| `notes` | no | Second problem, doubts, rule applied |
