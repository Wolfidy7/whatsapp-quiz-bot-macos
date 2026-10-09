"""Local exact rules, then jev threshold decisions, with alias matching as the offline fallback."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from quiz_app.jev import JevClient, NoulQuestion
from quiz_app.models import Question
from quiz_app.normalization import normalize as normalize

Scorer = Callable[[Question, dict[str, str]], dict[str, float | None]]
FALLBACK = "Repli local (jev indisponible) : "
LOCAL = "Règle locale : "
# Hidden grading guidance: with the bare question, jev accepted entities related to the answer
# (actor for director, character for author, host country for winner) far above the threshold.
INSTRUCTIONS = (
    "Question posée à un joueur de quiz : « {question} »\n"
    "Bonne réponse attendue : {answer}.\n"
    "La réponse du joueur est correcte si elle désigne la même chose que la bonne réponse attendue, "
    "même sous une forme incomplète ou mal écrite : le nom de famille seul, un surnom ou un nom d'usage "
    "connu, une faute de frappe, une transcription ou une traduction différente sont corrects. "
    "Elle est fausse si elle désigne une autre entité, même étroitement liée à la bonne réponse "
    "(acteur, réalisateur, auteur, personnage, pays, club, lieu, équipe adverse). "
    "Elle est aussi fausse si elle se contente de reprendre un nom ou un élément déjà cité dans la "
    "question, ou le titre de l'œuvre au lieu de ce qui est demandé."
)


@dataclass(frozen=True)
class Verdict:
    """Acceptance evidence shared by live scoring and the editor: jev score or matched alias."""

    accepted: bool
    alias: str | None
    reason: str
    score: float | None = None
    source: Literal["jev", "fallback", "local"] = "fallback"


def offline(question: Question, answers: dict[str, str]) -> dict[str, float | None]:
    """Score nothing, so every answer uses the local fallback; never touches the network."""
    return dict.fromkeys(answers)


def noul_question(question: Question) -> NoulQuestion:
    """Map a bank question to jev with hidden grading guidance; aliases are never sent."""
    instructions = INSTRUCTIONS.format(question=question.question, answer=question.criteria.true)
    return NoulQuestion(question.id, instructions, question.criteria.true, question.criteria.false)


def jev_scorer(api_key: str, model: str) -> Scorer:
    """Score round answers with jev in parallel; without a key, every answer falls back locally."""
    if not api_key:
        return offline
    client = JevClient(api_key, model)
    return lambda question, answers: client.score_many(noul_question(question), answers)


def local_verdict(question: Question, answer: str, ignore_accents: bool = True) -> Verdict | None:
    """Decide without jev: accept an exact reference or alias, reject a copy of a question passage."""
    value = normalize(answer, ignore_accents)
    if not value:
        return None
    for alias in [question.criteria.true, *question.aliases]:
        if value == normalize(alias, ignore_accents):
            return Verdict(True, alias, LOCAL + "correspondance exacte avec une référence.", source="local")
    if re.search(rf"(?<!\w){re.escape(value)}(?!\w)", normalize(question.question, ignore_accents)):
        return Verdict(False, None, LOCAL + "la réponse reprend un élément de la question.", source="local")
    return None


def fallback_verdict(question: Question, answer: str, ignore_accents: bool = True) -> Verdict:
    """Accept only a complete normalized match with the true criterion or a declared alias."""
    value = normalize(answer, ignore_accents)
    if value:
        for alias in [question.criteria.true, *question.aliases]:
            if value == normalize(alias, ignore_accents):
                return Verdict(True, alias, FALLBACK + "correspondance exacte après normalisation.")
    return Verdict(False, None, FALLBACK + "aucune référence ni alias ne correspond.")


def evaluate_answer(
    question: Question, answer: str, score: float | None, threshold: float, ignore_accents: bool = True
) -> Verdict:
    """Apply local rules first, then the jev threshold; fall back locally without a score."""
    local = local_verdict(question, answer, ignore_accents)
    if local:
        return local
    if score is None:
        return fallback_verdict(question, answer, ignore_accents)
    accepted = score >= threshold
    comparison = "≥" if accepted else "<"
    return Verdict(accepted, None, f"Score jev {score:.3f} {comparison} seuil {threshold:.3f}.", score, "jev")


def extract_answer(body: str, prefix: str) -> str | None:
    """Extract the nonempty answer after a case-insensitive command plus whitespace."""
    parts = body.strip().split(maxsplit=1)
    if len(parts) != 2 or parts[0].casefold() != prefix.casefold():
        return None
    return parts[1].strip() or None
