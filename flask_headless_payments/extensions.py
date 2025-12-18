"""
flask_headless_payments.extensions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Flask extensions initialization.
"""

from flask_sqlalchemy import SQLAlchemy

# Singletons
_db = None
db = None  # Will be set before models are imported


def get_db():
    """Get or create SQLAlchemy instance."""
    global _db, db
    if _db is None:
        _db = SQLAlchemy()
        db = _db
    return _db


def set_db(db_instance):
    """Set the SQLAlchemy instance (used when reusing app's existing db)."""
    global _db, db
    _db = db_instance
    db = db_instance

