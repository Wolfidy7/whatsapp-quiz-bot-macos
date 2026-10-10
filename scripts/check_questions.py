"""Check a generated question batch against the app schema and jev authoring rules; optionally save it."""

import argparse
import sys
from pathlib import Path

from quiz_app.batches import check, load_inputs, merge
from quiz_app.errors import QuizError


def run(batch_path: Path, bank_path: Path, mode: str | None) -> int:
    """Validate, print a report and optionally merge into or replace the bank; return a process exit code."""
    try:
        batch, bank = load_inputs(batch_path, bank_path)
    except (OSError, ValueError, QuizError) as exc:
        print(f"❌ Lecture impossible : {exc}")
        return 1
    # A replaced bank is discarded, so its ids and questions cannot conflict with the batch.
    errors, warnings = check(batch, [] if mode == "replace" else bank)
    for line in errors:
        print(f"❌ {line}")
    for line in warnings:
        print(f"⚠️ {line}")
    if errors:
        print(f"{len(errors)} erreur(s) bloquante(s) sur {len(batch)} questions : à corriger d'abord.")
        return 1
    print(f"✅ {len(batch)} questions conformes ({len(warnings)} avertissement(s)).")
    if mode == "merge":
        backup = merge(batch, bank, bank_path)
        print(
            f"✅ Ajoutées à {bank_path} ({len(bank) + len(batch)} questions). "
            f"Sauvegarde : {backup or 'aucune'}"
        )
    elif mode == "replace":
        backup = merge(batch, [], bank_path)
        print(
            f"✅ {bank_path} remplacée par le lot ({len(batch)} questions, {len(bank)} retirées). "
            f"Sauvegarde : {backup or 'aucune'}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse the command line and run the checks."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path, help="Lot JSON généré")
    parser.add_argument("--bank", type=Path, default=Path("data/questions.json"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--merge",
        dest="mode",
        action="store_const",
        const="merge",
        help="Ajouter le lot à la banque s'il est conforme",
    )
    mode.add_argument(
        "--replace",
        dest="mode",
        action="store_const",
        const="replace",
        help="Remplacer toute la banque par le lot s'il est conforme",
    )
    args = parser.parse_args(argv)
    return run(args.batch, args.bank, args.mode)


if __name__ == "__main__":
    sys.exit(main())
