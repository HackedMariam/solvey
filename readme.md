# Solvey — Agentic AI for IT Support

**From technical issues to actionable solutions.**

Solvey is an AI-powered IT support assistant designed to help users diagnose and resolve technical issues through intelligent retrieval, multimodal analysis, and collaborative AI agents.

Combining **Retrieval-Augmented Generation (RAG), deep learning, and agentic workflows**, Solvey transforms historical support tickets, technical documentation, and issue screenshots into actionable troubleshooting guidance.

## ✨ Key Features

- **🔎 Intelligent Issue Analysis** — Understands user-reported technical problems and identifies relevant error information.
- **📚 Knowledge Retrieval (RAG)** — Retrieves relevant solutions from historical support tickets, bug reports, and technical documentation.
- **🖼️ Multimodal Analysis** — Leverages screenshots and visual error evidence to support issue diagnosis.
- **🤖 Agentic AI Workflow** — Coordinates specialized agents for issue classification, retrieval, diagnosis, and solution generation.
- **🛠️ Guided Troubleshooting** — Provides contextual, step-by-step recommendations to help users resolve technical issues.
- **✅ Resolution Validation** — Evaluates user feedback to determine whether a proposed solution worked and supports alternative recommendations when necessary.

## 🏗️ How It Works

1. **Issue Submission** — The user describes a technical problem and optionally provides a screenshot.
2. **Issue Understanding** — The system extracts relevant information and classifies the issue.
3. **Knowledge Retrieval** — The RAG pipeline searches the knowledge base for similar incidents and relevant solutions.
4. **Agent Collaboration** — Specialized agents analyze the evidence and formulate a troubleshooting strategy.
5. **Solution Generation** — Solvey generates grounded, actionable recommendations based on the retrieved knowledge.
6. **Feedback & Validation** — The user reports the outcome, allowing the workflow to validate the resolution or explore alternative fixes.

## 🧠 Technical Approach

Solvey explores the integration of:

- **Agentic AI** for task decomposition, orchestration, and specialized reasoning.
- **Retrieval-Augmented Generation (RAG)** for knowledge-grounded responses.
- **Deep Learning** for semantic understanding and relevant information retrieval.
- **Multimodal AI** for interpreting technical screenshots alongside textual descriptions.
- **Workflow Automation** for coordinating the support process and connecting its components.

## 🗂️ Knowledge Sources

The system is designed to leverage structured and unstructured IT support data, including:

- Historical support tickets and their resolutions.
- Bug reports and troubleshooting discussions.
- Technical documentation and knowledge-base articles.
- Screenshots associated with technical issues.

## 📊 Dataset

The current dataset is scraped from **Stack Overflow** (via the Stack Exchange API) by `scrape_so.py` and `scrape_so copy.py`. It contains IT support bug reports, their error screenshots, and — in the extended variant — the accepted or top-voted resolution.

**What we have:**

- **100 bug reports** distributed across **5 categories** and **25 subcategories**.
- **154 error screenshots** (`.png`, `.jpg`, `.gif`) downloaded alongside the CSV.
- **80 of 100** reports have an answer: **37 accepted**, **43 top-voted**, and **20 unresolved**.

**Categories (25 subcategories each mapped to search queries):**

| Category | Reports |
| --- | --- |
| Software & Applications | 24 |
| Network & VPN | 22 |
| System & OS | 21 |
| Authentication & Access | 17 |
| Email & Communication | 16 |

**Two dataset variants:**

| Folder | Script | Description |
| --- | --- | --- |
| `so_bug_data/` | `scrape_so.py` | Base report + screenshots (no resolution). |
| `with resolution/` | `scrape_so copy.py` | Same reports enriched with the resolution/answer. |

**Fields — `so_bug_data/results.csv`:**
`category`, `subcategory`, `question_id`, `title`, `link`, `score`, `creation_date`, `image_count`, `image_files`, `body_html`

**Fields — `with resolution/results.csv`** (adds): `tags`, `view_count`, `answer_count`, `image_urls`, `description`, `resolution_status` (`accepted` / `top_voted` / `none`), `has_answer`, `answer_id`, `answer_score`, `answer_link`, `answer_owner`, `answer_creation_date`, `resolution`, `answer_body_html`

Each image is named `so_<question_id>_<index>.<ext>` and referenced from the `image_files` column, linking screenshots to their issue. This gives the project a **multimodal** corpus: text (issue description + resolution) paired with visual error evidence, plus a supervision signal (the resolution) for retrieval and validation experiments.

## 🎯 Project Goals

- Reduce the time required to diagnose and resolve common IT issues.
- Improve the relevance and reliability of AI-generated troubleshooting guidance.
- Reuse knowledge from previously resolved incidents.
- Explore how agentic workflows can automate multi-step IT support tasks.
- Evaluate retrieval quality, solution relevance, and resolution effectiveness.

## 🚀 Project Status

**In development.**

Solvey is being developed as an Advanced Deep Learning project exploring RAG, multimodal AI, prompt engineering, agentic workflows, and automation for intelligent IT support.

## 🛣️ Roadmap

- [ ] Prepare and clean IT support datasets.
- [ ] Build the semantic retrieval and RAG pipeline.
- [ ] Implement issue classification and specialized agents.
- [ ] Integrate screenshot-based issue analysis.
- [ ] Orchestrate the end-to-end support workflow.
- [ ] Develop an interactive user interface.
- [ ] Evaluate retrieval and answer quality.
- [ ] Test resolution validation and fallback strategies.

## 👥 Team

Developed as part of an Advanced Deep Learning academic project.

Mariam Ben Abdallah, Arij Chaaouri, Meriem Gharbi, Norhene Mraieh, Mohamed Mahmoud, Zied Hechmi. 