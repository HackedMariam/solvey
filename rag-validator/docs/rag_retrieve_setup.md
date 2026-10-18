# Importer et configurer `RAG Retrieve` dans n8n

Le workflow importable est [`n8n/rag_retrieve.json`](../n8n/rag_retrieve.json).
Il implémente le contrat de [`contracts.md`](contracts.md) : collection
`it_kb_blocks`, embeddings OpenAI 1 536 dimensions, top-k 5, filtre de
catégorie, secours sans filtre si moins de deux résultats et cutoff Qdrant
0,30. Ce cutoff ne décide pas d'une abstention; cette décision revient au
Validator.

## Pré-requis

- Une instance n8n pouvant joindre l'API Qdrant Cloud.
- Une clé OpenAI autorisée à appeler l'API Embeddings.
- Une clé API Qdrant avec droits de lecture sur `it_kb_blocks`.
- La collection `it_kb_blocks` créée avec vecteurs cosine de 1 536 dimensions.

## Import et configuration des identifiants

1. Dans n8n, ouvrir **Workflows → Import from File** et sélectionner
   `n8n/rag_retrieve.json`.
2. Dans **Credentials**, créer ou choisir un identifiant **OpenAI API**.
   Ouvrir le nœud **OpenAI Query Embedding** et sélectionner cet identifiant.
   Le modèle, la dimension et le format d'embedding sont définis dans la
   requête : `text-embedding-3-small`, 1 536 dimensions, vecteurs `float`.
3. Créer un identifiant **Header Auth** nommé par exemple `Qdrant API Key`,
   avec le nom d'en-tête `api-key` et la clé privée du cluster comme valeur.
   Sélectionner cet identifiant dans **Qdrant Search (category)** et
   **Qdrant Search (fallback)**. Ne jamais coller la clé dans le JSON du
   workflow ou dans un champ d'en-tête en clair.
4. Dans chacun des deux nœuds Qdrant, remplacer
   `https://YOUR-QDRANT-CLUSTER` par l'URL HTTPS du cluster, sans barre oblique
   finale. Conserver le chemin
   `/collections/it_kb_blocks/points/query`.
5. Enregistrer et vérifier que les nœuds OpenAI et Qdrant n'affichent plus
   d'avertissement d'identifiant manquant. Laisser ce workflow inactif; il est
   appelé par le workflow parent via Execute Workflow.

## Fonctionnement nœud par nœud

1. **Execute Workflow Trigger** reçoit `query`, `category` et éventuellement
   `top_k` en entrée.
2. **OpenAI Query Embedding** envoie uniquement le texte de `query` à
   l'endpoint OpenAI `/v1/embeddings`, avec le modèle figé et 1 536 dimensions.
3. **Qdrant Search (category)** recherche dans `it_kb_blocks`, limite à cinq
   points, renvoie le payload et applique `score_threshold: 0.30`. Si
   `category` n'est pas vide, il filtre sur l'égalité exacte du champ payload
   `category`; si `category` vaut `null` ou est absent, la requête est
   directement non filtrée.
4. **Need Unfiltered Fallback?** vérifie si une catégorie était fournie et si
   moins de deux points ont été renvoyés. La branche vraie poursuit la
   recherche sans filtre; la branche fausse formate directement les résultats
   principaux.
5. **Qdrant Search (fallback)** répète la recherche sur la même collection et
   avec le même cutoff/top-k, mais sans filtre de catégorie. Cette réponse
   remplace les résultats filtrés insuffisants.
6. **Format S1-S5 Response** transforme les payloads en objets `chunks`
   conformes au contrat, attribue les citations `S1` à `S5` dans l'ordre des
   scores et règle `used_filter` à `false` si la recherche était non filtrée
   ou si le secours a été utilisé.

Un cutoff de 0,30 écarte seulement des correspondances très faibles. Sur le
jeu de phase 2, les meilleurs scores de B filtré étaient tous supérieurs ou
égaux à 0,4053; ce cutoff ne rejetait donc aucun des trois cas sans réponse.
Le Validator doit évaluer l'appui documentaire et décider explicitement de
répondre ou de s'abstenir.

## Exemple d'appel de test

Dans un workflow parent, ajouter **Execute Sub-workflow**, choisir `RAG
Retrieve`, et transmettre cet objet :

```json
{
  "query": "Outlook messages stay in the Outbox and are not sent",
  "category": "email_communication",
  "top_k": 5
}
```

Avec un filtre produisant au moins deux points, la sortie respecte cette
forme (les scores, contenus et sources sont fournis par Qdrant) :

```json
{
  "chunks": [
    {
      "id": "S1",
      "text": "Document: ...",
      "table_raw": null,
      "title": "Email stays in the Outbox folder until you manually initiate a send/receive operation in Outlook",
      "section": "Troubleshooting",
      "page": null,
      "source": "corpus/email_communication/microsoftdocs/Outlook/classic-outlook-for-windows/synchronization/email-stays-in-outbox-until-manually-send-or-receive.md",
      "url": "https://learn.microsoft.com/...",
      "category": "email_communication",
      "score": 0.73
    }
  ],
  "used_filter": true
}
```

Pour vérifier le secours, passer une catégorie valide mais absente de la
collection ou une catégorie retournant zéro ou un point. Le workflow doit
exécuter **Qdrant Search (fallback)** et produire `used_filter: false`.
