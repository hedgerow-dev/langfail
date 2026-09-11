"""Command-line entry point for running the Modelbay app locally."""
from __future__ import annotations

from . import create_app


def main() -> None:
    """Run the development server."""
    create_app().run(host="127.0.0.1", port=5001, debug=True)


if __name__ == "__main__":
    main()
