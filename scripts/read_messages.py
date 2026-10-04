"""Read native group records directly, without scrolling or sending any messages."""

import argparse
import time
from pathlib import Path

from quiz_app.config import load_settings
from quiz_app.database_reader import DatabaseReader
from quiz_app.storage import write_json


def main() -> None:
    """Report requested record count/timing; save private contents only with explicit --output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", required=True)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    settings = load_settings(root / ".env")
    start = time.perf_counter()
    messages = DatabaseReader(Path(settings.whatsapp_database), args.group).recent(args.count)
    print(
        f"Recovered {len(messages)} native records in {time.perf_counter() - start:.3f}s. "
        "No scrolling or sending."
    )
    if args.output is not None:
        write_json(args.output, [message.model_dump() for message in messages])


if __name__ == "__main__":
    main()
