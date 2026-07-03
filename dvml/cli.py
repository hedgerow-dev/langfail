"""Command-line entrypoints for ModelForge (server, worker, seed)."""
from __future__ import annotations

import secrets

import click
from flask import Flask
from flask.cli import with_appcontext

from .core.db import db
from .core.security import hash_password


def register_cli(app: Flask) -> None:
    app.cli.add_command(seed_command)
    app.cli.add_command(worker_command)


@click.command("seed")
@with_appcontext
def seed_command():
    """Create demo users so the platform is usable out of the box."""
    from .models import User

    if User.query.filter_by(username="admin").first():
        click.echo("already seeded")
        return
    admin = User(username="admin", password_hash=hash_password("admin123"),
                 role="admin", api_token=secrets.token_hex(16))
    alice = User(username="alice", password_hash=hash_password("alice123"),
                 role="user", api_token=secrets.token_hex(16))
    bob = User(username="bob", password_hash=hash_password("bob123"),
               role="user", api_token=secrets.token_hex(16))
    db.session.add_all([admin, alice, bob])
    db.session.commit()
    click.echo("seeded users: admin/admin123, alice/alice123, bob/bob123")


@click.command("worker")
@with_appcontext
def worker_command():
    """Drain the background job queue (dataset import, model conversion, training)."""
    from .workers.runner import run_forever

    run_forever()


def main() -> None:
    from . import create_app

    create_app().run(host="127.0.0.1", port=5000, debug=True)
