"""Command line: ``python -m larchway.cli {serve,init-db,drain}``."""
from __future__ import annotations

import argparse
from dataclasses import replace

from . import domain
from .adapters.fs import prepare_data_dir
from .db import connect, init_schema
from .main import create_app, load_package
from .seed import seed
from .settings import Settings
from .worker import drain_once


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="larchway")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="run the web app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8040)
    commands.add_parser("init-db", help="create tables and starter members")
    commands.add_parser("drain", help="run pending background work until the queue is empty")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    if args.command == "serve":
        import uvicorn

        uvicorn.run(create_app(replace(settings, debug=True)), host=args.host, port=args.port)
        return

    prepare_data_dir(settings)
    conn = connect(settings.database_path)
    try:
        init_schema(conn)
        if args.command == "init-db":
            seed(conn)
            print(f"database ready at {settings.database_path}")
        elif args.command == "drain":
            load_package(domain)
            count = 0
            while drain_once(conn) is not None:
                count += 1
            print(f"processed {count} item(s)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
