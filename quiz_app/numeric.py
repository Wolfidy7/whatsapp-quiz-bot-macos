"""Exact decimal answers with explicitly declared equivalent unit labels."""

import re
from decimal import Decimal

from quiz_app.normalization import normalize

NUMBER = re.compile(r"([+-]?(?:[0-9]+(?:[.,][0-9]+)?|[.,][0-9]+))(.*)")


def numeric_value(text: str, units: list[str], require_unit: bool, ignore_accents: bool) -> Decimal | None:
    """Return an exact decimal for a full value and allowed unit, or None for invalid input.

    Unit labels are equivalent spellings, never conversion factors. Decimal comma and
    dot are accepted; grouping, expressions and scientific notation are unsupported.
    """
    match = NUMBER.fullmatch(normalize(text, ignore_accents))
    if match is None:
        return None
    number, unit = match.groups()
    unit = unit.strip()
    if unit:
        if unit not in {normalize(label, ignore_accents) for label in units}:
            return None
    elif require_unit:
        return None
    return Decimal(number.replace(",", "."))
