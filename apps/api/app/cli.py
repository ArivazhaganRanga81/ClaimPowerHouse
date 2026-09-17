from __future__ import annotations

import argparse

from .database import SessionLocal, create_schema
from .services.rag import rebuild_lexical_index
from .services.backup import restore_backup_offline
from .services.seed import seed_demo


def initialize(with_rag: bool = False) -> None:
    create_schema()
    with SessionLocal() as session:
        count = seed_demo(session)
        print(f"Database ready; seeded {count} claims.")
        if with_rag:
            print(rebuild_lexical_index(session))


def main() -> None:
    parser = argparse.ArgumentParser(prog="claim-power-house")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init", help="Create, migrate, and seed local stores")
    init_parser.add_argument("--with-rag", action="store_true")
    serve_parser = subparsers.add_parser("serve", help="Start the local API and bundled web UI")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    restore_parser = subparsers.add_parser("restore", help="Restore a backup while the API is stopped")
    restore_parser.add_argument("artifact_name")
    restore_parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.command == "init":
        initialize(with_rag=args.with_rag)
    elif args.command == "serve":
        import uvicorn

        uvicorn.run("app.main:app", host=args.host, port=args.port)
    elif args.command == "restore":
        if args.confirm != "RESTORE":
            raise SystemExit("Restore requires --confirm RESTORE")
        restore_backup_offline(args.artifact_name)
        print("Backup restored. Start the API to run migration validation.")


if __name__ == "__main__":
    main()
