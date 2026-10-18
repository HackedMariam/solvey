# Phase 1 corpus sources and attribution

## Microsoft support articles

The selected HTML-era support articles are published as Markdown in the
public repository [MicrosoftDocs/SupportArticles-docs](https://github.com/MicrosoftDocs/SupportArticles-docs).
The sparse checkout is pinned at commit
`2bc340377700b726eecb79f9dcca71dfa8d6a78e` as inspected on 2026-10-17.
The repository's root `LICENSE` is Creative Commons Attribution 4.0
International (CC BY 4.0); `LICENSE-CODE` is the MIT License. The corpus
selector records CC BY 4.0 and attributes each article to the repository,
including the pinned commit. Code samples remain subject to the repository's
MIT notice where applicable. The ingestion set contains Markdown only and
does not copy linked image assets or other media; review `ThirdPartyNotices.md`
before using any such asset.

The selected folders are Outlook classic for Windows, Exchange Online,
Microsoft 365 administration, Office client, Entra identity, and Windows
client networking, update, setup/driver, application-management, and hardware
driver support. `scripts/prepare_corpus.py` applies deterministic topic
filters, copies the selected Markdown under `data/corpus/<category>/`, and
writes the source URL, category, license, and attribution to
`data/corpus_manifest.csv`.

### Repository-wide Outlook Outbox search

A GitHub code search scoped to the complete `MicrosoftDocs/SupportArticles-docs`
repository (not only the sparse checkout) found these directly relevant
articles. Three were added from the pinned commit and classified as
`email_communication`; each is attributed under the repository's CC BY 4.0
license in the manifest:

- [Email stays in Outbox until manually send or receive](https://github.com/MicrosoftDocs/SupportArticles-docs/blob/2bc340377700b726eecb79f9dcca71dfa8d6a78e/Outlook/classic-outlook-for-windows/synchronization/email-stays-in-outbox-until-manually-send-or-receive.md)
- [Emails remain in Outbox for at least one minute](https://github.com/MicrosoftDocs/SupportArticles-docs/blob/2bc340377700b726eecb79f9dcca71dfa8d6a78e/Outlook/classic-outlook-for-windows/email-management/emails-remain-in-outbox-deferred-delivery-rule.md)
- [Email messages are stuck in Outbox in Outlook 2016 for Mac](https://github.com/MicrosoftDocs/SupportArticles-docs/blob/2bc340377700b726eecb79f9dcca71dfa8d6a78e/Outlook/legacy-outlook-for-mac/send-receive-emails/email-stuck-in-outbox-outlook-2016-mac.md)

## Rejected dataset

`UmerSajid/IT-Troubleshooting-Dataset` is listed in the manifest with
`status=rejected`. The Hugging Face dataset server reports 10,500 rows and
11 columns. The dataset card says that the scenarios were curated with
AI-assisted content generation and review. Sampled rows include repeated
`Variant N` scenarios with identical symptom/solution text and generic causes.
Neither the Hugging Face metadata nor its README declares a license. At the
user's direction, no rows are copied or indexed.

Five sampled rows and the proposed category mapping:

| ID | Dataset category | Issue sample | Proposed mapping |
| --- | --- | --- | --- |
| 1 | Cloud Computing | AWS instance not starting - Variant 30 | Exclude: outside the five-category internal support scope. |
| 1001 | Mobile Devices | iPhone not charging - Variant 12 | Exclude: mobile-device support is outside this corpus. |
| 2501 | Network | Slow internet - Variant 31 | `network_vpn`. |
| 5001 | Software | Blue screen error - Variant 33 | `system_os` because the issue is a Windows blue screen. |
| 7501 | Microsoft Office | Excel formula error - Variant 41 | `software_apps`; Outlook/email issues would map to `email_communication`. |

This is a mapping proposal for documenting the rejected source, not a mapping
used by the corpus builder.

## PDF sources included for parser validation

Ten PDFs are stored under `data/corpus/network_vpn/pdf/`, within the requested
limit. The NIST publication is marked public domain as a U.S. government work.
The nine university guides use the project-approved manifest attribution
`licence: non précisée, usage académique attribué`; this is not a claim that
their publishers issued an open license. Source page URLs, source type,
category, and attribution are recorded per file in `data/corpus_manifest.csv`.

| Document | Publisher | Topic | Source |
| --- | --- | --- | --- |
| NIST SP 800-46 Rev. 2 | NIST | Remote access, telework, BYOD | [PDF](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-46r2.pdf) |
| FAMU eduroam guide | Florida A&M University | eduroam | [PDF](https://www.famu.edu/administration/campus-services/information-technology-services/about-its/pdf/FAMU-Eduroam_27Jan2016.pdf) |
| GW eduroam wireless guide | George Washington University | eduroam | [PDF](https://internationalservices.gwu.edu/sites/g/files/zaxdzs6431/files/downloads/Eduroam%20Wireless%20Guide%20JUNE%202015%20%28MC%29.pdf) |
| iOS eduroam setup | San Jose State University | Wi-Fi / eduroam | [PDF](https://www.sjsu.edu/it/docs/connectivity/wifi_ios.pdf) |
| Android eduroam setup | Texas Southmost College | Wi-Fi / eduroam | [PDF](https://tsc.edu/images/Departments/helpdesk/eduroam-android.pdf) |
| CUNY eduroam guide | CUNY Graduate Center | Wi-Fi / eduroam | [PDF](https://www.gc.cuny.edu/sites/default/files/2023-10/How-do-I-connect-to-eduroam-Wifi-Network.pdf) |
| Purdue VPN connection | Purdue University | VPN | [PDF](https://www.purdue.edu/advisors/documents/connect-virtual-private-network.pdf) |
| Cisco VPN client setup | University of Florida | VPN | [PDF](https://isdoc.research.ufl.edu/wp-content/uploads/CiscoVPNClient.pdf) |
| VPN instructional guide | Prairie View A&M University | VPN | [PDF](https://www.pvamu.edu/cite/wp-content/uploads/sites/190/2020/10/Accessing-VPN-Instructional-Guide-10.19.20.pdf) |
| VPN access procedure and troubleshooting | City College of New York | VPN | [PDF](https://broadcast.ccny.cuny.edu/lyris2022/Docs/VPN_Access_Configuration.pdf) |

The NIST validation recovered eight tables from 53 pages; Table 5-1 was
extracted as Markdown on PDF page 43. Its source PDF contains glyphs that
extract as replacement characters, so check text fidelity before relying on
those passages. Docling 2.140.0 was installed in an isolated Python 3.11
environment in about 12 minutes, but its first conversion spent six more
minutes initializing layout/OCR models without completing. The parser uses
PyMuPDF4LLM 1.28.2 instead. PyMuPDF4LLM is dual-licensed under
AGPL-3.0-or-later or an Artifex commercial license; evaluate that license
before distributing the project. `pypdf` remains the PDF loader for baseline
A only. Figure descriptions remain deferred; extracted local image paths may
be retained without embedding image bytes or calling a vision model.
