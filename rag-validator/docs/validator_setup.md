# Brancher le Validator final dans n8n

Le sous-workflow importable est [`n8n/validator.json`](../n8n/validator.json).
Il reçoit le dossier complet inchangé, appelle le service Python final
Validator et retourne son verdict et ses contrôles déterministes. Le Validator
est le dernier garde-fou dans **les deux parcours** : avant l'envoi d'une
réponse et avant la création d'un ticket.

## Préparer le service Validator

1. Installer les dépendances depuis `rag-validator` avec
   `python -m pip install -r requirements.txt`.
2. Configurer `GROQ_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY` dans `.env`;
   les identifiants restent côté service, jamais dans le workflow n8n.
3. Depuis la racine de `rag-validator`, démarrer le service :

   ```powershell
   uvicorn src.validator.api:app --host 0.0.0.0 --port 8000
   ```

4. Vérifier `GET /health`. Le service utilise dans l'ordre Groq
   `openai/gpt-oss-120b`, Gemini `gemini-3.8-flash`, puis OpenAI
   `gpt-4o-mini`. Il journalise uniquement le fournisseur/modèle sélectionné,
   jamais les clés.
5. Le service réutilise `it-support-langgraph/itsupport/guardrails.py` et
   `taxonomy.yaml`. Dans un checkout où ce projet frère n'est pas placé à côté
   de `rag-validator`, définir `IT_SUPPORT_GUARDRAILS_PATH` et
   `IT_SUPPORT_TAXONOMY_PATH` côté service vers les fichiers partagés.

En déploiement, l'URL doit être joignable depuis n8n. Si n8n et le Validator
tournent dans le même réseau Docker, utiliser le nom DNS du service, par
exemple `http://validator-api:8000/validate`; ne pas laisser l'adresse
placeholder ou exposer le port sans authentification/règle réseau appropriée.

## Importer et configurer le sous-workflow

1. Dans n8n, **Workflows → Import from File**, sélectionner
   `n8n/validator.json`.
2. Dans **Run Deterministic Checks and Judge**, remplacer
   `http://YOUR-VALIDATOR-HOST:8000/validate` par l'URL privée et joignable du
   service.
3. Enregistrer le workflow et le laisser inactif; le workflow principal
   l'appellera avec **Execute Sub-workflow**.
4. L'entrée est un seul dossier JSON complet. Utiliser
   [`examples/dossier_answer.json`](../examples/dossier_answer.json) ou
   [`examples/dossier_ticket.json`](../examples/dossier_ticket.json) pour
   tester chacun des modes.
5. La réponse contient `verdict`, `failure_type`, `target_stage`,
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
