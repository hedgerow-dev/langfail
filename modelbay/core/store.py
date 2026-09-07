"""The SQLAlchemy handle, shared by the records module and the HTTP surface."""
from __future__ import annotations

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
