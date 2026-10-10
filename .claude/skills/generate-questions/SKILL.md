---
name: generate-questions
description: Génère un lot de questions de quiz pour le bot WhatsApp (format jev avec criteria true/false et alias), les vérifie, puis remplace entièrement la banque data/questions.json par ce lot. À utiliser dès que l'utilisateur veut créer, générer, ajouter ou préparer des questions de quiz, même sans dire « skill », par exemple « fais-moi 30 questions sur le cinéma, niveau difficile » ou « refais une banque de questions de géo ».
argument-hint: "<thèmes> <nombre> <difficulté> — ex. « cinéma, manga 40 difficile »"
---

# Générer des questions de quiz

Demande de l'utilisateur : $ARGUMENTS

Le but est de remplacer tout le contenu de `data/questions.json` par un nouveau lot de questions que jev note correctement : une bonne réponse est acceptée, et aucun piège plausible ne passe. Les règles qui le garantissent ont été mesurées sur sept lots d'environ 100 questions. Elles se trouvent dans `docs/question-generation-prompt.md`, qui reste la seule source de vérité. Ne les recopie pas de mémoire.

## 1. Paramètres

Extrais de la demande :
- **les thèmes** : un ou plusieurs ;
- **le nombre de questions** ;
- **la difficulté** : facile, moyenne ou difficile.

Si le nombre ou les thèmes manquent, demande-les. Si seule la difficulté manque, prends « moyenne » et dis-le. Avec plusieurs thèmes, répartis les questions à peu près équitablement, sauf indication contraire.

## 2. Contexte à lire

- Lis la section `## Prompt` de `docs/question-generation-prompt.md` en entier. C'est ton cahier des charges : format, choix des questions, règles des critères, alias, explication et vérification finale. La section « Ce que les tests ont montré », plus haut, explique pourquoi chaque règle existe. Lis-la si une règle te semble arbitraire.
- Inutile de lire `data/questions.json` : le lot remplace la banque. Les identifiants doivent seulement être uniques dans le lot.

## 3. Générer

Rédige le lot en suivant le prompt, puis écris-le dans `data/generated-questions.json`, sous forme de tableau JSON seul. Ce fichier sert d'intermédiaire avant l'enregistrement : il est écrasé à chaque appel.

Points qui ont causé le plus d'erreurs lors des itérations précédentes :
- **Alias.** Ils sont acceptés d'office, sans passer par jev. Un alias insuffisant donne donc des points à tort. Exemples à proscrire : un prénom seul, une description vague, ou un mot déjà présent dans la question.
- **Entités liées.** L'acteur pour un réalisateur, le personnage pour un auteur, le pays pour une ville : il faut les citer dans `criteria.false` avec « au lieu de ».
- **Faits datés.** Les « depuis », « actuellement » ou « publie toujours » deviennent faux avec le temps. Date la question ou choisis-en une autre.

## 4. Contrôler le format

```bash
PYTHONPATH=. .venv/bin/python scripts/check_questions.py data/generated-questions.json
```

Le script vérifie :
- le schéma de l'application ;
- la forme de `criteria.false` ;
- l'absence de consigne dans `criteria.true` ;
- les alias dangereux.

Corrige toutes les erreurs (❌) et relance jusqu'à ce que le script réponde ✅. Examine chaque avertissement (⚠️) : un alias réduit au premier mot de la réponse ne se garde que pour une personne connue sous ce seul nom, comme Dante.

## 5. Relire les faits

Relis le lot comme un vérificateur sceptique, question par question. Les lots précédents contenaient des erreurs dans environ 5 % des questions, surtout dans les explications : un nombre de sets inexact, un rang dans une série erroné, une œuvre présentée comme encore en cours, un titre inventé dans les pièges.

Pour chaque question, vérifie :
- que la bonne réponse est exacte et unique ;
- que la question n'est pas périmée ;
- que chaque fait de l'explication est sûr ;
- que les pièges cités existent réellement.

Utilise la recherche web pour les faits récents, chiffrés ou dont tu n'es pas certain. Remplace une question douteuse plutôt que de la garder avec une réserve. Relance ensuite le contrôle de l'étape 4.

## 6. Remplacer la banque

```bash
PYTHONPATH=. .venv/bin/python scripts/check_questions.py data/generated-questions.json --replace
```

Le script refait tous les contrôles et refuse d'enregistrer s'il reste une erreur. Sinon, il sauvegarde l'ancienne banque dans `data/questions.before-merge-<date>.json`, puis la remplace entièrement par le lot en passant par la validation de l'application. Les anciennes questions ne restent que dans cette sauvegarde.

## 7. Compte rendu

Termine par un court résumé :
- le nombre de questions de la nouvelle banque, par thème, et la difficulté ;
- les questions remplacées pendant la relecture des faits, avec la raison ;
- les avertissements conservés ;
- le nombre de questions retirées et le chemin de la sauvegarde.

N'affiche pas le JSON complet : il est dans la banque.
