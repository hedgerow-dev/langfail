"""Database handle shared across the application."""
from __future__ import annotations

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
