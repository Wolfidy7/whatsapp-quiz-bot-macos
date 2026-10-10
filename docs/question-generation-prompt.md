# Prompt de génération de questions

Dans Claude Code, le plus simple est d'utiliser le skill `/generate-questions <thèmes> <nombre> <difficulté>`. Il applique ce prompt, contrôle le lot avec `scripts/check_questions.py`, relit les faits et remplace toute la banque par le nouveau lot, après une sauvegarde horodatée. Ce prompt sert aussi à faire générer des questions par une autre IA, au format attendu par la banque de questions jev. Remplacez `[NOMBRE]`, `[THÈME]` et la difficulté, puis collez le JSON obtenu dans **Gérer la banque de questions** et cliquez sur **Enregistrer les questions**.

- **Coller remplace toute la banque.** La zone JSON contient la banque entière. Pour ajouter des questions, insérez les nouveaux objets dans le tableau existant, juste avant le `]` final, en ajoutant une virgule.
- **Une seule question invalide fait rejeter tout le lot**, par exemple un identifiant accentué. Corrigez-la avant d'enregistrer.
- **Testez quelques questions avant de jouer**, surtout les questions sur des personnes. Dans le testeur, essayez un prénom seul, une mauvaise réponse proche et une faute de frappe. Si un piège passe, ajoutez ce cas au critère faux.

## Ce que les tests ont montré

Toutes les mesures ont été faites avec `jev-latest`, au seuil de 0,8. Chaque réponse est évaluée deux à trois fois, sur des bonnes réponses (exactes, avec faute, en forme courte) et sur des pièges plausibles.

**Itération 1, 5 questions de sport.** Trois rédactions du critère faux ont été comparées.

