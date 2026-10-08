# Prompt de génération de questions

Ce prompt sert à faire générer des questions par une IA, au format attendu par la banque de questions jev. Remplacez `[NOMBRE]`, `[THÈME]` et la difficulté, puis collez le JSON obtenu dans **Gérer la banque de questions** et cliquez sur **Enregistrer les questions**.

- **Coller remplace toute la banque.** La zone JSON contient la banque entière. Pour ajouter des questions, insérez les nouveaux objets dans le tableau existant, juste avant le `]` final, en ajoutant une virgule.
- **Testez quelques questions avant de jouer**, surtout les questions sur des personnes. Dans le testeur, essayez un prénom seul, une mauvaise réponse proche et une faute de frappe. Si un piège passe, ajoutez ce cas au critère faux.

## Pourquoi la forme « La réponse est fausse si elle : … »

Trois rédactions du critère faux ont été comparées avec `jev-latest`, au seuil de 0,8, sur des pièges réels : prénoms seuls, fautes de frappe sur un autre nom, nombres proches écrits en lettres. Chaque rédaction a été évaluée deux fois.

| Rédaction du critère faux | Résultat |
| --- | --- |
| Liste courte (« Tout autre joueur que George Weah, comme Samuel Eto'o… ») | Le prénom seul « George » est accepté jusqu'à 0,96, et « Steffi » jusqu'à 0,98 |
| Critère positif (« La réponse ne contient pas le nom Weah… ») | Les prénoms seuls restent acceptés, avec une marge négative ou faible |
| **Cas explicites (« La réponse est fausse si elle : … ; … ; … »)** | **1 erreur sur 78 évaluations** sur la banque de test, avec une marge positive sur chaque question |

Le critère vrai est aussi annoncé aux joueurs comme « la bonne réponse ». Il doit donc rester une réponse courte, et les nuances de notation vont dans le critère faux.

## Prompt

````text
Tu génères des questions de quiz en français pour un jeu sur WhatsApp. Les joueurs répondent librement par un court message. Chaque réponse est notée automatiquement par un modèle de décision (jev). Il reçoit la question, un critère « vrai », un critère « faux » et la réponse du joueur, et renvoie la probabilité que la réponse soit correcte. La réponse est acceptée si cette probabilité est d'au moins 0,8.

TÂCHE
Génère [NOMBRE] questions sur le thème [THÈME], de difficulté [FACILE / MOYENNE / DIFFICILE].

FORMAT DE SORTIE — STRICT
- Réponds UNIQUEMENT avec un tableau JSON valide. Pas de texte avant ou après, pas de bloc ```json, pas de commentaires.
- Chaque élément contient exactement ces 5 champs, et aucun autre (tout champ inconnu fait rejeter la banque entière) :
  {
    "id": string,
    "question": string,
    "criteria": { "true": string, "false": string },
    "aliases": [string, ...],
    "explanation": string
  }

RÈGLES PAR CHAMP

1. "id"
   - Uniquement des lettres non accentuées, des chiffres, « - » ou « _ », au maximum 80 caractères.
   - Il est unique dans le tableau et décrit la question. Préfixe-le par le thème, par exemple « sport-decathlon-nombre-epreuves ».

2. "question" (au maximum 2000 caractères)
   - Elle doit avoir une seule bonne réponse, factuelle et vérifiable.
   - La réponse doit pouvoir s'écrire en quelques mots : un nom, un lieu, un nombre, une date. Évite les questions qui demandent une liste ou une phrase.
   - Si la réponse dépend du moment, date la question (par exemple « en 2024 »), sinon elle deviendra fausse avec le temps.
   - La question est envoyée telle quelle aux joueurs. Elle doit donc être claire, sans ambiguïté et sans indice qui donne la réponse.

3. "criteria.true" (au maximum 500 caractères)
   - C'est la bonne réponse, sous sa forme la plus courante, par exemple « George Weah », « 24 secondes » ou « La Nouvelle-Zélande ».
   - IMPORTANT : ce texte est annoncé aux joueurs comme « la bonne réponse ». Il ne doit contenir AUCUNE consigne de notation (pas de « y compris… » ni « accepter… »). Juste la réponse.

4. "criteria.false" (au maximum 500 caractères) — LE CHAMP LE PLUS IMPORTANT
   Le modèle a tendance à accepter trop facilement : une réponse partielle, une faute de frappe sur un AUTRE nom, ou un nombre proche. C'est ce champ qui l'empêche de se tromper. Une formulation vague comme « Toute autre réponse » donne de mauvais résultats.

   Utilise TOUJOURS cette structure, dont l'efficacité a été mesurée :
   « La réponse est fausse si elle : [cas 1] ; [cas 2] ; [cas 3]. »

   Les cas à couvrir, selon le type de réponse :
   a) Les confusions plausibles : cite 3 à 5 mauvaises réponses qu'un joueur pourrait vraiment donner (même catégorie, même époque, même pays, même domaine), suivies de « … », puis précise « même mal écrit(e) ». Exemple : « désigne un autre joueur (Samuel Eto'o, Didier Drogba, Roger Milla…), même mal écrit ».
   b) Les réponses partielles insuffisantes : pour une personne, un prénom seul ne suffit jamais. Écris-le explicitement avec le prénom réel, par exemple « ne donne que le prénom « George » ».
   c) L'élément indispensable : termine par ce que la réponse doit absolument contenir. Pour une personne, c'est le nom de famille, par exemple « ou ne contient pas le nom Weah ». Si ce nom s'écrit souvent avec des fautes, ajoute les variantes à accepter, par exemple « ou ne contient ni le nom Graf ni une orthographe proche (Graff, Grafe) ».
   d) Les nombres et les durées : « donne un autre nombre que dix, en chiffres ou en lettres (sept, huit, cinq, douze…) ». Cite des nombres proches ET certains écrits en lettres. Pour une durée, exclus aussi les autres unités, par exemple « exprime une durée en minutes (une minute…) ».
   e) Les lieux et les équipes : cite les pays ou équipes concurrents, y compris leurs surnoms, par exemple « (Australie, Wallabies, France…) ».

   N'écris pas de règle contraire à la bonne réponse. Ne cite jamais une forme acceptable de la bonne réponse comme exemple de réponse fausse.

5. "aliases" (au maximum 100 éléments, peut être vide)
   - C'est un filet de secours utilisé UNIQUEMENT si jev est indisponible. On compare alors la réponse mot pour mot, sans tenir compte des majuscules, des accents ni de la ponctuation finale.
   - Mets 2 à 6 formes exactes et courantes de la bonne réponse : nom seul, orthographe alternative, nombre en lettres. Par exemple ["Weah", "Georges Weah"] ou ["dix", "10 épreuves"].
   - Pas besoin d'être exhaustif, et n'y mets jamais de forme qui serait fausse. Chaque alias doit contenir au moins une lettre ou un chiffre.

6. "explanation" (au maximum 2000 caractères)
   - Une à deux phrases, montrées aux joueurs après la réponse. Elles confirment la réponse et ajoutent un fait intéressant.

VÉRIFICATION AVANT DE RÉPONDRE
- Le JSON est valide, sans virgule finale, avec des guillemets doubles. Les guillemets internes sont des « » ou des apostrophes typographiques.
- Les "id" sont tous uniques, et chaque objet contient exactement les 5 champs.
- "criteria.true" est une réponse courte, sans consigne.
- Chaque "criteria.false" commence par « La réponse est fausse si elle » et couvre les confusions plausibles, avec « même mal écrit ». Il couvre aussi la réponse partielle, si c'est une personne, et l'élément indispensable.
- Chaque fait est exact. En cas de doute sur un fait, remplace la question.

EXEMPLE DE SORTIE ATTENDUE
[
  {
    "id": "sport-ballon-or-africain-1995",
    "question": "Quel footballeur est devenu en 1995 le premier joueur né en Afrique à remporter le Ballon d'Or ?",
    "criteria": {
      "true": "George Weah",
      "false": "La réponse est fausse si elle : désigne un autre joueur (Samuel Eto'o, Didier Drogba, Roger Milla, Abedi Pelé…), même mal écrit ; ne donne que le prénom « George » ; ou ne contient pas le nom Weah."
    },
    "aliases": ["Weah", "Georges Weah"],
    "explanation": "George Weah, international libérien, a remporté le Ballon d'Or 1995 sous les couleurs de l'AC Milan."
  },
  {
    "id": "sport-decathlon-nombre-epreuves",
    "question": "Combien d'épreuves composent le décathlon en athlétisme ?",
    "criteria": {
      "true": "10",
      "false": "La réponse est fausse si elle donne un autre nombre que dix, en chiffres ou en lettres (sept, huit, cinq, douze…)."
    },
    "aliases": ["dix", "10 épreuves", "dix épreuves"],
    "explanation": "Le décathlon regroupe dix épreuves disputées sur deux jours."
  }
]
````
