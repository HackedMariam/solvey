# Validator final autonome dans n8n

Le sous-workflow importable [`n8n/validator.json`](../n8n/validator.json)
reçoit le dossier complet et effectue les contrôles en Code JavaScript, puis
appelle directement les APIs LLM avec des nœuds HTTP Request. Il ne dépend
d'aucun service FastAPI/Python ni d'une URL Validator externe. La version
Python dans `src/validator/service.py` reste la référence serveur et
d'évaluation; les règles embarquées dans n8n sont comparées à celle-ci par
`eval/validator_node_parity.py`.

## Préparer n8n

1. Importer `n8n/validator.json`.
2. Créer/réassigner les credentials `Header Auth` dans les trois nœuds HTTP :
   Groq (`Authorization: Bearer …`, modèle `openai/gpt-oss-120b`), Gemini
   (`x-goog-api-key`, modèle `gemini-3.8-flash`), et OpenAI
   (`Authorization: Bearer …`, modèle `gpt-4o-mini`). Les valeurs ne sont
   stockées que dans le coffre credentials de n8n.
3. Le nœud `Deterministic Validator Checks` exécute les vérifications locales.
   Un verdict déterministe termine le sous-workflow sans appeler de LLM;
   autrement Groq est tenté, puis Gemini et OpenAI si l'appel échoue ou ne
   renvoie pas de JSON. Le nœud final applique les règles de décision et les
   limites de boucle.
4. Tester avec `examples/dossier_answer.json` et
   `examples/dossier_ticket.json`. Un dossier ticket doit être validé avant
   tout nœud Jira.
5. Pour régénérer l'export après modification des règles JavaScript, lancer
   `python scripts/build_validator_n8n.py` depuis `rag-validator`.
6. Vérifier la parité sans appels LLM réels avec
   `python -m eval.validator_node_parity`; cette suite utilise des verdicts
   déterministes de fixture identiques côté Python et Node.

Le dépôt inclut ses fichiers de taxonomie et de guardrails dans
[`itsupport/`](../itsupport/). Un checkout frère n'est pas requis.

## Importer et configurer le sous-workflow

1. Dans n8n, **Workflows → Import from File**, sélectionner
   `n8n/validator.json`.
2. Re-sélectionner les credentials `Header Auth` **Groq API**,
   **Google Gemini API key** et **OpenAI Validator API** dans leurs nœuds
   HTTP Request respectifs.
3. Enregistrer le workflow et le laisser inactif; le workflow principal
   l'appellera avec **Execute Sub-workflow**.
4. L'entrée est un seul dossier JSON complet. Utiliser
   [`examples/dossier_answer.json`](../examples/dossier_answer.json) ou
   [`examples/dossier_ticket.json`](../examples/dossier_ticket.json) pour
   tester chacun des modes.
5. La sortie contient `verdict`, `failure_type`, `target_stage`,
   `stage_checks`, `feedback_for_stage` et `reason`. Le client doit traiter
   explicitement les verdicts; ne pas envoyer de réponse/créer de ticket sur
   `regenerate`, `retry_retrieval`, `clarify` ou `escalate`.

## Points d'appel dans le workflow principal

### Mode answer — avant l'envoi utilisateur

Après le Writer/Résolution, assembler le dossier avec `mode: "answer"` :
texte utilisateur et langue, sorties Vision et Triage, sortie retrieval
`{query, chunks, attempts}`, `draft_answer`, et compteurs de tentatives.
Appeler **Final Validator**.

- `approve`: envoyer le `draft_answer.final_message` (ou le texte composé du
  résumé et des étapes si `final_message` est absent).
- `retry_retrieval`: transmettre `feedback_for_stage` au RAG, incrémenter
  `attempt_counts.retry_retrieval` et relancer une seule fois.
- `regenerate`: transmettre le feedback au Writer, incrémenter
  `attempt_counts.regenerate` et regénérer une seule fois.
- `clarify`: envoyer la question de clarification à l'utilisateur.
- `escalate`: ne pas fournir la solution automatique; assembler le dossier
  mode ticket et passer à l'appel ticket ci-dessous.

### Mode ticket — avant l'outil de création de ticket

Après l'agent d'escalade, assembler un dossier avec `mode: "ticket"`,
conserver les sorties amont, placer la sortie d'Escalade dans `draft_ticket`,
et transmettre les compteurs d'essais actualisés. Appeler **Final Validator**
avant tout nœud Jira/ServiceNow/outil ticketing.

- `approve`: créer le ticket à partir du `draft_ticket` validé.
- `regenerate` avec `incomplete_ticket` ou `leak`: ne pas appeler l'outil;
  redemander une fois un ticket complet et sans secret, puis revalider.
- `escalate`: bloquer la création automatique et demander une vérification
  humaine.
- `retry_retrieval` ou `clarify`: router selon `target_stage` et le feedback;
  ne jamais les traiter comme une approbation.

Les secrets détectés sont redigés avant la réponse Validator; le résultat
`leak` signale qu'un contenu a été supprimé. Le contrôle de sécurité
déterministe a priorité sur le LLM. La décision de non-réponse est prise par
le Validator à partir des passages, pas par le seuil bas du retriever.
