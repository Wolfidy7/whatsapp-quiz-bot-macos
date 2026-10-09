"""Check a generated question batch against the app schema and jev authoring rules; merge on request."""

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

from quiz_app.errors import QuizError
from quiz_app.models import Question
from quiz_app.normalization import normalize
from quiz_app.repository import load_bank, save_bank, validate_questions

FALSE_START = "La réponse est fausse si elle"
ACCEPTED_FORM = re.compile(r"accept|orthographe proche", re.IGNORECASE)
INSTRUCTION = re.compile(r"y compris|accept|toléré", re.IGNORECASE)
# « une autre ville que Londres », « au lieu de la variole » name the answer without listing it as a trap;
# « ne donne que le prénom « George » » does list a trap, so it is kept.
ANSWER_CLAUSE = re.compile(r"\bau lieu d[eu'][^;,(…]*|(?<!donne )\bqu(?:e |')[^;,(…]*", re.IGNORECASE)
REQUIRED_PART = re.compile(r"ne contient (?:pas|ni)|ne désigne pas", re.IGNORECASE)


def contains(text: str, value: str) -> bool:
    """Tell whether a normalized value appears as whole words, hyphens included, in a normalized text."""
    needle = normalize(value)
    pattern = rf"(?<![\w-]){re.escape(needle)}(?![\w-])"
    return bool(needle) and re.search(pattern, normalize(text)) is not None


def criteria_errors(question: Question) -> list[str]:
    """Report criteria that break the tested authoring rules."""
    errors = []
    if not question.criteria.false.startswith(FALSE_START):
        errors.append(f"criteria.false doit commencer par « {FALSE_START} »")
    if ACCEPTED_FORM.search(question.criteria.false):
        errors.append("criteria.false cite une forme acceptée (« accept… », « orthographe proche »)")
    if INSTRUCTION.search(question.criteria.true):
        errors.append("criteria.true contient une consigne alors qu'il est annoncé aux joueurs")
    if contains(question.question, question.criteria.true):
        errors.append("la question contient déjà la bonne réponse")
    return errors


def traps(question: Question) -> str:
    """Return the traps of criteria.false, without the clauses that name the answer itself."""
    return ANSWER_CLAUSE.sub("", REQUIRED_PART.split(question.criteria.false, maxsplit=1)[0])


def alias_errors(question: Question) -> list[str]:
    """Report aliases that the local exact rule would wrongly accept."""
    errors = []
    for alias in question.aliases:
        if contains(question.question, alias):
            errors.append(
                f"alias « {alias} » repris de la question : un joueur qui recopie la question gagnerait"
            )
        if contains(traps(question), alias):
            errors.append(f"alias « {alias} » cité comme piège dans criteria.false")
    return errors


def warnings_for(question: Question, bank: list[Question]) -> list[str]:
    """Warn about likely duplicates and first-word aliases that are fine only for single-name people."""
    warnings = [
        f"question déjà présente dans la banque ({other.id})"
        for other in bank
        if normalize(other.question) == normalize(question.question)
    ]
    words = question.criteria.true.split()
    warnings += [
        f"alias « {alias} » = premier mot seul de la réponse : à garder seulement pour un nom usuel (Dante…)"
        for alias in question.aliases
        if len(words) > 1 and not alias.isdigit() and normalize(alias) == normalize(words[0])
    ]
    return warnings


def check(questions: list[Question], bank: list[Question]) -> tuple[list[str], list[str]]:
    """Return blocking errors and warnings, each prefixed by the question id."""
    errors = [f"{q.id} : {e}" for q in questions for e in criteria_errors(q) + alias_errors(q)]
    warnings = [f"{q.id} : {w}" for q in questions for w in warnings_for(q, bank)]
    clash = {q.id for q in questions} & {q.id for q in bank}
    errors += [f"{qid} : identifiant déjà utilisé dans la banque" for qid in sorted(clash)]
    return errors, warnings


def merge(batch: list[Question], bank: list[Question], bank_path: Path) -> Path | None:
    """Back up an existing bank, then append the batch through the app's validated atomic save."""
    backup = None
    if bank_path.exists():
        backup = bank_path.with_name(f"{bank_path.stem}.before-merge-{time.strftime('%Y%m%d-%H%M%S')}.json")
        shutil.copy2(bank_path, backup)
    save_bank(bank_path, [q.model_dump() for q in bank + batch])
    return backup


def load_inputs(batch_path: Path, bank_path: Path) -> tuple[list[Question], list[Question]]:
    """Read the batch and the current bank; raise QuizError, OSError or ValueError when unreadable."""
    batch = validate_questions(json.loads(batch_path.read_text(encoding="utf-8")))
    return batch, load_bank(bank_path) if bank_path.exists() else []


def run(batch_path: Path, bank_path: Path, apply: bool) -> int:
    """Validate, print a report and optionally merge; return a process exit code."""
    try:
        batch, bank = load_inputs(batch_path, bank_path)
    except (OSError, ValueError, QuizError) as exc:
        print(f"❌ Lecture impossible : {exc}")
        return 1
    errors, warnings = check(batch, bank)
    for line in errors:
        print(f"❌ {line}")
    for line in warnings:
        print(f"⚠️ {line}")
    if errors:
        print(f"{len(errors)} erreur(s) bloquante(s) sur {len(batch)} questions : à corriger avant fusion.")
        return 1
    print(f"✅ {len(batch)} questions conformes ({len(warnings)} avertissement(s)).")
    if apply:
        backup = merge(batch, bank, bank_path)
        print(
            f"✅ Ajoutées à {bank_path} ({len(bank) + len(batch)} questions). "
            f"Sauvegarde : {backup or 'aucune'}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse the command line and run the checks."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path, help="Lot JSON généré")
    parser.add_argument("--bank", type=Path, default=Path("data/questions.json"))
    parser.add_argument("--merge", action="store_true", help="Ajouter le lot à la banque s'il est conforme")
    args = parser.parse_args(argv)
    return run(args.batch, args.bank, args.merge)


if __name__ == "__main__":
    sys.exit(main())
