"""Launch the loopback-only web service."""

import uvicorn

from quiz_app.app import ROOT, create_app
from quiz_app.config import load_settings


def main() -> None:
    """Load validated settings and run one local worker; errors remain explicit."""
    settings = load_settings(ROOT / ".env")
    uvicorn.run(create_app(), host="127.0.0.1", port=settings.port, workers=1)


if __name__ == "__main__":
    main()
