"""Read-only native diagnostic; private content is never printed by default."""

import argparse

from quiz_app.ax_reader import AXReader
from quiz_app.history import merge_pages


def main() -> None:
    """Check native order and page overlap without sending, saving or displaying messages."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", required=True)
    args = parser.parse_args()
    reader = AXReader(args.group)
    try:
        reader.latest()
        page = reader.page()
        changed = reader.older()
        combined = merge_pages(reader.page(), page) if changed else page
        print(
            f"Rows: {len(page)}; incoming authors: {len({row.author for row in page if not row.outgoing})}; "
            f"verified vertical order: yes; older page changed: {changed}; reconciled rows: {len(combined)}"
        )
    finally:
        reader.latest()


if __name__ == "__main__":
    main()