| Rédaction du critère faux | Résultat |
| --- | --- |
| Liste courte (« Tout autre joueur que George Weah, comme Samuel Eto'o… ») | Le prénom seul « George » est accepté jusqu'à 0,96, et « Steffi » jusqu'à 0,98 |
| Critère positif (« La réponse ne contient pas le nom Weah… ») | Les prénoms seuls restent acceptés |
| **Cas explicites (« La réponse est fausse si elle : … ; … ; … »)** | **1 erreur sur 78 évaluations** |

**Itération 2, 50 questions de culture générale générées par une IA avec ce prompt.** 33 erreurs sur 712 évaluations, soit 95,4 % de bonnes évaluations. Après correction des critères, on descend à 14 erreurs sur 684. Les enseignements, désormais intégrés au prompt :

- **Citer les orthographes acceptées dans le critère faux se retourne contre nous.** Avec « ni une orthographe proche (Curry, Curi) », la réponse « Marie Curry » tombe à 0,33 : jev associe au faux tout ce qui est écrit dans ce critère.
- **Certaines questions ne peuvent pas être notées de façon fiable.** C'est le cas quand la mauvaise réponse la plus probable est le nom même de ce qui est demandé : « oxygène » est accepté jusqu'à 0,93 pour le symbole O, et « brésilien » jusqu'à 0,86 pour la langue du Brésil. C'est aussi le cas quand un concurrent est très lié à la bonne réponse : « Anatomie d'une chute » est accepté à 0,83 pour l'Oscar du meilleur film 2024.
- **Expliquer pourquoi un piège est faux n'aide pas.** Par exemple « le Soleil est une étoile, pas une planète » ne fait pas baisser le score. Il vaut mieux citer le piège et choisir une autre question.
- **Les pièges à nommer explicitement** sont :
  - les années ou nombres écrits en lettres, comme « mille sept cent quatre-vingt-treize » accepté à 0,89 ;
  - une catégorie plus large, comme « Himalaya » accepté à 0,90 pour le plus haut sommet ;
  - un ancien nom, comme « URSS » accepté à 0,84 ;
  - une réponse qui en cite plusieurs, comme « Pacifique Nord et Atlantique » accepté à 0,88.
- **Les erreurs de forme** sont :
  - un identifiant accentué, qui a bloqué tout le lot ;
  - un identifiant sans rapport avec la question ;
  - un film inventé dans la liste des pièges ;
  - des superlatifs approximatifs dans les explications.

**Itération 3, 100 questions générées avec la version 2 du prompt.** Le lot est importé tel quel, sans aucune correction, et obtient **96,4 % de bonnes évaluations** (1309 sur 1358). 75 questions sur 100 ne font aucune erreur. Les erreurs restantes relèvent de deux familles, désormais traitées dans le prompt :

- **Une entité liée à la réponse, mais d'une autre nature, est acceptée.** C'est le cas du lieu où se trouve la réponse (« Saint-Denis » pour le Stade de France à 0,94, « Dubaï » pour la Burj Khalifa, « Autriche » pour Salzbourg, « Catalogne » pour Barcelone), d'un membre (« John Lennon » pour les Beatles, à 0,93), d'un personnage (« Sancho Panza », « d'Artagnan ») ou d'un auteur (« Rouget de Lisle » pour La Marseillaise). Les nommer explicitement avec « au lieu de » divise ces erreurs par deux. Le lieu et le membre restent parfois juste au-dessus du seuil, entre 0,80 et 0,86.
- **La règle du prénom seul est appliquée à tort aux personnes connues sous un seul nom.** « Dante » était refusé à 0,53. Une fois la règle retirée, il est accepté à chaque fois.

**Itération 4 : 100 questions de sport, de cinéma et de manga.** Le lot est encore importé tel quel. Mais sur ces thèmes, chaque réponse a une entité liée connue : l'acteur d'un réalisateur, le personnage d'un auteur, le pays d'un vainqueur. jev en a accepté 128, et le score tombe à **88,8 %**, même quand ces entités étaient citées dans le critère faux (« Isao Takahata » à 0,95). Changer le seuil n'y change rien. La correction est donc faite dans l'application : elle envoie à jev une consigne fixe, invisible pour les joueurs. Cette consigne donne la bonne réponse attendue, tolère les formes incomplètes ou mal écrites et rejette toute autre entité, même liée (voir le README). Résultat sur le même lot : **97,4 %, avec 0 piège accepté**. Sur le lot de l'itération 2, on passe de 96,6 % à 97,1 %, avec 0 piège accepté au lieu de 15, y compris « oxygène » et « brésilien ». En contrepartie, quelques réponses justes mais mal écrites sont refusées.

**Itération 5 : 100 questions de santé, de géographie et de séries TV, notées avec la consigne.** Le lot est importé tel quel et obtient **98,6 % de bonnes évaluations hors fautes de frappe** (96,8 % en les comptant), avec 90 questions sur 100 sans erreur. Les 12 pièges encore acceptés, sur 800, reprenaient presque tous un nom déjà présent dans la question : « Ouagadougou » pour « Quel pays a pour capitale Ouagadougou ? », « Hanoï », « Mark Frost », « Doctor Who ». Une phrase ajoutée à la consigne les fait tous refuser : **99,3 % hors fautes, 0 piège accepté, 96 questions sur 100 sans erreur.**

**Itération 6 : 100 questions de santé, de psychologie et sur les pirates, avec le prompt inchangé.** Le lot obtient 97,3 % hors fautes de frappe, mais 10 pièges sont acceptés, entre 0,80 et 0,84. Ce sont tous des noms recopiés depuis la question : « Doliprane », « Nurofen », « Plasmodium », « thyroxine », « Calico Jack ». Deux règles locales sont ajoutées, appliquées avant jev : une réponse recopiée de la question est refusée, et une réponse identique à un alias est acceptée (voir le README). Résultat : **98,9 % hors fautes, 0 piège accepté, 93 questions sur 100 sans erreur.** Conséquence pour le prompt : les alias doivent être strictement corrects, puisqu'ils sont désormais acceptés d'office.

Le critère vrai est aussi annoncé aux joueurs comme « la bonne réponse ». Il doit donc rester une réponse courte, et les nuances de notation vont dans le critère faux.

## Prompt

````text
Tu génères des questions de quiz en français pour un jeu sur WhatsApp. Les joueurs répondent librement par un court message. Chaque réponse est notée automatiquement par un modèle de décision (jev). Il reçoit la question, un critère « vrai », un critère « faux » et la réponse du joueur, et renvoie la probabilité que la réponse soit correcte. La réponse est acceptée si cette probabilité est d'au moins 0,8.

TÂCHE
Génère [NOMBRE] questions sur le thème [THÈME], de difficulté [FACILE / MOYENNE / DIFFICILE].

FORMAT DE SORTIE — STRICT
- Réponds UNIQUEMENT avec un tableau JSON valide. Pas de texte avant ou après, pas de bloc ```json, pas de commentaires.
- Chaque élément contient exactement ces 5 champs, et aucun autre. Une seule erreur de format dans une seule question fait rejeter TOUT le lot.
  {
    "id": string,
    "question": string,
    "criteria": { "true": string, "false": string },
    "aliases": [string, ...],
    "explanation": string
  }

CHOIX DES QUESTIONS — ce qui rend la notation fiable
Le correcteur est fiable quand la bonne réponse est un nom propre, un nombre ou une date, et que les mauvaises réponses plausibles sont des choses DIFFÉRENTES de la bonne réponse. Écarte une question, et choisis-en une autre, si l'un de ces cas s'applique :
- La mauvaise réponse la plus probable est le nom même de ce qui est demandé, ou un mot de la même famille. Par exemple « Quel est le symbole de l'oxygène ? », où un joueur répondra « oxygène », ou « Quelle langue parle-t-on au Brésil ? », où il répondra « brésilien ».
- Une mauvaise réponse très plausible est fortement liée à la bonne réponse : même cérémonie, même événement, prix voisin. Par exemple « Quel film a reçu l'Oscar du meilleur film en 2024 ? », alors qu'un autre film nommé a reçu la Palme d'or.
- La réponse est une abréviation, un symbole ou un code d'une ou deux lettres.
- Plusieurs réponses peuvent être défendues. Par exemple, « le plus grand organe » ou « le plus petit pays » peuvent prêter à discussion.

RÈGLES PAR CHAMP

1. "id"
   - UNIQUEMENT des lettres a à z SANS ACCENT, des chiffres, « - » ou « _ ». Pas d'espace, pas d'apostrophe, au maximum 80 caractères. Transforme les accents : « misérables » devient « miserables ».
   - Il est unique dans le tableau et décrit CETTE question. Préfixe-le par le thème, par exemple « sport-decathlon-nombre-epreuves ».

2. "question" (au maximum 2000 caractères)
   - Elle doit avoir une seule bonne réponse, factuelle et vérifiable.
   - La réponse doit pouvoir s'écrire en quelques mots : un nom, un lieu, un nombre, une date. Évite les questions qui demandent une liste ou une phrase.
   - Si la réponse dépend du moment, date la question (par exemple « en 2024 »), sinon elle deviendra fausse avec le temps.
   - La question est envoyée telle quelle aux joueurs. Elle doit donc être claire, sans ambiguïté et sans indice qui donne la réponse.

3. "criteria.true" (au maximum 500 caractères)
   - C'est la bonne réponse, sous sa forme la plus courante, par exemple « George Weah », « 24 secondes » ou « La Nouvelle-Zélande ».
   - IMPORTANT : ce texte est annoncé aux joueurs comme « la bonne réponse ». Il ne doit contenir AUCUNE consigne de notation (pas de « y compris… » ni « accepter… »). Juste la réponse.

4. "criteria.false" (au maximum 500 caractères) — LE CHAMP LE PLUS IMPORTANT
   Le modèle a tendance à accepter trop facilement une réponse partielle, une faute de frappe sur un AUTRE nom, un nombre proche ou une catégorie voisine. C'est ce champ qui l'en empêche. Une formulation vague comme « Toute autre réponse » donne de mauvais résultats.

   Utilise TOUJOURS cette structure, dont l'efficacité a été mesurée :
   « La réponse est fausse si elle : [cas 1] ; [cas 2] ; [cas 3]. »

   Les cas à couvrir, selon le type de réponse :
   a) Les confusions plausibles : cite 3 à 5 mauvaises réponses qu'un joueur pourrait vraiment donner (même catégorie, même époque, même pays, même domaine), suivies de « … », puis précise « même mal écrit(e) ». Exemple : « désigne un autre joueur (Samuel Eto'o, Didier Drogba, Roger Milla…), même mal écrit ». Ne cite que des éléments qui existent réellement, et n'invente jamais un titre, un nom ou un lieu.
   b) Les réponses partielles insuffisantes : pour une personne, un prénom seul ne suffit pas. Écris-le explicitement avec le prénom réel, par exemple « ne donne que le prénom « George » ».
      EXCEPTION : si la personne est couramment désignée par un seul nom (Dante, Michel-Ange, Raphaël, Napoléon, Molière, Voltaire, Pelé…), n'écris PAS cette règle. L'élément indispensable devient ce nom usuel, par exemple « ou ne contient pas le nom Dante ».
   c) Les catégories voisines, selon le cas :
      - une catégorie plus large ou un ensemble qui contient la réponse : « désigne une chaîne de montagnes ou une région (Himalaya, Alpes…) au lieu d'un sommet », ou « désigne la ville qui l'entoure (Rome) » ;
      - un ancien nom ou un ancien État : « URSS, Union soviétique » ;
      - un objet d'une autre nature : « désigne une étoile ou un autre astre (le Soleil, la Lune…) », « désigne une substance qui n'est pas un métal (eau, brome…) » ;
      - plusieurs réponses à la fois : « cite plusieurs océans ».
   d) Les entités LIÉES à la réponse mais d'une autre nature. C'est la cause d'erreur la plus fréquente, et elle est OBLIGATOIRE dès qu'une telle entité est connue. Formule-la toujours avec « au lieu de » :
      - le lieu où se trouve la réponse : « désigne la ville ou le pays où il se trouve (Dubaï…) au lieu du bâtiment », « désigne la région ou le pays (Catalogne, Espagne) au lieu de la ville » ;
      - une autre ville du pays demandé : « désigne une ville (Hô Chi Minh-Ville…) au lieu d'un pays » ;
      - un membre d'un groupe : « désigne un membre du groupe (John Lennon, Paul McCartney…) au lieu du groupe » ;
      - un personnage d'une œuvre : « désigne un personnage du roman (d'Artagnan, Athos…) au lieu de l'auteur » ;
      - l'auteur ou le créateur d'une œuvre : « désigne son auteur (Rouget de Lisle) au lieu du chant ».
   e) Les nombres, les années et les durées : « donne une autre année que 1789, en chiffres ou en lettres (1788, 1792, 1799, mille sept cent quatre-vingt-treize…) ». Cite toujours des valeurs proches ET au moins une écrite en lettres. Pour une durée, exclus aussi les autres unités, par exemple « exprime une durée en minutes (une minute…) ».
   f) L'élément indispensable : termine par ce que la réponse doit absolument contenir. Pour une personne, c'est le nom de famille, par exemple « ou ne contient pas le nom Weah ». Pour un lieu, c'est son nom, par exemple « ou ne contient pas le nom Ottawa ».

   INTERDIT dans "criteria.false" :
   - Citer des formes ACCEPTÉES de la bonne réponse : orthographes proches, variantes, traductions, ou une parenthèse « (X est accepté) ». Le modèle associe au faux tout ce qui est écrit dans ce critère, et refuse alors ces formes. Les formes acceptées vont UNIQUEMENT dans "aliases".
   - Toute règle qui contredit la bonne réponse, ou qui dit qu'un cas est accepté.
   - Expliquer pourquoi un piège est faux, par exemple « le Soleil est une étoile, pas une planète ». Cela n'aide pas : cite simplement le piège.

5. "aliases" (au maximum 100 éléments, peut être vide)
   - Une réponse identique à un alias, sans tenir compte des majuscules, des accents ni de la ponctuation finale, est ACCEPTÉE D'OFFICE, sans passer par jev. Les alias servent aussi de filet de secours si jev est indisponible.
   - Un alias ne doit donc JAMAIS être une forme insuffisante ou ambiguë : pas de prénom seul (« George »), pas de description vague (« le joueur libérien »), pas de catégorie (« Afrique »).
   - Mets 2 à 6 formes exactes et courantes de la bonne réponse : nom seul, orthographe alternative, traduction courante, nombre en lettres. Par exemple ["Weah", "Georges Weah"] ou ["dix", "10 épreuves"].
   - Pas besoin d'être exhaustif, et n'y mets jamais de forme qui serait fausse. Chaque alias doit contenir au moins une lettre ou un chiffre.

6. "explanation" (au maximum 2000 caractères)
   - Une à deux phrases, montrées aux joueurs après la réponse. Elles confirment la réponse et ajoutent un fait intéressant.
   - N'écris que des faits sûrs. Évite les superlatifs discutables (« la plus grande ville d'Afrique ») et les ordres de grandeur approximatifs (« deux fois plus grand »). En cas de doute, retire la précision.

VÉRIFICATION AVANT DE RÉPONDRE — passe chaque question en revue
- Chaque "id" ne contient que a à z, 0 à 9, « - » ou « _ », sans aucun accent. Il est unique et correspond à la question.
- Chaque objet contient exactement les 5 champs, et le JSON est valide : guillemets doubles, pas de virgule finale. Les guillemets internes sont des « » ou des apostrophes typographiques.
- Aucune question ne relève d'un des cas à écarter de la section « CHOIX DES QUESTIONS ».
- "criteria.true" est une réponse courte, sans consigne.
- Chaque "criteria.false" commence par « La réponse est fausse si elle ». Il cite :
  - des pièges réels, avec « même mal écrit » ;
  - le prénom seul, pour une personne (sauf si elle est connue sous un seul nom) ;
  - les catégories voisines pertinentes ;
  - les entités liées (lieu, membre, personnage, auteur) avec « au lieu de » ;
  - les valeurs en lettres, pour un nombre ;
  - l'élément indispensable.
- Aucun "criteria.false" ne contient de forme acceptée, de variante d'orthographe de la bonne réponse, ni de « est accepté ».
- Chaque fait de la question, de la réponse et de l'explication est exact. En cas de doute, remplace la question.

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
    "id": "histoire-prise-bastille-annee",
    "question": "En quelle année a eu lieu la prise de la Bastille ?",
    "criteria": {
      "true": "1789",
      "false": "La réponse est fausse si elle donne une autre année que 1789, en chiffres ou en lettres (1788, 1792, 1793, 1799, mille sept cent quatre-vingt-treize…)."
    },
    "aliases": ["en 1789", "mille sept cent quatre-vingt-neuf"],
    "explanation": "La prise de la Bastille a eu lieu le 14 juillet 1789 à Paris, date devenue la fête nationale française."
  },
  {
    "id": "geo-plus-haut-sommet-monde",
    "question": "Quel est le plus haut sommet du monde au-dessus du niveau de la mer ?",
    "criteria": {
      "true": "L'Everest",
      "false": "La réponse est fausse si elle : désigne une autre montagne (K2, Kangchenjunga, Mont Blanc, Kilimandjaro…), même mal écrite ; désigne une chaîne de montagnes ou une région (Himalaya, Alpes, Andes…) au lieu d'un sommet ; ou ne contient pas le nom Everest."
    },
    "aliases": ["Everest", "mont Everest"],
    "explanation": "Le mont Everest culmine à 8 849 mètres dans l'Himalaya, à la frontière entre le Népal et la Chine."
  }
]
````
